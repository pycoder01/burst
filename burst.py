from Box2D import *
import pyglet
from pyglet.gl import *
import rabbyt

from math import *
from operator import attrgetter
import random
import sys

PLAYER_1_GROUP = -1
PLAYER_2_GROUP = -2
ASTEROID_GROUP = -3

def create_circle_vertex_list(center=(0., 0.), radius=1., vertex_count=100):
    x, y = center
    coords = []
    for i in xrange(vertex_count):
        angle = 2. * pi * float(i) / float(vertex_count)
        coords.append(x + radius * cos(angle))
        coords.append(y + radius * sin(angle))
        if i:
            coords.extend(coords[-2:])
    coords.extend(coords[:2])
    return pyglet.graphics.vertex_list(len(coords) // 2, ('v2f', coords))

def debug_draw(world):
    circle_vertex_list = create_circle_vertex_list()
    for body in world.bodyList:
        glPushMatrix()
        x, y = body.position.tuple()
        glTranslatef(x, y, 0.)
        glRotatef(rad_to_deg(body.angle), 0., 0., 1.)
        for shape in body.shapeList:
            if isinstance(shape, b2CircleShape):
                glPushMatrix()
                x, y = shape.localPosition.tuple()
                glTranslatef(x, y, 0.)
                glScalef(shape.radius, shape.radius, shape.radius)
                circle_vertex_list.draw(GL_LINES)
                glPopMatrix()
        glPopMatrix()

def rad_to_deg(angle):
    return angle * 180. / pi

def create_shadow(sprite, texture, x=20, y=-20):
    """Create a shadow sprite."""
    return MySprite(texture, scale=sprite.scale, alpha=0.8,
                    rot=(sprite.attrgetter('rot')),
                    x=(sprite.attrgetter('x') + x),
                    y=(sprite.attrgetter('y') + y),
                    z=(sprite.attrgetter('z') - 0.1))

def create_ao(sprite, texture):
    """Create an ambient occlusion (AO) sprite."""
    return create_shadow(sprite, texture, x=0, y=0)

class MySprite(rabbyt.Sprite):
    z = rabbyt.anim_slot()

def create_aabb(lower_bound, upper_bound):
    aabb = b2AABB()
    aabb.lowerBound = lower_bound
    aabb.upperBound = upper_bound
    return aabb

def create_circle_body(world, position=(0., 0.), linear_velocity=(0., 0.),
                       angle=0., angular_velocity=0., radius=1., density=1.,
                       group_index=0, sensor=False):
    body_def = b2BodyDef()
    body_def.position = position
    body_def.angle = angle
    body = world.CreateBody(body_def)
    shape_def = b2CircleDef()
    shape_def.radius = radius
    shape_def.density = density
    shape_def.filter.groupIndex = group_index
    shape_def.isSensor = sensor
    body.CreateShape(shape_def)
    body.SetMassFromShapes()
    body.linearVelocity = linear_velocity
    body.angularVelocity = angular_velocity
    return body

def create_prismatic_joint(world, body_1, body_2, anchor=None, axis=None,
                           lower_translation=-1., upper_translation=1.,
                           max_motor_force=1., motor_speed=1.):
    if anchor is None:
        anchor = body_2.position
    if axis is None:
        axis = body_1.GetWorldVector(b2Vec2(0., 1.))
    joint_def = b2PrismaticJointDef()
    joint_def.Initialize(body_1, body_2, anchor, axis)
    joint_def.enableLimit = True
    joint_def.lowerTranslation = lower_translation
    joint_def.upperTranslation = upper_translation
    joint_def.enableMotor = True
    joint_def.maxMotorForce = max_motor_force
    joint_def.motorSpeed = motor_speed
    world.CreateJoint(joint_def)

def connect_sprite_to_body(sprite, body):
    sprite.x = lambda: body.position.x
    sprite.y = lambda: body.position.y
    sprite.rot = lambda: rad_to_deg(body.angle)

def disconnect_sprite_from_body(sprite, body):
    end_x = body.position.x + body.linearVelocity.x
    end_y = body.position.y + body.linearVelocity.y
    end_rot = rad_to_deg(body.angle + body.angularVelocity)
    sprite.x = rabbyt.lerp(end=end_x, dt=1., extend='extrapolate')
    sprite.y = rabbyt.lerp(end=end_y, dt=1., extend='extrapolate')
    sprite.rot = rabbyt.lerp(end=end_rot, dt=1., extend='extrapolate')

class Camera(object):
    def __init__(self):
        # Translation, in meters.
        self.position = b2Vec2(0., 0.)

        # Minimum width and height of screen, in meters.
        self.scale = 30.

        # Rotation, in degrees.
        self.angle = 0.

class Level(object):
    dt = 1. / 60.

    def __init__(self, debug=False):
        self.debug = debug
        self.time = 0.
        
        # Things coordinate bodies and sprites.
        self.things = []

        # The sprites to draw every frame.
        self.sprites = []

        self.stars_texture = pyglet.image.load('stars.png')
        self.stars_texture = pyglet.image.TileableTexture.create_for_image(self.stars_texture)

        self._init_world()
        self._init_circle_vertex_list()
        self.camera = Camera()

        self.player_ships = []
        self.challenge = None
        self._create_challenge()
        pyglet.clock.schedule_interval(self._create_challenge, 30.)

    def _create_challenge(self, dt=None):
        if self.challenge is not None:
            self.challenge.delete()
            self.challenge = None
        self.challenge = AsteroidField(level=self)

    def _init_world(self):
        aabb = create_aabb((-100., -100.), (100., 100.))
        self.world = b2World(aabb, (0., 0.), True)
        self.contact_listener = MyContactListener()
        self.world.SetContactListener(self.contact_listener)
        self.boundary_listener = MyBoundaryListener()
        self.world.SetBoundaryListener(self.boundary_listener)

    def _init_circle_vertex_list(self):
        self.circle_vertex_list = create_circle_vertex_list()

    def step(self):
        self.time += self.dt
        self.challenge.step()
        for thing in self.things:
            thing.step()
        self.world.Step(self.dt, 10, 10)

        contacts = list(self.contact_listener.contacts)
        self.contact_listener.contacts.clear()
        for thing_1, thing_2 in contacts:
            thing_1.collide(thing_2)
            thing_2.collide(thing_1)

        boundary_violators = list(self.boundary_listener.violators)
        self.boundary_listener.violators.clear()
        for thing in boundary_violators:
            thing.delete()

    def draw(self, width, height):
        glColor3f(1., 1., 1.)
        self.stars_texture.blit_tiled(0, 0, 0, width, height)
        glPushMatrix()
        glTranslatef(float(width // 2), float(height // 2), 0.)
        scale = float(min(width, height)) / self.camera.scale
        glScalef(scale, scale, scale)
        rabbyt.set_time(self.time)
        self.sprites.sort(key=attrgetter('z'))
        rabbyt.render_unsorted(self.sprites)
        if self.debug:
            glColor3f(0., 1., 0.)
            glDisable(GL_TEXTURE_2D)
            debug_draw(self.world)
        glPopMatrix()

class MyContactListener(b2ContactListener):
    def __init__(self):
        super(MyContactListener, self).__init__()
        self.contacts = set()

    def Add(self, point):
        thing_1 = point.shape1.GetBody().userData
        thing_2 = point.shape2.GetBody().userData
        self.contacts.add((thing_1, thing_2))

class MyBoundaryListener(b2BoundaryListener):
    def __init__(self):
        super(MyBoundaryListener, self).__init__()
        self.violators = set()

    def Violation(self, body):
        self.violators.add(body.userData)

class Thing(object):
    """A physical, visible thing.

    Things have a circular physics body and a sprite that moves and rotates
    with the body.

    For non-physical stuff, such as pure special effects, use sprites directly
    instead.
    """

    radius = 1.
    density = 1.
    texture = None
    scale = 1.
    fade_dt = 0.2
    sensor = False
    group_index = 0

    def __init__(self, level, position=(0., 0.), linear_velocity=(0., 0.),
                 angle=0., angular_velocity=0., z=0., group_index=0,
                 red=1., green=1., blue=1.):
        self.group_index = group_index
        self.deleted = False
        self.level = level
        self._init_body(position=position, linear_velocity=linear_velocity,
                        angle=angle, angular_velocity=angular_velocity)
        self._init_sprite(z=z, red=red, green=green, blue=blue)
        self.level.things.append(self)

    def _init_body(self, position=(0., 0.), linear_velocity=(0., 0.),
                   angle=0., angular_velocity=0.):
        self.body = create_circle_body(self.level.world,
                                       position=position,
                                       linear_velocity=linear_velocity,
                                       angle=angle,
                                       angular_velocity=angular_velocity,
                                       radius=self.radius,
                                       density=self.density,
                                       group_index=self.group_index,
                                       sensor=self.sensor)
        self.body.userData = self

    def _init_sprite(self, z=0., red=1., green=1., blue=1.):
        self.sprite = MySprite(texture=self.texture, scale=self.scale,
                               red=red, green=green, blue=blue, alpha=0., z=z)
        connect_sprite_to_body(self.sprite, self.body)
        self.fade_in()
        self.level.sprites.append(self.sprite)

    def delete(self):
        if not self.deleted:
            self.deleted = True
            self.level.things.remove(self)
            self.fade_away()
            self.level.world.DestroyBody(self.body)
            self.body = None

    def step(self):
        pass

    def fade_in(self):
        dt = self.fade_dt * (1. - self.sprite.alpha)
        self.sprite.alpha = rabbyt.lerp(end=1., dt=dt)

    def fade_out(self):
        dt = self.fade_dt * self.sprite.alpha
        self.sprite.alpha = rabbyt.lerp(end=0., dt=self.fade_dt)

    def fade_away(self):
        self.fade_out()
        disconnect_sprite_from_body(self.sprite, self.body)
        def remove_sprite(dt, sprite):
           self.level.sprites.remove(sprite)
        pyglet.clock.schedule_once(remove_sprite, self.fade_dt, self.sprite)
        self.sprite = None

    def collide(self, other):
        pass

class Challenge(object):
    """A challenge that the player encounters and must endure or overcome."""
    def __init__(self, level):
        self.level = level

    def delete(self):
        pass

    def step(self):
        pass

class AsteroidField(Challenge):
    """The player must navigate through an asteroid field."""

    def __init__(self, **kwargs):
        super(AsteroidField, self).__init__(**kwargs)
        self.asteroids = []

    def delete(self):
        for asteroid in self.asteroids:
            asteroid.delete()
        self.asteroids = []

    def step(self):
        self.asteroids = [a for a in self.asteroids if not a.deleted]
        targets = [s for s in self.level.player_ships if not s.deleted]
        if targets:
            while len(self.asteroids) < 10:
                target = random.choice(targets)
                asteroid = self.create_asteroid(target)
                self.asteroids.append(asteroid)

    def create_asteroid(self, target):
        position_angle = 2 * pi * random.random()
        distance = random.gauss(50., 1.)
        position = (self.level.camera.position +
                    distance * b2Vec2(cos(position_angle),
                                      sin(position_angle)))
        linear_velocity = target.body.position - position
        linear_velocity.Normalize()
        linear_velocity *= random.gauss(5., 1.)
        orientation_angle = 2 * pi * random.random()
        angular_velocity = random.gauss(0., 0.5)
        asteroid = Asteroid(level=self.level, position=position,
                            linear_velocity=linear_velocity,
                            angle=orientation_angle,
                            angular_velocity=angular_velocity)
        return asteroid

class Cannon(Thing):
    radius = 0.1

    def __init__(self, ship, **kwargs):
        super(Cannon, self).__init__(group_index=ship.group_index, **kwargs)
        self.ship = ship
        self.firing = False
        self.fire_time = self.level.time

class PlasmaCannon(Cannon):
    texture = 'plasma-cannon-ao.png'
    scale = 0.015
    recoil = 1.5
    cooldown_mean = 0.3
    cooldown_dev = 0.05
    muzzle_velocity = 30.

    def __init__(self, **kwargs):
        super(PlasmaCannon, self).__init__(**kwargs)
        self.cooldown = random.gauss(self.cooldown_mean, self.cooldown_dev)

    def step(self):
        if self.firing and self.fire_time + self.cooldown < self.level.time:
            # Spread the cooldown, so that the cannons are only synchronized
            # for the very first shots after a cease fire.
            self.fire_time = self.level.time
            self.cooldown = random.gauss(self.cooldown_mean, self.cooldown_dev)
            self.fire()

    def fire(self):
        # Don't add the ship's linear velocity to the shot's linear velocity.
        # If the ship is moving sideways, the shots would also move sideways.
        # It doesn't look good, and it doesn't feel good either. Space Invaders
        # was right.
        #
        # TODO: However, we may want to add the linear velocity component in
        # the cannon's direction, or adjust the linear velocity for scrolling.
        muzzle_velocity = b2Vec2(0., self.muzzle_velocity)
        linear_velocity = self.body.GetWorldVector(muzzle_velocity)
        shot = PlasmaShot(level=self.level, position=self.body.position,
                          linear_velocity=linear_velocity,
                          angle=self.body.angle, z=self.sprite.z,
                          group_index=self.group_index)
        recoil = self.recoil * self.body.GetWorldVector(b2Vec2(0., -1.))
        self.body.ApplyImpulse(recoil, self.body.position)

class MissileRamp(Cannon):
    pass

class Shot(Thing):
    pass

class PlasmaShot(Shot):
    texture = 'plasma-shot.png'
    scale = 0.015
    group_index = -1
    radius = 0.1
    sensor = True
    fade_dt = 0.1

    def collide(self, other):
        self.delete()

class Missile(Shot):
    pass

class Ship(Thing):
    thrust_force = 700.
    damping_force = 20.
    turn_torque = 200.
    damping_torque = 20.
    cannon_slots = [(-0.75, 1.), (0., 1.75), (0.75, 1.)]
    scale = 0.015
    fade_dt = 0.5

    def __init__(self, texture='ship-1-ao.png', **kwargs):
        self.texture = texture
        super(Ship, self).__init__(**kwargs)
        self.locking = False
        self.target = None
        self.thrust = b2Vec2(0., 0.)
        self.cannons = [None, None, None]
        for i in xrange(3):
            position = self.body.GetWorldPoint(self.cannon_slots[i])
            z = self.sprite.attrgetter('z') - 0.1
            self.cannons[i] = PlasmaCannon(level=self.level, ship=self,
                                           position=position,
                                           angle=self.body.angle, z=z)
            create_prismatic_joint(self.level.world, self.body,
                                   self.cannons[i].body, upper_translation=0.,
                                   max_motor_force=20., motor_speed=5.)
            self.angle = self.body.angle
        self.linear_velocity = b2Vec2(0., 0.)

    # TODO: Set self.linear_velocity from e.g. scrolling.
    def step(self):
        self._update_target()
        self._update_angle()
        self._apply_force()
        self._apply_torque()

    def _update_target(self):
        if self.locking:
            if self.target is not None:
                if self.target.body is None:
                    self.target = None
                else:
                    distance = ((self.body.position -
                                 self.target.body.position).Length() -
                                self.target.radius)
                    if distance >= 50.:
                        self.target = None
            if self.target is None:
                segment = b2Segment()
                segment.p1 = (self.body.position +
                              self.body.GetWorldVector(b2Vec2(0., 5.)))
                segment.p2 = (segment.p1 +
                              self.body.GetWorldVector(b2Vec2(0., 20.)))
                fraction, normal, shape = self.level.world.RaycastOne(segment,
                                                                      True,
                                                                      None)
                if shape is not None:
                    self.target = shape.GetBody().userData
        else:
            self.target = None

    def _update_angle(self):
        if self.target is None:
            self.angle = 0.
        else:
            offset = self.target.body.position - self.body.position
            self.angle = atan2(offset.y, offset.x) - pi / 2.

    def _apply_force(self):
        linear_velocity_error = self.linear_velocity - self.body.linearVelocity
        force = (self.thrust * self.thrust_force +
                 linear_velocity_error * self.damping_force)
        self.body.ApplyForce(force, self.body.position)

    def _apply_torque(self):
        angle_error = self.angle - self.body.angle
        while angle_error < -pi:
            angle_error += 2. * pi
        while angle_error >= pi:
            angle_error -= 2. * pi
        torque = (self.turn_torque * angle_error -
                  self.damping_torque * self.body.angularVelocity)
        self.body.ApplyTorque(torque)

class ShipControls(object):
    def __init__(self, level, ship):
        self.level = level
        self.ship = ship
        self.keys = set()

    def on_key_press(self, symbol, modifiers):
        if symbol == pyglet.window.key.ENTER:
           self.ship.locking = not self.ship.locking
        self.keys.add(symbol)
        self.update()

    def on_key_release(self, symbol, modifiers):
        self.keys.discard(symbol)
        self.update()

    def update(self):
        self._update_thrust()
        self._update_firing()

    def _update_thrust(self):
        left = float(pyglet.window.key.LEFT in self.keys)
        right = float(pyglet.window.key.RIGHT in self.keys)
        up = float(pyglet.window.key.UP in self.keys)
        down = float(pyglet.window.key.DOWN in self.keys)

        thrust = b2Vec2(right - left, up - down)
        thrust.Normalize()
        self.ship.thrust = thrust

    def _update_firing(self):
        for cannon in self.ship.cannons:
            cannon.firing = pyglet.window.key.SPACE in self.keys

class CameraControls(object):
    def __init__(self, level, camera):
        self.level = level
        self.camera = camera

    def on_key_press(self, symbol, modifiers):
        if symbol == pyglet.window.key.PLUS:
           self.camera.scale /= 1.5
        if symbol == pyglet.window.key.MINUS:
           self.camera.scale *= 1.5

    def on_key_release(self, symbol, modifiers):
        pass

class Asteroid(Thing):
    texture = 'asteroid-ao.png'
    density = 10.

    def __init__(self, group_index=ASTEROID_GROUP, **kwargs):
        self.radius = random.gauss(4.5, 0.2)
        self.scale = 0.0075 * self.radius
        self.power = self.radius ** 2
        red = random.gauss(0.95, 0.05)
        green = random.gauss(0.95, 0.05)
        blue = random.gauss(0.95, 0.05)
        super(Asteroid, self).__init__(group_index=group_index,
                                       red=red, green=green, blue=blue,
                                       **kwargs)

    def collide(self, other):
        if isinstance(other, Shot):
            self.power -= 1.
            if self.power <= 0.:
                self.delete()

class GameScreen(object):
    def __init__(self, window, debug=False, single=True):
        self.window = window
        self.level = Level(debug)
        if single:
            position_1 = position=(0., -10.)
        else:
            position_1 = position=(-10., -10.)
            position_2 = position=(10., -10.)
        ship_1 = Ship(level=self.level, position=position_1, z=2.,
                      group_index=PLAYER_1_GROUP)
        self.level.player_ships.append(ship_1)
        if not single:
            ship_2 = Ship(texture='ship-2-ao.png', level=self.level,
                          position=position_2, z=1.,
                          group_index=PLAYER_2_GROUP)
            self.level.player_ships.append(ship_2)
        self.controls = []
        self.controls.append(ShipControls(self.level,
                                          self.level.player_ships[0]))
        self.controls.append(CameraControls(self.level,
                                            self.level.camera))
        self.time = 0.
        pyglet.clock.schedule_interval(self.step, self.level.dt)

    def step(self, dt):
        self.time += dt
        while self.level.time + self.level.dt < self.time:
            self.level.step()

    def on_draw(self):
        self.window.clear()
        self.level.draw(self.window.width, self.window.height)

    def close(self):
        pyglet.clock.unschedule(self.step)

    def on_key_press(self, symbol, modifiers):
        for controls in self.controls:
            controls.on_key_press(symbol, modifiers)

    def on_key_release(self, symbol, modifiers):
        for controls in self.controls:
            controls.on_key_release(symbol, modifiers)
            
class MyWindow(pyglet.window.Window):
    def __init__(self, fps=False, debug=False, single=True, **kwargs):
        super(MyWindow, self).__init__(**kwargs)

        # Grab mouse and keyboard if we're in fullscreen mode.
        self.set_exclusive_mouse(self.fullscreen)
        self.set_exclusive_keyboard(self.fullscreen)

        # Initialize Rabbyt.
        rabbyt.set_default_attribs()

        # Clear to opaque black for opaque screenshots.
        glClearColor(0., 0., 0., 1.)

        # Create FPS display.
        self.fps_display = pyglet.clock.ClockDisplay() if fps else None

        # Most window calls are delegated to a screen.
        self.my_screen = GameScreen(self, debug=debug, single=single)

    def on_draw(self):
        # Delegate to screen.
        self.my_screen.on_draw()

        # Display FPS counter.
        if self.fps_display is not None:
            self.fps_display.draw()

    def on_key_press(self, symbol, modifiers):
        if symbol == pyglet.window.key.ESCAPE:
            # Close window.
            self.on_close()
        elif symbol == pyglet.window.key.F11:
            # Toggle fullscreen mode.
            self.set_fullscreen(not self.fullscreen)
            self.set_exclusive_mouse(self.fullscreen)
            self.set_exclusive_keyboard(self.fullscreen)
        elif symbol == pyglet.window.key.F12:
            # Save screenshot.
            color_buffer = pyglet.image.get_buffer_manager().get_color_buffer()
            color_buffer.save('burst-screenshot.png')
        else:
            # Delegate to screen.
            self.my_screen.on_key_press(symbol, modifiers)

    def on_key_release(self, symbol, modifiers):
        # Delegate to screen.
        self.my_screen.on_key_release(symbol, modifiers)

def help():
    print """
Usage: burst [OPTION]...

Options:
  -1            Enable single-player mode (default).
  -2            Enable two-player mode.
  --debug       Enable debug graphics.
  --fps         Enable FPS counter.
  --fullscreen  Enable fullscreen mode (default).
  -h, --help    Print this helpful text and exit.
  --test        Run tests and exit.
  -v            Enable verbose output (use with --test).
  --windowed    Enable windowed mode.

Controls:
  Arrows        Fly.
  Space         Fire.
  Enter         Toggle target locking.

  Escape        Exit.
  F11           Toggle fullscreen mode.
  F12           Save a screenshot.
""".strip()

def test():
    import doctest
    doctest.testmod()

def main():
    args = sys.argv[1:]
    if '-h' in args or '--help' in args:
        return help()
    if '--test' in args:
        return test()
    debug = '--debug' in args
    fps = '--fps' in args
    single = True
    fullscreen = True
    for arg in args:
        if arg == '-1':
            single = True
        if arg == '-2':
            single = False
        if arg == '--fullscreen':
            fullscreen = True
        if arg == '--windowed':
            fullscreen = False
    two = '-2' in args or '--two' in args
    window = MyWindow(debug=debug, fps=fps, fullscreen=fullscreen,
                      single=single)
    pyglet.app.run()

if __name__ == '__main__':
    main()
