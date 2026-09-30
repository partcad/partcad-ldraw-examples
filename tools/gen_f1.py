#!/usr/bin/env python3
"""Generate f1.assy, f1/car.assy and the pieces under f1/ - a Formula 1 car in LEGO Technic.

The car is a Power Functions one, and drives, steers and is driven the way a
real one would be:

  * an XL motor on a rear subframe turns a 12-tooth pinion, which drives the
    crown of a differential between two half axles;
  * the subframe swings on a pivot across the chassis and is held up by two
    shock absorbers under towers, so the whole rear axle is sprung;
  * the front wheels are on double wishbones, a kingpin at the end of each pair
    and a knuckle turning on it, with a shock absorber from each upper wishbone
    to a crossbeam;
  * a servo stands behind the front axle, output down, and pushes a track rod
    across between the two knuckles;
  * the battery box sits across the car between the side frames, pinned into
    them by the holes in both of its ends; the IR receiver is the airbox over
    the motor; the IR remote control stands beside the car.

How it is written, and why

Every part is designed at the pose it should have, in a Y-up frame (X to the
car's right, Y up, Z forward, millimetres - the parts' own LDraw-derived
frame). Then, part by part, the generator looks for a port of the new part and a
port of the part it is being put on that are at the same point, facing each
other, and have interfaces that mate - a pin in a pin hole, an axle in an axle
hole or a round one, a stud in an anti-stud. That pair becomes the part's
'connect:', with whatever 'turnZ' or 'moveZ' the interfaces allow, and the pose
PartCAD will compute from it - the target's port, turned around, offset by the
parameters, pulled back by the part's own port - is computed here with the same
rule and has to come out exactly where the part was designed to be. A part for
which no such pair exists is an error, not a coordinate: the design is changed
until it has one.

That is also why the ports come from partcad-ldraw's own index and nowhere else:
a joint through a port the package does not serve is not a joint.

Parts that are round about the axle they sit on - bushes, wheels, the pinion,
the axles themselves - take whatever roll the axle gives them, since an axle
hole cannot take a turn and nothing about them depends on it. A part whose roll
does matter (a cross block on an axle) is made to land right by turning the
axle, which went into a round hole and can take the turn.

The car is cut into pieces the way it would be built on a bench, several pairs
of hands at once, each piece a block that is finished before it is fitted:

  * the tub - the two side frames, the battery box they are pinned onto, the
    pivot the drivetrain swings on and the airbox over the motor, each of those
    four a piece of its own;
  * the front end - the front frame, both front corners, the steering, the nose
    and the front wing, all but the frame pieces of their own, and the frame
    the one the others are hung on;
  * the drivetrain - the motor unit, a piece, and the differential, half axles,
    wheels and shocks around it;
  * the rear wing, and the sidepod, which is the one piece used twice.

A piece is placed by its first part and everything else in it hangs off that.
Where two pieces meet, the joint is written in the lowest piece that holds both,
through the ports each of them exports: a piece's 'interfaces:' block maps
every port a joint outside it uses, through as many levels of pieces as the
port is deep, so a part is never reached into from outside the piece that owns
it. Whatever joins two pieces and belongs to neither - the pins between the
knuckles and the track rod, the tops of the front shocks - sits in the piece
that holds both. The remote control is not part of the car: f1.assy is the car
and the remote beside it, placed by coordinates because nothing joins a handset
to the car it drives.

That split is also what the interference test is run on: each piece is tested
on its own, in parallel with the others, and what is left for the car is the
pairs that straddle two pieces.

The car's origin is its first beam, the left side frame's lower rail, so
f1/car.assy is placed at that beam's own pose turned +90 degrees about X: that
takes this Y-up frame into PartCAD's Z-up world with the nose towards -Y, so
'front' shows the nose and 'right' the car's right side, and the ground at
z = 0. partcad-ldraw stands each part up with that same turn, which is why the
design frame is the parts' LDraw frame and not the frame they are served in:
see UPRIGHT.

Usage, from the repository root, with a checkout of partcad-ldraw beside this
one (or LDRAW_INDEX pointing at its parts-index.zip):

    python3 tools/gen_f1.py          # writes f1.assy, f1/*.assy and the f1 block of partcad.yaml
    python3 tools/gen_f1.py --check  # only re-derives every joint and reports
"""

import json
import math
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.environ.get("LDRAW_INDEX") or os.path.join(os.path.dirname(ROOT), "partcad-ldraw", "parts-index.zip")

LEGO = "//pub/universe/lego"

# ---------------------------------------------------------------------------
# Rigid transforms, as 4 x 4 row-major lists. Location(t, axis, angle) is what
# PartCAD means by [t, axis, angle]: a turn about 'axis' through the origin,
# then the translation.


def ident():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def inv(m):
    r = [[m[j][i] for j in range(3)] for i in range(3)]
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]], [0.0, 0.0, 0.0, 1.0]]


