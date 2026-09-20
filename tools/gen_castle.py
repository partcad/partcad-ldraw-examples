#!/usr/bin/env python3
"""Generate castle.assy - a gothic castle built from LDraw LEGO parts.

The design follows what the Gothic castles actually look like - Corvin,
Pierrefonds, Carcassonne - rather than a generic keep-and-curtain-wall:

  * the skyline is made of spires, not battlements. Every tower carries a
    steep needle roof taller than half the tower under it;
  * towers stand at intervals along the curtain wall, not only at its corners,
    and the gate is flanked by a pair of them;
  * buttresses step out from the wall between the towers, each capped with a
    pinnacle - the vertical rhythm that reads as Gothic more than anything
    else does;
  * the keep is tall and narrow rather than square and squat, with a bartizan
    turreted at each corner and a spire over the middle;
  * the gateway is a pointed arch, corbelled in a course at a time.

Geometry is worked in LEGO's own grid, in the parts' native (LDraw-derived)
frame: X and Z are the stud grid, Y is up. A part's origin sits at the centre
of its top face, so a part `h` courses tall whose bottom is at course `c` spans
Y in [c*BRICK, (c+h)*BRICK] and is placed with its origin at (c+h)*BRICK.

The whole thing is rotated +90 deg about X at the container level, taking that
Y-up frame into PartCAD's Z-up world so front/top/right/iso mean what they say.
"""
import collections
import re
import sys

STUD = 8.0     # stud pitch, mm
BRICK = 9.6    # brick height, mm

LEGO = "//pub/universe/lego/ldraw"

# LDraw part ids. Note the letter suffixes: LDraw has no plain "3942" - the
# cone is 3942a/b/c, and only 3942b resolves.
BRICK_1X1 = f"{LEGO}/Brick:3005"
BRICK_1X2 = f"{LEGO}/Brick:3004"
BRICK_1X4 = f"{LEGO}/Brick:3010"
ROUND_2X2 = f"{LEGO}/Brick:3941"        # Brick 2 x 2 Round
CONE_2X2X2 = f"{LEGO}/Cone:3942b"       # 2 courses tall
CONE_3X3X2 = f"{LEGO}/Cone:6233"        # 2 courses tall
CONE_1X1 = f"{LEGO}/Cone:4589"          # 1 course tall

SIZE = 26         # curtain wall footprint, studs
WALL_TOP = 7      # solid wall courses 0..6; crenellations on course 7
CORNER_TOP = 15   # corner towers run courses 0..14
MURAL_TOP = 12    # the towers along the walls
GATE_TOP = 13     # the pair flanking the gateway
KEEP_TOP = 17     # the keep, which has to out-top all of them
BUTTRESS_TOP = 8  # buttresses stop just above the wall head
# The keep is tall enough for two tiers of windows.
KEEP_LANCETS = (4, 5, 6, 10, 11, 12)
KEEP_SIZE = 6     # the keep's footprint, studs

# The gateway, in absolute stud columns of the south wall.
GATE_FROM, GATE_TO = 11, 15

nodes = []
cells = {}

# Each reusable piece of the castle is built once, into a file of its own, and
# then placed wherever it occurs. The castle is not 732 unrelated bricks: it is
# nine identical spires, sixteen identical buttresses, four identical corner
# towers, three identical stretches of curtain wall, and a keep that is the
# same two courses of masonry over and over. Building each once means PartCAD
# meshes and caches it once, and the instruction book shows it once.
units = {}          # object name -> the nodes it holds
footprints = {}     # the unit being built -> {part name: where it sits on the grid}
placements = []     # (unit name, instance name, [x, y, z], angle) at the top
_stack = []         # the unit currently being built, if any


def target():
    return _stack[-1] if _stack else nodes


class unit:
    """Collect everything placed inside the 'with' into a named sub-assembly.

    Coordinates inside are the piece's own: a unit built at column 0, row 0,
    course 0 has its origin at that stud, and the top level says where the
    origin goes. That is what makes the same file usable in four places.
    """

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        _stack.append([])
        return self

    def __exit__(self, *exc):
        got = _stack.pop()
        if self.name in units:
            # Built twice: the second one has to agree with the first, or the
            # two placements are not the same piece after all.
            assert units[self.name] == got, "%s built twice, differently" % self.name
        else:
            units[self.name] = got
        return False


def put(name, instance, col, row, course, angle=0):
    """Place a built unit at a stud column, row and course."""
    placements.append((name, instance,
                       [round(col * STUD, 3), round(course * BRICK, 3), round(row * STUD, 3)],
                       angle))