def loc(t=(0, 0, 0), axis=(0, 0, 1), angle=0.0):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z)
    m = ident()
    if n > 0 and angle % 360:
        x, y, z = x / n, y / n, z / n
        th = math.radians(angle)
        c, s = math.cos(th), math.sin(th)
        k = 1 - c
        m = [
            [c + x * x * k, x * y * k - z * s, x * z * k + y * s, 0.0],
            [y * x * k + z * s, c + y * y * k, y * z * k - x * s, 0.0],
            [z * x * k - y * s, z * y * k + x * s, c + z * z * k, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    for i in range(3):
        m[i][3] = float(t[i])
    return m


def frame(origin, x=None, y=None, z=None):
    """A pose from where two of the part's own axes should point."""

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    if x is None:
        x = cross(y, z)
    if y is None:
        y = cross(z, x)
    if z is None:
        z = cross(x, y)
    m = ident()
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = x[i], y[i], z[i], float(origin[i])
    return m


def close(a, b, tol=1e-3):
    return all(abs(p - q) <= tol for p, q in zip(a, b))


def same(m, n, tol=1e-3):
    return all(close(a, b, tol) for a, b in zip(m, n))


# PartCAD's mate: the target's port, turned half a turn about (1, 1, 0) so
# that it faces the other way, then the parameters, then the source's port
# undone. See 'handle_node' in partcad's assembly_factory_assy.py.
TURN_AROUND = loc((0, 0, 0), (0.71, 0.71, 0), 180)

PARAMS = {  # what a connection may set, per interface - partcad-ldraw's partcad.yaml
    "stud": ("turnZ",),
    "anti-stud": ("turnZ",),
    "technic-pin-hole": ("turnZ", "moveZ"),
    "technic-pin": ("turnZ",),
    "technic-axle": ("moveZ",),
    "technic-axle-hole": ("moveZ",),
}
MATES = {
    frozenset(p)
    for p in (
        ("stud", "anti-stud"),
        ("technic-pin", "technic-pin-hole"),
        ("technic-axle", "technic-axle-hole"),
        ("technic-axle", "technic-pin-hole"),
    )
}
SHORT = {
    "technic-pin-hole": "hole",
    "technic-axle-hole": "axlehole",
    "technic-pin": "pin",
    "technic-axle": "axle",
    "stud": "stud",
    "anti-stud": "anti",
}


class Index:
    """The parts, their categories and their ports, from partcad-ldraw's index."""

    def __init__(self, path):
        z = zipfile.ZipFile(path)
        self.category, self.entry = {}, {}
        for member in z.namelist():
            if member.startswith("c/"):
                for pid, entry in json.loads(z.read(member)).items():
                    if pid not in self.category:
                        self.category[pid] = member[2:-5]
                        self.entry[pid] = entry

    def ref(self, pid):
        return "%s/ldraw/%s:%s" % (LEGO, self.category[pid], pid)

    def desc(self, pid):
        return self.entry[pid][0]

    def ports(self, pid):
        for iface, instances in sorted((self.entry[pid][3] or {}).items()):
            for inst, (t, a, ang) in sorted(instances.items()):
                yield iface.split(":")[1], inst, lying(loc(t, a, ang))

    def port(self, pid, iface, inst):
        t, a, ang = self.entry[pid][3]["%s:%s" % (LEGO, iface)][inst]
        return lying(loc(t, a, ang))


# partcad-ldraw serves every part stood up in Z: its mesh and its ports are
# LDraw's, turned this quarter about X on the way out. The car is designed in
# the frame before that turn, where a part is one negation away from the .dat
# it is read off, so a port read from the index is turned back into it - and a
# pose written out for PartCAD is given the turn back (see 'placement').
#
# Nothing in between needs to know. A joint's 'turnZ' and 'moveZ' are measured
# between two ports, and turning both parts and both ports by the same amount
# leaves every one of them as it was.
UPRIGHT = loc((0, 0, 0), (1, 0, 0), 90)


def lying(port):
    """A port as served, in the frame of the part before it was stood up."""
    return mul(inv(UPRIGHT), port)


class Node:
    def __init__(self, module, name, pid, M, joint=None, note=None):
        self.module, self.name, self.pid, self.M, self.joint, self.note = module, name, pid, M, joint, note


def _offset(A, M, Ps):
    """(turn, move) with A . Rz(turn) . Tz(move) . Ps^-1 == M, or None."""
    off = mul(mul(inv(A), M), Ps)
    if abs(off[2][2] - 1) > 1e-4 or abs(off[0][2]) > 1e-4 or abs(off[1][2]) > 1e-4:
        return None
    if abs(off[0][3]) > 1e-3 or abs(off[1][3]) > 1e-3:
        return None
    turn = round(math.degrees(math.atan2(off[1][0], off[0][0])), 3)
    if abs(turn - round(turn)) < 1e-3:
        turn = float(round(turn))
    move = round(off[2][3], 3)
    return (0.0 if turn == 0 else turn), (0.0 if move == 0 else move)


class Scene:
    def __init__(self, index):
        self.ix = index
        self.nodes = {}
        self.order = []

    def get(self, module, name):
        return self.nodes[(module, name)]

    def _add(self, n):
        assert (n.module, n.name) not in self.nodes, (n.module, n.name)
        self.nodes[(n.module, n.name)] = n
        self.order.append(n)
        return n

    def first(self, module, name, pid, M):
        return self._add(Node(module, name, pid, M))

    def placed(self, module, name, pid, M, note):
        return self._add(Node(module, name, pid, M, "location", note))

    def world(self, node, iface, inst):
        return mul(node.M, self.ix.port(node.pid, iface, inst))

    def mate(self, pid, wiface, winst, target, tiface, tinst, turn, move):
        A = mul(self.world(target, tiface, tinst), TURN_AROUND)
        off = mul(loc((0, 0, move)), loc((0, 0, 0), (0, 0, 1), turn))
        return mul(mul(A, off), inv(self.ix.port(pid, wiface, winst)))

    def put(self, module, name, pid, M0, to, round_part=False):
        """Place 'pid' at M0, joined to one of 'to' through two ports that meet there."""
        targets = to if isinstance(to, (list, tuple)) else [to]
        found, rolled = [], []
        for target in targets:
            tports = list(self.ix.ports(target.pid))
            for wiface, winst, Pw in self.ix.ports(pid):
                W = mul(M0, Pw)
                wp = [W[i][3] for i in range(3)]
                wz = [W[i][2] for i in range(3)]
                for tiface, tinst, Pt in tports:
                    if frozenset((wiface, tiface)) not in MATES:
                        continue
                    T = mul(target.M, Pt)
                    if not close(wz, [-T[i][2] for i in range(3)], 1e-4):
                        continue
                    d = [wp[i] - T[i][3] for i in range(3)]
                    along = sum(d[i] * wz[i] for i in range(3))
                    if not close([d[i] - along * wz[i] for i in range(3)], (0, 0, 0)):
                        continue
                    axle = "technic-axle" in (wiface, tiface)
                    if abs(along) > 1e-3 and not axle:
                        continue  # only an axle lies along a hole; a pin stops at its collar
                    sol = _offset(mul(T, TURN_AROUND), M0, Pw)
                    if sol is None:
                        continue
                    turn, move = sol
                    if move and "moveZ" not in PARAMS[wiface] + PARAMS[tiface]:
                        continue
                    if turn and "turnZ" not in PARAMS[wiface] + PARAMS[tiface]:
                        if not round_part:
                            rolled.append((target, wiface, winst, tiface, tinst, move))
                            continue
                        turn = 0.0  # round about this axis: the axle decides the roll
                    found.append(
                        (
                            (move != 0, turn != 0, abs(move), abs(turn)),
                            target.name,
                            wiface,
                            winst,
                            tiface,
                            tinst,
                            target,
                            turn,
                            move,
                        )
                    )
        if not found and rolled:
            return self._roll_axle(module, name, pid, M0, rolled[0])
        if not found:
            raise ValueError(
                "%s/%s (%s): no port of it meets a port of %s where it was designed to be"
                % (module, name, pid, [t.name for t in targets])
            )
        found.sort(key=lambda c: c[:6])
        _, _, wiface, winst, tiface, tinst, target, turn, move = found[0]
        M = self.mate(pid, wiface, winst, target, tiface, tinst, turn, move)
        if not same(M, M0):
            # only a round part may differ, and only by a turn about the joint
            assert round_part and close([r[3] for r in M], [r[3] for r in M0]), (module, name)
        joint = dict(wiface=wiface, winst=winst, target=target, tiface=tiface, tinst=tinst, turn=turn, move=move)
        return self._add(Node(module, name, pid, M, joint))

    def _roll_axle(self, module, name, pid, M0, rolled):
        """Turn the axle 'rolled' names so that 'pid' lands at M0 on it."""
        target, wiface, winst, tiface, tinst, move = rolled
        if any(isinstance(n.joint, dict) and n.joint["target"] is target for n in self.order):
            raise ValueError("%s/%s: lands rolled on %s, which already carries parts" % (module, name, target.name))
        got = self.mate(pid, wiface, winst, target, tiface, tinst, 0.0, move)
        want = mul(mul(M0, inv(got)), target.M)
        j = target.joint
        A = mul(self.world(j["target"], j["tiface"], j["tinst"]), TURN_AROUND)
        sol = _offset(A, want, self.ix.port(target.pid, j["wiface"], j["winst"]))
        if sol is None or "turnZ" not in PARAMS[j["wiface"]] + PARAMS[j["tiface"]]:
            raise ValueError("%s/%s: lands rolled on %s, which cannot turn" % (module, name, target.name))
        j["turn"], j["move"] = sol
        target.M = self.mate(target.pid, j["wiface"], j["winst"], j["target"], j["tiface"], j["tinst"], *sol)
        return self.put(module, name, pid, M0, [target])


# ===========================================================================
# The design

S = None
X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)


def neg(v):
    return tuple(-c for c in v)


def side(s):
    return "r" if s > 0 else "l"


PIN = "3673"  # Technic Pin: every joint that turns
FPIN = "2780"  # Technic Pin with Friction: every joint that holds
BEAM = {3: "32523", 5: "32316", 7: "32524", 9: "40490", 11: "32525", 13: "41239", 15: "32278"}
AXLE = {2: "3704", 3: "4519", 4: "3705", 9: "60485", 12: "3708"}
BUSH = "3713"
SHOCK = "76320-f2"  # Shock Absorber 10L Damped, compressed: its eyes are 6 studs apart
CROSS_BLOCK = "6536"  # Cross Block 1 x 2 (Axle/Pin): an axle one way, a pin hole the other


def beam(mod, name, n, center, long, holes, to):
    return S.put(mod, name, BEAM[n], frame(center, z=long, y=holes), to)


def pin(mod, name, collar, into, to, pid=FPIN):
    """A pin with its collar at 'collar', its 'right' half going the way 'into' points."""
    perp = Y if abs(into[1]) < 0.9 else X
    return S.put(mod, name, pid, frame(collar, x=into, y=perp), to)


def axle(mod, name, n, center, along, to):
    perp = Y if abs(along[1]) < 0.9 else X
    return S.put(mod, name, AXLE[n], frame(center, x=along, y=perp), to, round_part=True)


def bush(mod, name, center, along, to):
    perp = Y if abs(along[1]) < 0.9 else X
    return S.put(mod, name, BUSH, frame(center, z=along, y=perp), to, round_part=True)


def block(mod, name, center, axle_along, pin_side, to):
    """A cross block: its axle hole along 'axle_along', its pin hole 8 mm towards 'pin_side'."""
    return S.put(mod, name, CROSS_BLOCK, frame(center, x=axle_along, y=neg(pin_side)), to)


# Where things are. The rear axle is at z = 0, the front one at ZW.
YF1, YF2 = 40.0, 56.0  # the side frames' two rails, and the rear axle's height
ZP = 80.0  # the pivot the drivetrain swings on
ZB = 136.0  # the battery box
ZW = 280.0  # the front axle, and the plane the wishbones lie in
ZK = ZW + 8  # the kingpins
YL, YU, YK = 16.0, 32.0, 24.0  # lower / upper wishbone, knuckle
XI, XO, XK = 16.0, 48.0, 56.0  # wishbone inner pivot, outer end, kingpin
ZN = 304.0  # the nose

# Where the pieces sit. A module is a path: 'tub/battery' is the battery,
# pre-assembled on its own and then fitted into the tub, which is itself built
# before it goes into the car. The empty path is the car.
TUB, FRONT, DRIVE = "tub", "front-end", "drivetrain"
SIDE_L, SIDE_R = TUB + "/side-frame-left", TUB + "/side-frame-right"
BATTERY, AIRBOX = TUB + "/battery", TUB + "/airbox"
FRAME, STEERING = FRONT + "/front-frame", FRONT + "/steering"
NOSE, FRONT_WING = FRONT + "/nose", FRONT + "/front-wing"
MOTOR = DRIVE + "/motor-unit"
REAR_WING = "rear-wing"


def corner_of(s):
    return FRONT + "/front-" + ("right" if s > 0 else "left")


def side_frame(s):
    return SIDE_R if s > 0 else SIDE_L


def build_side_frame(s, onto):
    """A side frame: the two rails, the post at the back and the shock tower over it.

    The left one is where the car starts, and says nothing; the right one goes
    onto the battery box's pins, which is how it is put on in the hand.
    """
    m = side_frame(s)
    if onto is None:
        lo = S.first(m, "rail-lo", BEAM[15], frame((s * 48, YF1, ZB), z=Z, y=X))
    else:
        lo = beam(m, "rail-lo", 15, (s * 48, YF1, ZB), Z, X, onto)
    post = beam(m, "post", 7, (s * 40, 64, 88), Y, X, pin(m, "pin-post-lo", (s * 44, YF1, 88), neg((s, 0, 0)), lo))
    beam(m, "rail-up", 15, (s * 48, YF2, ZB), Z, X, pin(m, "pin-post-up", (s * 44, YF2, 88), (s, 0, 0), post))
    beam(m, "tower", 13, (s * 48, 88, 40), Z, X, pin(m, "pin-post-tower", (s * 44, 88, 88), (s, 0, 0), post))


def build_battery():
    """The battery box and the eight pins in its end holes; four of them go into each side frame."""
    m = BATTERY
    p = pin(m, "pin-l-lo-front", (-44, YF1, ZB - 16), X, S.get(SIDE_L, "rail-lo"))
    box = S.put(m, "battery-box", "58119", frame((0, 48, ZB), x=X, y=neg(Z)), p)
    for s in (-1, 1):
        for y, lvl in ((YF1, "lo"), (YF2, "up")):
            for z, end in ((ZB - 16, "front"), (ZB + 16, "back")):
                nm = "pin-%s-%s-%s" % (side(s), lvl, end)
                if nm != "pin-l-lo-front":
                    pin(m, nm, (s * 44, y, z), (s, 0, 0), box)


def build_tub():
    build_side_frame(-1, None)
    build_battery()
    build_side_frame(1, S.get(BATTERY, "pin-r-lo-front"))
    # the pivot the drivetrain swings on runs right across, through both frames
    pv = S.put(TUB, "pivot", AXLE[12], frame((0, YF1, ZP), x=X, y=Y), S.get(SIDE_L, "rail-lo"), round_part=True)
    for nm, x in (("pivot-bush-l", -40), ("pivot-bush-r1", 32), ("pivot-bush-r2", 40)):
        bush(TUB, nm, (x, YF1, ZP), X, pv)
    # the airbox: a crossbeam carried by the two posts through a cross block
    # each, and the IR receiver pinned to it
    m = AIRBOX
    ax = axle(m, "axle-l", 2, (-36, 80, 88), X, S.get(SIDE_L, "post"))
    blk = block(m, "block-l", (-32, 80, 88), neg(X), neg(Y), ax)
    cb = beam(m, "beam", 9, (0, 72, 80), X, Z, pin(m, "pin-beam-l", (-32, 72, 84), neg(Z), blk))
    blk = block(m, "block-r", (32, 80, 88), X, neg(Y), pin(m, "pin-beam-r", (32, 72, 84), Z, cb))
    axle(m, "axle-r", 2, (36, 80, 88), X, blk)
    rx = S.put(
        m, "ir-receiver", "58123", frame((0, 76, 60), z=neg(Z), y=Y), pin(m, "pin-rx-1", (-8, 72, 76), neg(Z), cb)
    )
    pin(m, "pin-rx-2", (8, 72, 76), Z, rx)


def build_front_frame():
    """The front of the car's structure, built on its own and pinned to both upper rails.

    From the left upper rail forward to the left bulkhead, across the car on the
    shock crossbeam, and back from the right bulkhead to the right rail: one
    rigid frame, so that it can be built and handled before it goes on the tub.
    """
    m = FRAME
    order = []
    nu = beam(
        m, "nose-up-l", 13, (-40, YF2, 224), Z, X, pin(m, "pin-nose-1-l", (-44, YF2, 176), X, S.get(SIDE_L, "rail-up"))
    )
    order.append((-1, nu))
    for s, nose_up in ((-1, nu), (1, None)):
        if s > 0:
            # the right side is reached across the shock crossbeam
            bulk_r = beam(
                m,
                "bulk-r",
                9,
                (XI, 48, ZW - 8),
                Y,
                Z,
                pin(m, "pin-shock-beam-r", (XI, 80, ZW - 4), neg(Z), S.get(m, "shock-beam")),
            )
            cb = block(
                m, "bulk-block-r", (16, YF2, 264), X, neg(Y), pin(m, "pin-bulk-r", (XI, 48, 268), neg(Z), bulk_r)
            )
            ax = axle(m, "bulk-axle-r", 4, (28, YF2, 264), X, cb)
            nose_up = beam(m, "nose-up-r", 13, (40, YF2, 224), Z, X, ax)
        pin(m, "pin-nose-%s-%s" % (2, side(s)), (s * 44, YF2, 184), (s, 0, 0), nose_up)
        if s > 0:
            pin(m, "pin-nose-1-r", (44, YF2, 176), X, nose_up)
        link = beam(
            m,
            "nose-link-" + side(s),
            5,
            (s * 32, 40, 240),
            Y,
            X,
            pin(m, "pin-link-up-" + side(s), (s * 36, YF2, 240), neg((s, 0, 0)), nose_up),
        )
        nl = beam(
            m,
            "nose-lo-" + side(s),
            5,
            (s * 40, 32, 248),
            Z,
            X,
            pin(m, "pin-link-lo-" + side(s), (s * 36, 32, 240), (s, 0, 0), link),
        )
        if s < 0:
            ax = axle(m, "bulk-axle-l", 4, (-28, YF2, 264), X, nose_up)
            cb = block(m, "bulk-block-l", (-16, YF2, 264), neg(X), neg(Y), ax)
            bulk_l = beam(m, "bulk-l", 9, (-XI, 48, ZW - 8), Y, Z, pin(m, "pin-bulk-l", (-XI, 48, 268), Z, cb))
        bush(m, "bulk-bush-%s-1" % side(s), (s * 24, YF2, 264), X, ax)
        bush(m, "bulk-bush-%s-2" % side(s), (s * 32, YF2, 264), X, ax)
        ax2 = axle(m, "servo-axle-" + side(s), 4, (s * 28, 32, 256), X, nl)
        S.put(m, "servo-rail-" + side(s), BEAM[3], frame((s * 16, 32, 256), z=Z, y=X), ax2)
        bush(m, "servo-bush-%s-1" % side(s), (s * 24, 32, 256), X, ax2)
        bush(m, "servo-bush-%s-2" % side(s), (s * 32, 32, 256), X, ax2)
        beam(
            m,
            "nose-ext-" + side(s),
            9,
            (s * 48, YF2, 288),
            Z,
            X,
            pin(m, "pin-ext-1-" + side(s), (s * 44, YF2, 256), (s, 0, 0), nose_up),
        )
        pin(m, "pin-ext-2-" + side(s), (s * 44, YF2, 272), (s, 0, 0), nose_up)
        if s < 0:
            # the crossbeam the front shocks hang from, across to the right
            beam(m, "shock-beam", 11, (0, 80, ZW), X, Z, pin(m, "pin-shock-beam-l", (-XI, 80, ZW - 4), Z, bulk_l))


def build_corner(s):
    m = corner_of(s)
    bulk = S.get(FRAME, "bulk-" + side(s))
    lower = beam(
        m,
        "wishbone-lower",
        5,
        (s * (XI + XO) / 2, YL, ZW),
        X,
        Z,
        pin(m, "pin-lower-in", (s * XI, YL, ZW - 4), Z, bulk, pid=PIN),
    )
    bl = S.put(
        m,
        "kingpin-lower",
        CROSS_BLOCK,
        frame((s * XK, YL, ZK), y=(s, 0, 0), z=Z),
        pin(m, "pin-lower-out", (s * XO, YL, ZW + 4), neg(Z), lower, pid=PIN),
    )
    kp = axle(m, "kingpin", 3, (s * XK, YK, ZK), Y, bl)
    bu = S.put(m, "kingpin-upper", CROSS_BLOCK, frame((s * XK, YU, ZK), y=(s, 0, 0), z=Z), kp)
    upper = beam(
        m,
        "wishbone-upper",
        5,
        (s * (XI + XO) / 2, YU, ZW),
        X,
        Z,
        pin(m, "pin-upper-out", (s * XO, YU, ZW + 4), Z, bu, pid=PIN),
    )
    pin(m, "pin-upper-in", (s * XI, YU, ZW - 4), neg(Z), upper, pid=PIN)
    knuckle = S.put(m, "knuckle", "32557", frame((s * XK, YK, ZK), x=Y, y=Z), kp)
    stub = axle(m, "stub-axle", 4, (s * (XK + 12), 28, ZW), (s, 0, 0), knuckle)
    bush(m, "bush", (s * (XK + 8), 28, ZW), (s, 0, 0), stub)
    S.put(m, "wheel", "41896c01", frame((s * (XK + 20), 28, ZW), z=(s, 0, 0), y=Y), stub, round_part=True)
    S.put(
        m,
        "shock",
        SHOCK,
        frame((s * 24, 80, ZW + 8), z=Z, y=Y),
        pin(m, "pin-shock", (s * 24, YU, ZW + 4), neg(Z), upper, pid=PIN),
    )


def build_steering():
    m = STEERING
    servo = S.put(
        m,
        "servo",
        "99498",
        frame((0, 28, 264), z=Y, y=neg(Z)),
        pin(m, "pin-servo-1", (12, 32, 248), neg(X), S.get(FRAME, "servo-rail-r")),
    )
    pin(m, "pin-servo-2", (12, 32, 264), X, servo)
    pin(m, "pin-servo-3", (-12, 32, 248), neg(X), servo)
    pin(m, "pin-servo-4", (-12, 32, 264), neg(X), servo)
    out = axle(m, "output", 2, (0, 28, 264), Y, servo)
    arm = S.put(m, "arm", "11478", frame((0, 26, 280), z=Z, y=Y), out)
    tip = axle(m, "arm-tip", 2, (0, 32, 296), Y, arm)
    beam(m, "track-rod", 15, (0, 32, 296), X, Y, tip)


def build_nose():
    m = NOSE
    fa = S.put(m, "axle", AXLE[12], frame((0, YF2, ZN), x=X, y=Y), S.get(FRAME, "nose-ext-l"), round_part=True)
    blocks = [block(m, "block-" + side(s), (s * 16, YF2, ZN), X, neg(Y), fa) for s in (-1, 1)]
    nb = beam(m, "beam", 9, (0, 48, ZN + 8), X, Z, pin(m, "pin-beam-l", (-16, 48, ZN + 4), Z, blocks[0]))
    pin(m, "pin-beam-r", (16, 48, ZN + 4), neg(Z), nb)
    # a pair of long fairings, upside down so that they slope to the tip
    for s, pid in ((1, "64681"), (-1, "64393")):
        cone = S.put(
            m,
            "cone-" + side(s),
            pid,
            frame((s * 8, 48, ZN + 16), z=Z, y=neg(Y)),
            pin(m, "pin-cone-%s-1" % side(s), (s * 8, 48, ZN + 12), Z, nb),
        )
        pin(m, "pin-cone-%s-2" % side(s), (s * 16, 48, ZN + 12), neg(Z), cone)


def build_front_wing():
    m = FRONT_WING
    nb = S.get(NOSE, "beam")
    pl = beam(m, "pylon-l", 5, (-24, 32, ZN + 16), Y, Z, pin(m, "pin-pylon-l", (-24, 48, ZN + 12), Z, nb))
    lo = beam(m, "slat-lo", 15, (0, 16, ZN + 24), X, Z, pin(m, "pin-slat-lo-l", (-24, 16, ZN + 20), Z, pl))
    beam(m, "slat-hi", 15, (0, 24, ZN + 24), X, Z, pin(m, "pin-slat-hi-l", (-24, 24, ZN + 20), Z, pl))
    pr = beam(m, "pylon-r", 5, (24, 32, ZN + 16), Y, Z, pin(m, "pin-slat-lo-r", (24, 16, ZN + 20), neg(Z), lo))
    pin(m, "pin-slat-hi-r", (24, 24, ZN + 20), Z, pr)
    pin(m, "pin-pylon-r", (24, 48, ZN + 12), neg(Z), pr)
    for s in (-1, 1):
        ep = beam(
            m,
            "endplate-" + side(s),
            3,
            (s * 56, 24, ZN + 32),
            Y,
            Z,
            pin(m, "pin-endplate-%s-lo" % side(s), (s * 56, 16, ZN + 28), Z, lo),
        )
        pin(m, "pin-endplate-%s-hi" % side(s), (s * 56, 24, ZN + 28), neg(Z), ep)


def build_front_end():
    build_front_frame()
    build_steering()
    build_corner(1)
    build_corner(-1)
    # what joins two of its pieces and belongs to neither: the tops of the
    # front shocks, and the knuckles' pins into the track rod
    for s in (-1, 1):
        pin(FRONT, "pin-shock-top-" + side(s), (s * 24, 80, ZW + 4), Z, S.get(FRAME, "shock-beam"), pid=PIN)
    for s in (-1, 1):
        pin(FRONT, "pin-track-rod-" + side(s), (s * XK, 28, 296), neg(Y), S.get(STEERING, "track-rod"), pid=PIN)
    build_nose()
    build_front_wing()


def build_drivetrain():
    """The rear subframe: a motor unit built on its own, then the beams, axles and wheels around it."""
    m = DRIVE
    inl = beam(m, "inner-l", 11, (-32, YF1, 40), Z, X, S.get(TUB, "pivot"))
    u = MOTOR
    # the motor, 8 mm left of centre so that its pinion meets the crown
    motor = S.put(
        u, "xl-motor", "58121", frame((-8, YF1, 28), x=X, y=Y), pin(u, "pin-motor-l1", (-28, YF1, 32), X, inl)
    )
    pin(u, "pin-motor-l2", (-28, YF1, 72), X, motor)
    sp = beam(u, "spacer", 7, (16, YF1, 56), Z, X, pin(u, "pin-motor-r1", (12, YF1, 32), X, motor))
    pin(u, "pin-motor-r2", (12, YF1, 72), X, motor)
    beam(u, "bracket", 5, (-8, YF1, 24), Y, Z, pin(u, "pin-bracket-1", (-8, 48, 28), neg(Z), motor))
    pin(u, "pin-bracket-2", (-8, 32, 28), neg(Z), motor)
    shaft = axle(u, "pinion-shaft", 3, (-8, YF1, 24), Z, motor)
    S.put(u, "pinion", "32270", frame((-8, YF1, 16), z=Z, y=Y), shaft, round_part=True)
    spin = pin(u, "pin-spacer-1", (20, YF1, 40), X, sp)
    pin(u, "pin-spacer-2", (20, YF1, 64), X, sp)
    inr = beam(m, "inner-r", 11, (24, YF1, 40), Z, X, spin)
    right = axle(m, "half-axle-r", 9, (40, YF1, 0), X, inr)
    left = axle(m, "half-axle-l", 9, (-40, YF1, 0), X, inl)
    # the crown faces the pinion from the right
    S.put(m, "differential", "62821", frame((4, YF1, 0), z=neg(X), y=Y), right)
    for s, a, inner in ((-1, left, inl), (1, right, inr)):
        outer = beam(m, "outer-" + side(s), 9, (s * 48, YF1, 32), Z, X, a)
        for z in (8, 56):
            if s < 0:
                axle(m, "tie-%s-%d" % (side(s), z), 3, (-40, YF1, z), X, inner)
            else:
                axle(m, "tie-%s-%d" % (side(s), z), 4, (36, YF1, z), X, inner)
        bush(m, "bush-%s-1" % side(s), (s * 56, YF1, 0), X, a)
        bush(m, "bush-%s-2" % side(s), (s * 64, YF1, 0), X, a)
        S.put(m, "wheel-" + side(s), "49294c01", frame((s * 80, YF1, 0), z=(s, 0, 0), y=Y), a, round_part=True)
        sk = S.put(
            m,
            "shock-" + side(s),
            SHOCK,
            frame((s * 40, 88, 24), z=X, y=Y),
            pin(m, "pin-shock-foot-" + side(s), (s * 44, YF1, 24), neg((s, 0, 0)), outer),
        )
        # and its head into the tower above it
        pin(m, "pin-shock-head-" + side(s), (s * 44, 88, 24), (s, 0, 0), sk)


def build_rear_wing():
    m = REAR_WING
    ra = axle(m, "axle", 12, (0, 88, -8), X, S.get(SIDE_L, "tower"))
    blocks = [block(m, "block-" + side(s), (s * 24, 88, -8), X, Y, ra) for s in (-1, 1)]
    pl = beam(m, "pylon-l", 7, (-24, 120, -16), Y, Z, pin(m, "pin-pylon-l", (-24, 96, -12), neg(Z), blocks[0]))
    lo = beam(m, "slat-lo", 15, (0, 136, -24), X, Z, pin(m, "pin-slat-lo-l", (-24, 136, -20), neg(Z), pl))
    beam(m, "slat-hi", 15, (0, 144, -24), X, Z, pin(m, "pin-slat-hi-l", (-24, 144, -20), neg(Z), pl))
    pr = beam(m, "pylon-r", 7, (24, 120, -16), Y, Z, pin(m, "pin-slat-lo-r", (24, 136, -20), Z, lo))
    pin(m, "pin-slat-hi-r", (24, 144, -20), neg(Z), pr)
    pin(m, "pin-pylon-r", (24, 96, -12), Z, pr)
    for s in (-1, 1):
        ep = beam(
            m,
            "endplate-" + side(s),
            5,
            (s * 56, 128, -32),
            Y,
            Z,
            pin(m, "pin-endplate-%s-lo" % side(s), (s * 56, 136, -28), neg(Z), lo),
        )
        pin(m, "pin-endplate-%s-hi" % side(s), (s * 56, 144, -28), Z, ep)


def build_sidepod(s):
    m = "sidepod@" + side(s)
    pod = S.put(
        m,
        "panel",
        "62531",
        frame((s * 64, 40, ZB), x=(s, 0, 0), y=Y),
        pin(m, "pin-front", (s * 52, YF2, ZB - s * 32), neg((s, 0, 0)), S.get(side_frame(s), "rail-up")),
    )
    pin(m, "pin-back", (s * 52, YF2, ZB + s * 32), neg((s, 0, 0)), pod)


REMOTE_AT = (150.0, 18.4, 180.8)  # the handset, on the ground beside the car

CAR = ""  # the car's own level: f1/car.assy
SET = "set"  # the car and the remote control beside it: f1.assy
PRODUCT = "f1"


def build():
    global S
    S = Scene(Index(INDEX))
    build_tub()
    build_front_end()
    build_drivetrain()
    build_rear_wing()
    build_sidepod(-1)
    build_sidepod(1)
    S.placed(SET, "ir-remote", "58122", frame(REMOTE_AT, x=X, y=Y), note="a handset is not joined to the car it drives")
    return S


# ===========================================================================
# Writing it out

PIECES = {  # piece -> (what it is, for partcad.yaml and the file's header)
    "tub": "The tub: both side frames, the battery box between them, the pivot the drivetrain swings on, and the"
    " airbox",
    "side-frame-left": "The left side frame: the two rails, the post at the back and the shock tower over it",
    "side-frame-right": "The right side frame: the two rails, the post at the back and the shock tower over it",
    "battery": "The Power Functions battery box, with the pins in its end holes that the side frames go onto",
    "airbox": "The Power Functions IR receiver on a crossbeam, and the cross blocks the rear posts carry it by",
    "front-end": "Everything ahead of the battery: the front frame, both front corners, the steering, the nose and"
    " the front wing",
    "front-frame": "The front frame: the nose rails, the bulkheads the wishbones pivot on, the shock crossbeam and the"
    " servo's cradle",
    "front-right": "The right front corner: double wishbones, a kingpin, the knuckle, the wheel and a shock",
    "front-left": "The left front corner: double wishbones, a kingpin, the knuckle, the wheel and a shock",
    "steering": "The servo, its arm and the track rod",
    "nose": "The nose: a cross axle between the nose rails, a crossbeam, and the nose cone",
    "front-wing": "The front wing: two slats on edge between two endplates, hung from the nose on two pylons",
    "drivetrain": "The rear subframe: the motor unit, the differential, the half axles and wheels, and the two"
    " shocks it hangs from",
    "motor-unit": "The XL motor with its pinion, the bracket across its face and the spacer beam beside it",
    "rear-wing": "The rear wing: an axle through the shock towers, two slats on edge between two endplates, on two"
    " pylons",
    "sidepod": "A sidepod: one smooth panel pinned to the upper side rail",
}


def parent_of(module):
    return module.rsplit("/", 1)[0] if "/" in module else CAR


def leaf(module):
    return module.rsplit("/", 1)[-1]


def piece_of(module):
    return leaf(module).split("@")[0]


def instance_of(module):
    return leaf(module).replace("@", "-")


def object_of(module):
    return "%s/%s" % (PRODUCT, piece_of(module)) if module else "%s/car" % PRODUCT


def chain(module):
    """The modules from the car down to 'module', the car excluded."""
    out = []
    while module:
        out.insert(0, module)
        module = parent_of(module)
    return out


def num(v):
    v = round(v, 3)
    return str(int(v)) if v == int(v) else repr(v)


def mapname(node, iface, inst):
    return "%s-%s-%s" % (node.name, SHORT[iface], inst)


class Plan:
    """Which module every joint is written in, and what each piece has to externalize.

    A joint is written in the lowest module holding both of its parts. On the
    side of the part being placed, every module between there and the part has
    to be placed by that very joint - the part is the first thing in each of
    them - and on both sides a port inside a module is reached through what
    that module maps, one level at a time.
    """

    def __init__(self, S):
        self.S = S
        self.nodes = [n for n in S.order if n.module != SET]
        self.index = {id(n): i for i, n in enumerate(self.nodes)}
        self.modules = {CAR: []}
        for n in self.nodes:
            for m in chain(n.module):
                self.modules.setdefault(m, [])
        for n in self.nodes:
            self.modules[n.module].append(n)
        self.maps = {}  # piece -> {name: (element, iface, inst)}
        self.joints = []  # (module, element name, joint, with-inst, to-element name, to-inst)
        for n in self.nodes:
            if isinstance(n.joint, dict):
                self._place(n)
        self._check_reuse()

    def first(self, module):
        """The first node anywhere under 'module': what the module is placed by."""
        return min(
            (n for n in self.nodes if n.module == module or n.module.startswith(module + "/")),
            key=lambda n: self.index[id(n)],
        )

    def elements(self, module):
        """What 'module' holds directly - its own nodes and its child modules - in build order."""
        items = [(self.index[id(n)], "node", n) for n in self.modules[module]]
        for child in self.modules:
            if child and parent_of(child) == module:
                items.append((self.index[id(self.first(child))], "module", child))
        return [(kind, x) for _, kind, x in sorted(items, key=lambda i: i[0])]

    def _exported(self, module, node, iface, inst):
        """The name 'module' externalizes a port of 'node' by, mapping it on the way up."""
        below = chain(node.module)
        assert module in below, (module, node.module)
        inner = below[below.index(module) + 1 :]
        if not inner:
            name = mapname(node, iface, inst)
            self.maps.setdefault(piece_of(module), {})[name] = (node.name, iface, inst)
            return name
        child = inner[0]
        name_inside = self._exported(child, node, iface, inst)
        name = "%s-%s" % (instance_of(child), name_inside)
        self.maps.setdefault(piece_of(module), {})[name] = (instance_of(child), iface, name_inside)
        return name

    def _side(self, where, node, iface, inst):
        """(element name, instance name) that 'where' refers to a port of 'node' by."""
        if node.module == where:
            return node.name, inst
        below = chain(node.module)
        child = below[below.index(where) + 1] if where else below[0]
        return instance_of(child), self._exported(child, node, iface, inst)

    def _place(self, n):
        j = n.joint
        t = j["target"]
        a, b = chain(n.module), chain(t.module)
        common = [x for x, y in zip(a, b) if x == y]
        where = common[-1] if common else CAR
        # every module between 'where' and the part is placed by this joint
        for m in a[len(common) :]:
            if self.first(m) is not n:
                raise ValueError("%s/%s is joined out of %s, which it is not the first part of" % (n.module, n.name, m))
        src, with_inst = self._side(where, n, j["wiface"], j["winst"])
        dst, to_inst = self._side(where, t, j["tiface"], j["tinst"])
        self.joints.append((where, src, j, with_inst, dst, to_inst))

    def _check_reuse(self):
        """A piece used twice must be the same piece twice."""
        by_piece = {}
        for m in self.modules:
            if m:
                by_piece.setdefault(piece_of(m), []).append(m)
        for piece, mods in by_piece.items():
            ref = [n for n in self.nodes if n.module == mods[0]]
            for other in mods[1:]:
                got = [n for n in self.nodes if n.module == other]
                assert [n.name for n in got] == [n.name for n in ref], piece
                r0, o0 = inv(ref[0].M), inv(got[0].M)
                for x, y in zip(ref, got):
                    assert same(mul(r0, x.M), mul(o0, y.M)), (piece, x.name)
        self.by_piece = by_piece


def connect_yaml(out, j, with_inst, to_name, to_inst, indent="    "):
    out.append(indent + "connect:")
    out.append(indent + "  with: %s:%s" % (LEGO, j["wiface"]))
    out.append(indent + "  withInstance: %s" % with_inst)
    wp, tp = {}, {}
    for key, value in (("turnZ", j["turn"]), ("moveZ", j["move"])):
        if value:
            (wp if key in PARAMS[j["wiface"]] else tp)[key] = value
    if wp:
        out.append(indent + "  withParams:")
        out += [indent + "    %s: %s" % (k, num(v)) for k, v in wp.items()]
    out.append(indent + "  name: %s" % to_name)
    out.append(indent + "  to: %s:%s" % (LEGO, j["tiface"]))
    out.append(indent + "  toInstance: %s" % to_inst)
    if tp:
        out.append(indent + "  toParams:")
        out += [indent + "    %s: %s" % (k, num(v)) for k, v in tp.items()]


def write_module(plan, module, header, location=None):
    out = list(header)
    if location is not None:
        out.append("location: %s" % location)
    out.append("links:")
    joints = {(src, where): (j, w, dst, t) for where, src, j, w, dst, t in plan.joints}
    for kind, x in plan.elements(module):
        if kind == "node":
            out.append("  - part: %s" % plan.S.ix.ref(x.pid))
            out.append("    name: %s" % x.name)
            key = (x.name, module)
        else:
            out.append("  - assembly: %s" % object_of(x))
            out.append("    name: %s" % instance_of(x))
            key = (instance_of(x), module)
        if key in joints:
            j, w, dst, t = joints[key]
            connect_yaml(out, j, w, dst, t)
    return "\n".join(out) + "\n"


def piece_header(module):
    piece = piece_of(module)
    return [
        "# %s - a piece of the F1 car, generated by tools/gen_f1.py." % object_of(module),
        "#",
        "# " + PIECES[piece] + ".",
        "#",
        "# Built on its own and then fitted where it goes: its first item is its",
        "# origin and says nothing, and everything else in it is joined through its",
        "# ports to something before it. What the piece is joined by from outside",
        "# is what 'map:' externalizes in partcad.yaml.",
    ]


CAR_HEADER = [
    "# The Formula 1 car: Power Functions XL motor through a differential, a",
    "# servo on the steering, the battery box and the IR receiver. Generated by",
    "# tools/gen_f1.py.",
    "#",
    "# Four sub-systems, each built from pre-assembled blocks and fitted to the",
    "# tub through the ports those blocks externalize ('map:' in partcad.yaml),",
    "# plus the two sidepods. The container's placement is the tub's first beam's",
    "# own pose, turned from the parts' Y-up frame into PartCAD's Z-up world:",
    "# nose towards -Y, the ground at z = 0.",
    "name: car",
]


def world():
    """The build frame turned into PartCAD's Z-up world: the ground at z = 0."""
    return loc((0, 0, 0), (1, 0, 0), 90)


def placement(M):
    """Where PartCAD puts a part designed at M: in its Z-up world, and served upright."""
    return packed(mul(mul(world(), M), inv(UPRIGHT)))


def packed(m):
    t, a, ang = to_axis_angle(m)
    return "[[%s], [%s], %s]" % (", ".join(num(v) for v in t), ", ".join(num(v) for v in a), num(ang))


def write_set(S):
    out = [
        "# A Formula 1 car in LEGO Technic, and the Power Functions IR remote control",
        "# that drives it. Generated by tools/gen_f1.py.",
        "#",
        "# Two items and nothing joining them, since nothing does. The car, joined",
        "# part by part in f1/car.assy, is the set's origin; the handset stands on",
        "# the ground beside it, placed by coordinates in PartCAD's Z-up world.",
        "name: f1",
        "links:",
        "  - assembly: %s/car" % PRODUCT,
        "    name: car",
    ]
    for n in S.order:
        if n.module != SET:
            continue
        out.append("  - part: %s" % S.ix.ref(n.pid))
        out.append("    name: %s" % n.name)
        out.append("    # %s%s, so it is placed rather than joined." % (n.note[0].upper(), n.note[1:]))
        out.append("    location: %s" % placement(n.M))
    return "\n".join(out) + "\n"


def to_axis_angle(m):
    tr = m[0][0] + m[1][1] + m[2][2]
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))
    t = [m[0][3], m[1][3], m[2][3]]
    if ang < 1e-6:
        return t, [0, 0, 1], 0
    s = 2 * math.sin(math.radians(ang))
    axis = [(m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s]
    # scaled so that its largest component is one: [1, 1, -1] rather than a
    # rounded unit vector, which would move far parts by hundredths of a mm
    big = max(abs(c) for c in axis)
    return t, [round(c / big, 6) for c in axis], ang


BEGIN = "  # --- f1: generated by tools/gen_f1.py; edit the generator, not this block ---"
END = "  # --- end of f1 ---"


def write_yaml_block(plan):
    out = [BEGIN]
    for piece in PIECES:
        out.append("  %s/%s:" % (PRODUCT, piece))
        out.append("    type: assy")
        if piece in plan.maps:
            out.append("    map:")
            for name, (element, iface, inst) in sorted(plan.maps[piece].items()):
                out.append("      %s: [%s, %s:%s, %s]" % (name, element, LEGO, iface, inst))
        out.append('    desc: "%s"' % PIECES[piece])
    out += [
        "  %s/car:" % PRODUCT,
        "    type: assy",
        '    desc: "The car: every one of its parts joined through its ports, none placed by coordinates"',
        "  %s:" % PRODUCT,
        "    type: assy",
        "    path: f1.assy",
        "    desc: A Formula 1 car in LEGO Technic - Power Functions motors, suspension, and the IR remote control.",
        END,
    ]
    return "\n".join(out)


def main():
    S = build()
    plan = Plan(S)
    parts = len(S.order)
    joined = sum(1 for n in S.order if isinstance(n.joint, dict))
    placed = [n for n in S.order if n.joint == "location"]
    print(
        "%d parts: %d joined through ports, %d the car's origin, %d placed by coordinates (%s); %d pieces"
        % (
            parts,
            joined,
            parts - joined - len(placed),
            len(placed),
            ", ".join(n.name for n in placed),
            len(plan.by_piece),
        ),
        file=sys.stderr,
    )
    if "--check" in sys.argv:
        return 0
    folder = os.path.join(ROOT, PRODUCT)
    for name in os.listdir(folder):
        if name.endswith(".assy"):
            os.remove(os.path.join(folder, name))  # a piece that is gone must not linger
    for piece, mods in plan.by_piece.items():
        with open(os.path.join(folder, piece + ".assy"), "w") as f:
            f.write(write_module(plan, mods[0], piece_header(mods[0])))
    with open(os.path.join(folder, "car.assy"), "w") as f:
        f.write(write_module(plan, CAR, CAR_HEADER, location=placement(S.order[0].M)))
    with open(os.path.join(ROOT, PRODUCT + ".assy"), "w") as f:
        f.write(write_set(S))
    path = os.path.join(ROOT, "partcad.yaml")
    text = open(path).read()
    block_text = write_yaml_block(plan)
    text = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END), lambda _: block_text, text, flags=re.S)
    with open(path, "w") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