def place(part, name, col, row, course, w, d, h=1, turned=False):
    """Place a part with a w x d stud footprint and h courses of height, its
    near-left stud at (col, row) and its body starting at `course`."""
    if turned:
        w, d = d, w
    x = (col + (w - 1) / 2.0) * STUD
    z = (row + (d - 1) / 2.0) * STUD
    y = (course + h) * BRICK
    target().append((part, name, [round(x, 3), round(y, 3), round(z, 3)],
                     [0, 1, 0], 90 if turned else 0))
    # Where this part sits on the stud grid, for '_supports' below to work out
    # what it is standing on and which stud of it. Recorded per unit, because a
    # part may only be joined to one built in the same file.
    footprints.setdefault(id(target()), {})[name] = (col, row, course, w, d, h, turned)
    # What stud cells this part fills, for the overlap check below. Half-stud
    # placements (a 1x1 centred on a 2x2) are rounded down into their cell.
    for dx in range(int(w)):
        for dz in range(int(d)):
            for dy in range(h):
                cells.setdefault((int(col // 1) + dx, int(row // 1) + dz, course + dy), []).append(name)


# Which courses a lancet is cut through. One stud wide and three courses tall,
# closing below the parapet: at this scale a stud is the narrowest opening
# there is, so the window is made tall and thin by running it up three courses
# rather than by shaping its head. The gateway is the one opening wide enough
# to be given a pointed arch.
LANCET_COURSES = (2, 3, 4)


def run(course, col, row, length, horizontal, tag, offset, skip=()):
    """Tile a straight wall run out of 1x4 / 1x2 / 1x1 bricks, starting with a
    short piece so that consecutive courses break joint. `skip` names offsets
    within the run to leave open, which is how the lancets are cut."""
    part_for = {1: BRICK_1X1, 2: BRICK_1X2, 4: BRICK_1X4}
    at = 0
    n = 0
    while at < length:
        if at in skip:
            at += 1
            continue
        remaining = length - at
        size = min(offset, remaining) if (offset and at == 0) else remaining
        size = 4 if size >= 4 else (2 if size >= 2 else 1)
        # Do not run a brick through a window.
        for s in range(1, size + 1):
            if at + s in skip:
                size = s
                break
        size = 4 if size >= 4 else (2 if size >= 2 else 1)
        if horizontal:
            place(part_for[size], f"{tag}_c{course}_{n}", col + at, row, course, size, 1)
        else:
            place(part_for[size], f"{tag}_c{course}_{n}", col, row + at, course, size, 1, turned=True)
        at += size
        n += 1


def wall(col, row, length, horizontal, tag, gap=None, lancets=()):
    """A curtain wall. `gap` is a (start, end) span of studs, relative to the
    run, left open for the gateway; `lancets` are offsets carrying a window."""
    for course in range(WALL_TOP):
        offset = 2 if course % 2 else 0
        skip = tuple(lancets) if course in LANCET_COURSES else ()
        if gap is None:
            run(course, col, row, length, horizontal, tag, offset, skip)
            continue
        a, b = gap
        if a > 0:
            run(course, col, row, a, horizontal, f"{tag}L", offset,
                tuple(x for x in skip if x < a))
        if length - b > 0:
            tail_skip = tuple(x - b for x in skip if x >= b)
            if horizontal:
                run(course, col + b, row, length - b, horizontal, f"{tag}R", offset, tail_skip)
            else:
                run(course, col, row + b, length - b, horizontal, f"{tag}R", offset, tail_skip)


def crenellate(col, row, length, horizontal, tag):
    """Alternating merlons along the wall head."""
    for i in range(0, length, 2):
        if horizontal:
            place(BRICK_1X1, f"{tag}_m{i}", col + i, row, WALL_TOP, 1, 1)
        else:
            place(BRICK_1X1, f"{tag}_m{i}", col, row + i, WALL_TOP, 1, 1)


def spire(col, row, tag, course):
    """A steep needle: two stacked 2x2 cones flaring off the tower, then a pair
    of 1x1 cones drawing it to a point. Six courses - taller than half the
    tower it sits on, which is what makes the skyline read as Gothic."""
    place(CONE_2X2X2, f"{tag}_s0", col, row, course, 2, 2, h=2)
    place(CONE_2X2X2, f"{tag}_s1", col, row, course + 2, 2, 2, h=2)
    place(CONE_1X1, f"{tag}_s2", col + 0.5, row + 0.5, course + 4, 1, 1)
    place(CONE_1X1, f"{tag}_s3", col + 0.5, row + 0.5, course + 5, 1, 1)


def tower(col, row, tag, top):
    """A round tower under a needle spire."""
    for course in range(top):
        place(ROUND_2X2, f"{tag}_c{course}", col, row, course, 2, 2)
    spire(col, row, tag, top)


def pinnacle(col, row, tag, course):
    """What caps a buttress: a small cone, repeating the spires in miniature."""
    place(CONE_1X1, f"{tag}_p", col, row, course, 1, 1)


def buttress(col, row, tag):
    """A pier stepping out from the wall, capped with a pinnacle.

    Gothic before anything else is this: the wall broken into vertical bays by
    projecting piers, each carried up past the parapet and finished with a
    point.
    """
    for course in range(BUTTRESS_TOP):
        place(BRICK_1X1, f"{tag}_c{course}", col, row, course, 1, 1)
    pinnacle(col, row, tag, BUTTRESS_TOP)


def bartizan(col, row, tag, base, top):
    """A turret corbelled out at a corner, carried up to its own little spire."""
    for course in range(base, top):
        place(BRICK_1X1, f"{tag}_c{course}", col, row, course, 1, 1)
    place(CONE_1X1, f"{tag}_p0", col, row, top, 1, 1)
    place(CONE_1X1, f"{tag}_p1", col, row, top + 1, 1, 1)


def keep(col, row, size, tag):
    """The central keep: tall and narrow, turreted at the corners, spired."""
    for course in range(KEEP_TOP):
        offset = 2 if course % 2 else 0
        lit = (2,) if course in KEEP_LANCETS else ()
        run(course, col, row, size, True, f"{tag}S", offset, lit)
        run(course, col, row + size - 1, size, True, f"{tag}N", offset, lit)
        run(course, col, row + 1, size - 2, False, f"{tag}W", offset, lit)
        run(course, col + size - 1, row + 1, size - 2, False, f"{tag}E", offset, lit)
    # merlons between the corner turrets
    for i in range(2, size - 2, 2):
        place(BRICK_1X1, f"{tag}_mS{i}", col + i, row, KEEP_TOP, 1, 1)
        place(BRICK_1X1, f"{tag}_mN{i}", col + i, row + size - 1, KEEP_TOP, 1, 1)
        place(BRICK_1X1, f"{tag}_mW{i}", col, row + i, KEEP_TOP, 1, 1)
        place(BRICK_1X1, f"{tag}_mE{i}", col + size - 1, row + i, KEEP_TOP, 1, 1)
    for dx, dz, nm in ((0, 0, "sw"), (size - 1, 0, "se"), (0, size - 1, "nw"), (size - 1, size - 1, "ne")):
        bartizan(col + dx, row + dz, f"{tag}_{nm}", KEEP_TOP, KEEP_TOP + 3)
    mid = col + (size - 3) / 2.0, row + (size - 3) / 2.0
    place(CONE_3X3X2, f"{tag}_spire", mid[0], mid[1], KEEP_TOP, 3, 3, h=2)
    place(CONE_1X1, f"{tag}_f0", col + (size - 1) / 2.0, row + (size - 1) / 2.0, KEEP_TOP + 2, 1, 1)
    place(CONE_1X1, f"{tag}_f1", col + (size - 1) / 2.0, row + (size - 1) / 2.0, KEEP_TOP + 3, 1, 1)


def keep_head(col, row, size, tag):
    """What finishes the keep: merlons between the corner turrets, a bartizan
    at each corner, and the spire over the middle. Built at course KEEP_TOP,
    which is course 0 of this piece."""
    top = KEEP_TOP
    for i in range(2, size - 2, 2):
        place(BRICK_1X1, f"{tag}_mS{i}", col + i, row, top, 1, 1)
        place(BRICK_1X1, f"{tag}_mN{i}", col + i, row + size - 1, top, 1, 1)
        place(BRICK_1X1, f"{tag}_mW{i}", col, row + i, top, 1, 1)
        place(BRICK_1X1, f"{tag}_mE{i}", col + size - 1, row + i, top, 1, 1)
    for dx, dz, nm in ((0, 0, "sw"), (size - 1, 0, "se"), (0, size - 1, "nw"), (size - 1, size - 1, "ne")):
        bartizan(col + dx, row + dz, f"{tag}_{nm}", top, top + 3)
    mid = col + (size - 3) / 2.0, row + (size - 3) / 2.0
    place(CONE_3X3X2, f"{tag}_spire", mid[0], mid[1], top, 3, 3, h=2)
    place(CONE_1X1, f"{tag}_f0", col + (size - 1) / 2.0, row + (size - 1) / 2.0, top + 2, 1, 1)
    place(CONE_1X1, f"{tag}_f1", col + (size - 1) / 2.0, row + (size - 1) / 2.0, top + 3, 1, 1)


def gateway_local():
    """The pointed arch, in the south wall's own columns rather than the
    castle's: the wall piece starts at column 2, so everything shifts by that."""
    a, b = GATE_FROM - 2, GATE_TO - 2
    place(BRICK_1X1, "gate_a0", a, 0, 3, 1, 1)
    place(BRICK_1X1, "gate_a1", b, 0, 3, 1, 1)
    place(BRICK_1X2, "gate_b0", a, 0, 4, 2, 1)
    place(BRICK_1X2, "gate_b1", b - 1, 0, 4, 2, 1)
    place(BRICK_1X4, "gate_c0", a, 0, 5, 4, 1)
    place(BRICK_1X1, "gate_c1", b, 0, 5, 1, 1)
    run(6, a, 0, b - a + 1, True, "gate_d", 0)


def gateway():
    """A pointed arch, corbelled in a course at a time: the opening is five
    studs wide for courses 0-2, steps in to three, then to one, and closes at
    course 5. That is what makes it read as Gothic rather than as a hole."""
    place(BRICK_1X1, "gate_a0", GATE_FROM, 0, 3, 1, 1)
    place(BRICK_1X1, "gate_a1", GATE_TO, 0, 3, 1, 1)
    place(BRICK_1X2, "gate_b0", GATE_FROM, 0, 4, 2, 1)
    place(BRICK_1X2, "gate_b1", GATE_TO - 1, 0, 4, 2, 1)
    place(BRICK_1X4, "gate_c0", GATE_FROM, 0, 5, 4, 1)
    place(BRICK_1X1, "gate_c1", GATE_TO, 0, 5, 1, 1)
    for course in (6,):
        run(course, GATE_FROM, 0, GATE_TO - GATE_FROM + 1, True, "gate_d", 0)


def build_castle():
    E = SIZE - 1
    span = SIZE - 4  # the wall between the corner towers

    # --- the pieces, each built once at its own origin --------------------
    bays = (3, 7, 14, 18)  # one lancet per bay, clear of the buttress piers

    with unit("castle/spire"):
        spire(0, 0, "spire", 0)
    with unit("castle/buttress"):
        buttress(0, 0, "butt")
    with unit("castle/tower-corner"):
        for course in range(CORNER_TOP):
            place(ROUND_2X2, f"t_c{course}", 0, 0, course, 2, 2)
    with unit("castle/tower-mural"):
        for course in range(MURAL_TOP):
            place(ROUND_2X2, f"t_c{course}", 0, 0, course, 2, 2)
    with unit("castle/tower-gate"):
        for course in range(GATE_TOP):
            place(ROUND_2X2, f"t_c{course}", 0, 0, course, 2, 2)
    with unit("castle/wall"):
        wall(0, 0, span, True, "w", lancets=bays)
        crenellate(0, 0, span, True, "w")
    with unit("castle/wall-gate"):
        wall(0, 0, span, True, "w", gap=(GATE_FROM - 2, GATE_TO - 1), lancets=bays)
        crenellate(0, 0, span, True, "w")
        gateway_local()

    # The keep is the same two courses of masonry over and over: an even course
    # and the odd one that breaks joint against it. Three kinds of pair - plain,
    # both courses cut by a lancet, and the pair a lancet ends in - cover all of
    # it but the last course and the roof.
    def band(tag, base, lit_courses):
        for i in (0, 1):
            course = base + i
            offset = 2 if course % 2 else 0
            lit = (2,) if course in lit_courses else ()
            for side, (c, r, ln, horiz) in {
                "S": (0, 0, KEEP_SIZE, True),
                "N": (0, KEEP_SIZE - 1, KEEP_SIZE, True),
                "W": (0, 1, KEEP_SIZE - 2, False),
                "E": (KEEP_SIZE - 1, 1, KEEP_SIZE - 2, False),
            }.items():
                run(i, c, r, ln, horiz, f"{tag}{side}", offset, lit)

    with unit("castle/keep-courses"):
        band("k", 0, ())
    with unit("castle/keep-courses-lancets"):
        band("k", 4, (4, 5))
    with unit("castle/keep-courses-lancet-head"):
        band("k", 6, (6,))
    with unit("castle/keep-course-last"):
        offset = 2 if (KEEP_TOP - 1) % 2 else 0
        for side, (c, r, ln, horiz) in {
            "S": (0, 0, KEEP_SIZE, True),
            "N": (0, KEEP_SIZE - 1, KEEP_SIZE, True),
            "W": (0, 1, KEEP_SIZE - 2, False),
            "E": (KEEP_SIZE - 1, 1, KEEP_SIZE - 2, False),
        }.items():
            run(0, c, r, ln, horiz, f"k{side}", offset, ())
    with unit("castle/keep-head"):
        keep_head(0, 0, KEEP_SIZE, "keep")

    # --- and where each one goes ------------------------------------------
    put("castle/wall-gate", "wallS", 2, 0, 0)
    put("castle/wall", "wallN", 2, E, 0)
    put("castle/wall", "wallW", 0, 2, 0, angle=270)
    put("castle/wall", "wallE", E, 2, 0, angle=270)

    # Every tower body first and every spire after it, rather than a body and
    # its spire at a time: the bodies are all the same piece and so are the
    # spires, and that is what lets the file say so once.
    corners = (("SW", 0, 0), ("SE", SIZE - 2, 0), ("NW", 0, SIZE - 2), ("NE", SIZE - 2, SIZE - 2))
    for nm, c, r in corners:
        put("castle/tower-corner", f"tower{nm}", c, r, 0)
    for nm, c, r in corners:
        put("castle/spire", f"spire{nm}", c, r, CORNER_TOP)

    mid = SIZE // 2 - 1
    mural = (("N", mid, E + 1), ("W", -2, mid), ("E", E + 1, mid))
    for nm, c, r in mural:
        put("castle/tower-mural", f"tower{nm}", c, r, 0)
    for nm, c, r in mural:
        put("castle/spire", f"spire{nm}", c, r, MURAL_TOP)
    gates = (("W", GATE_FROM - 3), ("E", GATE_TO + 1))
    for nm, c in gates:
        put("castle/tower-gate", f"gate{nm}", c, -2, 0)
    for nm, c in gates:
        put("castle/spire", f"gateSpire{nm}", c, -2, GATE_TOP)

    for c in (4, 6, 19, 21):
        put("castle/buttress", f"buttS{c}", c, -1, 0)
    for c in (5, 8, 17, 20):
        put("castle/buttress", f"buttN{c}", c, SIZE, 0)
    for r in (5, 8, 17, 20):
        put("castle/buttress", f"buttW{r}", -1, r, 0)
        put("castle/buttress", f"buttE{r}", SIZE, r, 0)

    for i, base in enumerate((0, 2, 8, 14)):
        put("castle/keep-courses", f"keepC{base}", 10, 10, base)
    for base in (4, 10):
        put("castle/keep-courses-lancets", f"keepL{base}", 10, 10, base)
    for base in (6, 12):
        put("castle/keep-courses-lancet-head", f"keepH{base}", 10, 10, base)
    put("castle/keep-course-last", "keepLast", 10, 10, KEEP_TOP - 1)
    put("castle/keep-head", "keepHead", 10, 10, 0)


# --- joining the bricks to each other --------------------------------------
#
# A brick placed by coordinates is a brick nothing holds up: the model says
# where it ended up and not what puts it there, so nothing can check it and an
# instruction book can only say "at (144, 9.6, 0)". Joined instead through the
# stud it sits on, the model says the thing that is true - this brick goes on
# that one, on that stud - and PartCAD works the coordinates out.
#
# '//pub/universe/lego' declares the pair: a 'stud' on the top of a part and an
# 'anti-stud' underneath it, one instance per stud, named 'c<column>r<row>' in
# the part's own grid. So a joint is two of those names, and the arithmetic
# below is only about which two.

STUD_IFACE = "//pub/universe/lego:stud"
ANTI_IFACE = "//pub/universe/lego:anti-stud"

# Every part here has the anti-studs it stands on, as of partcad-ldraw#12: the
# 1 x 1 cone had none at all and the 2 x 2 cone had two of its four, both on
# one side, and both are fixed. Nothing is excluded for want of an interface
# any more.
NO_ANTI_STUD = set()


# Where each part's studs and anti-studs actually are, in its own frame, in mm.
# Read from '//pub/universe/lego/ldraw' rather than worked out from the stud
# grid, because for these parts the grid is not the answer: a Cone 2 x 2 x 2
# has four anti-studs under it and a single stud on top, at its centre, and a
# Cone 3 x 3 x 2 has nine and four. A joint picked by grid index puts such a
# part half a stud out; picked by where the ports are, it cannot.
PORTS = {
    'Brick:3004': {
        "stud": {'c0r0': [-4.0, 0.0, 0.0], 'c1r0': [4.0, 0.0, 0.0]},
        "anti": {'c0r0': [-4.0, -9.6, 0.0], 'c1r0': [4.0, -9.6, 0.0]},
    },
    'Brick:3005': {
        "stud": {'c0r0': [0.0, 0.0, 0.0]},
        "anti": {'c0r0': [0.0, -9.6, 0.0]},
    },
    'Brick:3010': {
        "stud": {'c0r0': [-12.0, 0.0, 0.0], 'c1r0': [-4.0, 0.0, 0.0], 'c2r0': [4.0, 0.0, 0.0], 'c3r0': [12.0, 0.0, 0.0]},
        "anti": {'c0r0': [-12.0, -9.6, 0.0], 'c1r0': [-4.0, -9.6, 0.0], 'c2r0': [4.0, -9.6, 0.0], 'c3r0': [12.0, -9.6, 0.0]},
    },
    'Brick:3941': {
        "stud": {'c0r0': [-4.0, 0.0, -4.0], 'c0r1': [-4.0, 0.0, 4.0], 'c1r0': [4.0, 0.0, -4.0], 'c1r1': [4.0, 0.0, 4.0]},
        "anti": {'c0r0': [-4.0, -9.6, -4.0], 'c0r1': [-4.0, -9.6, 4.0], 'c1r0': [4.0, -9.6, -4.0], 'c1r1': [4.0, -9.6, 4.0]},
    },
    'Cone:3942b': {
        "stud": {'c0r0': [0.0, 0.0, 0.0]},
        "anti": {'c0r0': [-4.0, -19.2, -4.0], 'c0r1': [-4.0, -19.2, 4.0], 'c1r0': [4.0, -19.2, -4.0], 'c1r1': [4.0, -19.2, 4.0]},
    },
    'Cone:4589': {
        "stud": {'c0r0': [0.0, 0.0, 0.0]},
        "anti": {'c0r0': [0.0, -9.6, 0.0]},
    },
    'Cone:6233': {
        "stud": {'c0r0': [-4.0, 0.0, -4.0], 'c0r1': [-4.0, 0.0, 4.0], 'c1r0': [4.0, 0.0, -4.0], 'c1r1': [4.0, 0.0, 4.0]},
        "anti": {'c0r0': [-8.0, -19.2, -8.0], 'c0r1': [-8.0, -19.2, 0.0], 'c0r2': [-8.0, -19.2, 8.0], 'c1r0': [0.0, -19.2, -8.0], 'c1r1': [0.0, -19.2, 0.0], 'c1r2': [0.0, -19.2, 8.0], 'c2r0': [8.0, -19.2, -8.0], 'c2r1': [8.0, -19.2, 0.0], 'c2r2': [8.0, -19.2, 8.0]},
    },
}

# Two ports meet when they are at the same place. They are written to three
# decimals and land on an 8 mm grid, so anything this close is the same point.
TOUCHING = 0.01


def _turned_xz(local, angle):
    """A port's offset from its part's origin, once the part is turned."""
    x, _y, z = local
    return (z, -x) if angle else (x, z)


def _world_ports(part, pos, angle, kind):
    """Where every port of one kind on one placed part is, in the unit's frame."""
    out = {}
    for inst, local in (PORTS.get(part.split("/")[-1], {}).get(kind) or {}).items():
        dx, dz = _turned_xz(local, angle)
        out[inst] = (round(pos[0] + dx, 3), round(pos[1] + local[1], 3), round(pos[2] + dz, 3))
    return out


def _meeting(a, b):
    """The first pair of ports from 'a' and 'b' that are at the same point."""
    for mine, here in sorted(a.items()):
        for theirs, there in sorted(b.items()):
            if all(abs(here[i] - there[i]) < TOUCHING for i in range(3)):
                return mine, theirs
    return None


def _joints(items, unit_key=None):
    """A joint for every part whose underside meets a stud already placed.

    Worked out from where the ports are rather than from the stud grid: a part
    stands on another when one of its anti-studs is at the same point as one of
    that part's studs. That is the whole test, and it is the same test for a
    brick, a round brick and a cone, whatever grid their names imply.

    Only something already in the file may be stood on, because a joint may
    only name a node placed before it; the first part of a unit therefore keeps
    its coordinates, having nothing under it.
    """
    joints = {}
    placed = []
    for part, name, pos, _axis, ang in items:
        mine = _world_ports(part, pos, ang, "anti")
        for other, other_part, other_pos, other_ang in placed:
            # A brick laid across the one under it is left on coordinates. The
            # joint is expressible - 'anti-stud' carries 'turnZ' and a probe
            # reproduces the placement exactly - but which anti-stud to name
            # and which way to turn cannot be worked out from the geometry
            # here: the pair that meet are found correctly (c0r0 on c2r0 for
            # the keep's west wall, and they do coincide), and PartCAD still
            # lands the brick a stud away, because where a turned part ends up
            # depends on the roll of the port frames rather than on the offset
            # of the port. Predicting it means repeating PartCAD's mate
            # arithmetic here, and getting it wrong means a brick silently in
            # the wrong place.
            if ang or part in NO_ANTI_STUD:
                break
            theirs = _world_ports(other_part, other_pos, other_ang, "stud")
            met = _meeting(mine, theirs)
            if met:
                joints[name] = (other, met[0], met[1], ang)
                break
        placed.append((name, part, pos, ang))
    return joints


# --- writing the ASSY files -----------------------------------------------
#
# An ASSY file has to enumerate every step: PartCAD reads the tree it makes to
# work out the bill of materials, and the assembly instructions are that tree
# written out one step per page. Nothing here may be left implicit.
#
# The *text* need not repeat itself, though. Every ASSY file is a Jinja2
# template, rendered before it is parsed, so a run of parts laid out regularly -
# fifteen courses of round brick, one on top of the next; seven 1x4 bricks along
# a wall a stud pitch apart - is written as the loop it is and reaches the parser
# as the fifteen or seven nodes it always was. The steps are all still there.
#
# Which runs those are is not worth deciding by hand: '_fold' finds them, by
# looking for consecutive nodes that differ only by an arithmetic step in each
# coordinate and in the number ending their name.

NAME_TAIL = re.compile(r"^(.*?)(\d+)$")
MIN_RUN = 3  # below this a loop is longer than what it replaces, and harder to read


def _num(v):
    """A coordinate as YAML, without a float's trailing noise."""
    return repr(round(v + 0.0, 3))


def _split_name(name):
    m = NAME_TAIL.match(name)
    return (m.group(1), int(m.group(2))) if m else (name, None)


def _step(a, b):
    return None if a is None or b is None else b - a


def _run_length(items, start):
    """How many nodes from 'start' are the same node moved by a constant step."""
    kind, ref, name, pos, axis, ang = items[start]
    if start + 1 >= len(items):
        return 1
    prefix, n0 = _split_name(name)
    nxt = items[start + 1]
    if (nxt[0], nxt[1], tuple(nxt[4]), nxt[5]) != (kind, ref, tuple(axis), ang):
        return 1
    prefix1, n1 = _split_name(nxt[2])
    if prefix1 != prefix or n0 is None or n1 is None:
        return 1
    dn = n1 - n0
    delta = [nxt[3][i] - pos[i] for i in range(3)]
    length = 2
    while start + length < len(items):
        cur = items[start + length]
        if (cur[0], cur[1], tuple(cur[4]), cur[5]) != (kind, ref, tuple(axis), ang):
            break
        p, n = _split_name(cur[2])
        if p != prefix or n != n0 + dn * length:
            break
        if any(abs(cur[3][i] - (pos[i] + delta[i] * length)) > 1e-6 for i in range(3)):
            break
        length += 1
    return length


def _axis_yaml(axis, ang):
    return f"[{axis[0]}, {axis[1]}, {axis[2]}], {ang}"


def _group_length(items, start):
    """How many nodes from 'start' are the same thing placed somewhere else."""
    kind, ref, _, _, axis, ang = items[start]
    length = 1
    while start + length < len(items):
        cur = items[start + length]
        if (cur[0], cur[1], tuple(cur[4]), cur[5]) != (kind, ref, tuple(axis), ang):
            break
        length += 1
    return length


def _table_loop(items, indent):
    """A run of one thing placed at unrelated spots, as a loop over a table.

    Nothing about where the sixteen buttresses go is regular - they sit where
    the bays leave room for them - so there is no arithmetic to write. What
    repeats is everything else, which a loop over the placements still saves.
    """
    kind, ref, _, _, axis, ang = items[0]
    varying = [k for k in range(3) if len({round(it[3][k], 6) for it in items}) > 1]
    fields = ["name"] + ["xyz"[k] for k in varying]
    rows = [
        "%s    [%s]," % (indent, ", ".join(['"%s"' % it[2]] + [_num(it[3][k]) for k in varying]))
        for it in items
    ]
    coords = [f"{{{{ {'xyz'[k]} }}}}" if k in varying else _num(items[0][3][k]) for k in range(3)]
    return [
        f"{indent}{{% for {', '.join(fields)} in [",
        *rows,
        f"{indent}  ] %}}",
        f"{indent}- {kind}: {ref}",
        f"{indent}  name: {{{{ name }}}}",
        f"{indent}  location: [[{coords[0]}, {coords[1]}, {coords[2]}], {_axis_yaml(axis, ang)}]",
        f"{indent}{{% endfor %}}",
    ]


def _fold(items, indent="  "):
    """The nodes as YAML, with runs of them written as Jinja2 loops."""
    out = []
    i = 0
    while i < len(items):
        length = _run_length(items, i)
        kind, ref, name, pos, axis, ang = items[i]
        if length < MIN_RUN:
            group = _group_length(items, i)
            if group >= MIN_RUN:
                out.extend(_table_loop(items[i : i + group], indent))
                i += group
                continue
        if length < MIN_RUN:
            out.append(f"{indent}- {kind}: {ref}")
            out.append(f"{indent}  name: {name}")
            out.append(f"{indent}  location: [[{_num(pos[0])}, {_num(pos[1])}, {_num(pos[2])}], {_axis_yaml(axis, ang)}]")
            i += 1
            continue

        prefix, n0 = _split_name(name)
        dn = _split_name(items[i + 1][2])[1] - n0
        delta = [items[i + 1][3][k] - pos[k] for k in range(3)]
        var = "i"
        counted = f"{{{{ {n0} + {var} * {dn} }}}}" if (n0, dn) != (0, 1) else f"{{{{ {var} }}}}"
        coords = [
            _num(pos[k])
            if abs(delta[k]) < 1e-9
            else f"{{{{ ({_num(pos[k])} + {var} * {_num(delta[k])}) | round(3) }}}}"
            for k in range(3)
        ]
        out.append(f"{indent}{{% for {var} in range({length}) %}}")
        out.append(f"{indent}- {kind}: {ref}")
        out.append(f"{indent}  name: {prefix}{counted}")
        out.append(f"{indent}  location: [[{coords[0]}, {coords[1]}, {coords[2]}], {_axis_yaml(axis, ang)}]")
        out.append(f"{indent}{{% endfor %}}")
        i += length
    return out


def _nodes_yaml(items, indent="  ", joints=None):
    """The part nodes of one file: joined where they stand on something.

    A part with nothing under it - the first course of a unit - still has to be
    put somewhere, so it keeps its coordinates. Everything above it names the
    part and the stud it goes on instead, and a part laid across the one under
    it says so with 'turnZ', which is the freedom a single stud really has.

    Folding is for coordinates and has nothing to fold here, so a joined part is
    written out one node at a time.
    """
    joints = joints or {}
    out = []
    for part, nm, pos, axis, ang in items:
        joint = joints.get(nm)
        if joint is None:
            out.extend(_fold([("part", part, nm, pos, axis, ang)], indent))
            continue
        other, mine, theirs, angle = joint
        out.append(f"{indent}- part: {part}")
        out.append(f"{indent}  name: {nm}")
        out.append(f"{indent}  connect:")
        out.append(f"{indent}    with: {ANTI_IFACE}")
        out.append(f"{indent}    withInstance: {mine}")
        if angle:
            # 'turnZ' turns about the anti-stud's own Z, which points down into
            # the part, so it runs the opposite way round from the angle a
            # 'location:' states about +Y.
            out.append(f"{indent}    withParams:")
            out.append(f"{indent}      turnZ: {-angle}")
        out.append(f"{indent}    name: {other}")
        out.append(f"{indent}    to: {STUD_IFACE}")
        out.append(f"{indent}    toInstance: {theirs}")
    return out


def write_units(directory):
    """One file per reusable piece, under the directory its name gives it."""
    import os

    for name, items in units.items():
        path = os.path.join(directory, name + ".assy")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out = [
            f"# {name}: one of the pieces '{'castle'}' is assembled from, built once here",
            "# and placed wherever it occurs. Its first course is put down by",
            "# coordinates - its origin is the stud it starts at, which is what lets one",
            "# file stand for every instance of it - and everything above that says the",
            "# brick and the stud it goes on.",
            "links:",
            *_nodes_yaml(items, joints=_joints(items)),
        ]
        open(path, "w").write("\n".join(out) + "\n")
        print(f"  {path}: {len(items)} parts")


def write(path, name, header):
    out = [*header, f"name: {name}", "location: [[0, 0, 0], [1, 0, 0], 90]", "links:"]
    counts = collections.Counter(u for u, _, _, _ in placements)
    out.extend(_fold([("assembly", u, nm, pos, [0, 1, 0], ang) for u, nm, pos, ang in placements]))
    out.extend(_nodes_yaml(nodes))
    open(path, "w").write("\n".join(out) + "\n")
    total = sum(len(v) for v in units.values())
    print(f"{path}: {len(placements)} placements of {len(units)} pieces"
          f" ({total} parts written once), {len(nodes)} loose parts")
    for u, n in counts.most_common():
        print(f"  x{n:<3d} {u} ({len(units[u])} parts)")


def check():
    """Report stud cells more than one part claims.

    An assembly whose parts are all in the wrong place still passes `pc test`,
    and 666 parts is too many to check by eye. Two parts in one cell is either
    a mistake or a deliberate bond; either way it should be a decision.
    """
    clashes = {k: v for k, v in cells.items() if len(v) > 1}
    if not clashes:
        print("no two parts share a stud cell")
        return 0
    print("%d stud cells claimed more than once:" % len(clashes))
    by_pair = collections.Counter()
    for names in clashes.values():
        by_pair[tuple(sorted({n.rsplit("_c", 1)[0] for n in names}))] += 1
    for pair, n in by_pair.most_common(12):
        print("  %4d cells  %s" % (n, " + ".join(pair)))
    return 1


build_castle()
if "--check" in sys.argv:
    sys.exit(check())
write_units(".")
write("castle.assy", "castle", [
    "# A gothic castle in LEGO, generated by tools/gen_castle.py.",
    "#",
    "# Spired towers along the curtain wall and at its corners, a twin-towered",
    "# gatehouse over a pointed arch, buttresses with pinnacles between the",
    "# bays, and a tall turreted keep. Parts are LDraw parts from",
    "# //pub/universe/lego, placed on LEGO's own grid: 8 mm stud pitch,",
    "# 9.6 mm brick height.",
    "#",
    "# The container rotation takes the parts' native Y-up frame into PartCAD's",
    "# Z-up world, so front/top/right/iso mean what they say.",
])
