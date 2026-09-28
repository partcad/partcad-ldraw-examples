# //pub/examples/lego

Assemblies built from the [LDraw](https://library.ldraw.org) parts library, as
served by `//pub/universe/lego/ldraw`. Nothing is vendored here: this package is
the assemblies, and the geometry is meshed from LDraw's own `.dat` files on
demand.

## castle

A gothic castle: spired towers along the curtain wall and at its corners, a
twin-towered gatehouse over a pointed arch, buttresses with pinnacles between
the bays, and a tall turreted keep.

<table><tr>
<td valign=top><a href="./images/castle-birdseye.png"><img src="./images/castle-birdseye.png" alt="The castle from above" width="420"></a></td>
<td valign=top><a href="./images/castle-front.png"><img src="./images/castle-front.png" alt="The castle from the front" width="420"></a></td>
</tr></table>

732 parts, seven distinct LDraw parts between them:

| part | count | |
| --- | --- | --- |
| `Brick:3005` | 271 | 1 x 1 brick |
| `Brick:3004` | 161 | 1 x 2 brick |
| `Brick:3941` | 122 | 1 x 1 round brick |
| `Brick:3010` | 115 | 1 x 4 brick |
| `Cone:4589` | 44 | 1 x 1 cone — the spires |
| `Cone:3942b` | 18 | 2 x 2 cone |
| `Cone:6233` | 1 | 3 x 3 roof cone — the keep |

Everything sits on LEGO's own grid: 8 mm stud pitch, 9.6 mm brick height. The
container carries a single rotation that takes the parts' native Y-up frame into
PartCAD's Z-up world, so `front`, `top`, `right` and `iso` mean what they say.

```shell
pc inspect -a castle
pc render -a -t png --view iso castle
```

### The pieces it is built from

A castle this size repeats itself: four identical corner towers, nine identical
spires, sixteen identical buttresses. So `castle` is not 732 parts in one file -
it is twelve sub-assemblies under `castle/`, placed 48 times between them. Each
one is written once and built once, and every further use of it is a cache hit
rather than a rebuild; 273 parts are described instead of 732.

| sub-assembly | parts | used | |
| --- | --- | --- | --- |
| `castle/buttress` | 9 | 16 | a pier stepping out from the wall, capped with a pinnacle |
| `castle/spire` | 4 | 9 | two 2x2 cones flaring off a tower, then two 1x1 cones to a point |
| `castle/wall` | 65 | 3 | a stretch of curtain wall between two corner towers |
| `castle/wall-gate` | 70 | 1 | the same wall with the gateway's pointed arch corbelled through it |
| `castle/tower-corner` | 15 | 4 | the body of a corner tower |
| `castle/tower-mural` | 12 | 3 | the body of a tower standing along a wall |
| `castle/tower-gate` | 13 | 2 | the body of one of the gatehouse pair |
| `castle/keep-courses` | 14 | 3 | two courses of the keep, the second breaking joint against the first |
| `castle/keep-lancet` | 38 | 2 | four courses: a lancet, and the course that closes it |
| `castle/keep-top` | 47 | 1 | the keep's last three courses, its merlons, four bartizans and the spire |

Each is a PartCAD assembly in its own right, so any of them can be looked at,
rendered or built alone:

```shell
pc inspect -a castle/tower-corner
pc render -a -t png --view iso castle/wall
```

The keep is cut into pairs of courses rather than left whole because its
masonry alternates: an even course and the odd one that breaks joint against
it, three kinds of pair covering all of it but the last course and the roof.
The walls are not split further - the gate wall differs from a plain one in
every course, so there is no band of it the two could share.

### Joined, not just placed

A brick placed by coordinates is a brick nothing holds up: the file says where
it ended up, not what puts it there. Most of these bricks say the other thing
instead — which brick they sit on, and which stud of it:

```yaml
- part: //pub/universe/lego/ldraw/Brick:3010
  name: w_c1_0
  connect:
    with: //pub/universe/lego:anti-stud
    withInstance: c0r0
    name: w_c0_0
    to: //pub/universe/lego:stud
    toInstance: c2r0
```

`//pub/universe/lego` declares the pair — a `stud` on top of a part and an
`anti-stud` underneath — and PartCAD works the coordinates out. **Every one of
the 287 part nodes** is joined that way, in the order they are put together —
there is not a single `location:` left on a part or a piece anywhere in the
model.

Which two ports meet is decided by where they *are*, not by the stud grid the
part's name implies, because for several of these parts the grid is not the
answer: a `Cone 2 x 2 x 2` has four anti-studs under it and a single stud on
top, at its centre, and a `Cone 3 x 3 x 2` has nine and four. A joint picked by
grid index puts such a part half a stud out.

A brick joins downwards to a stud under it *or* upwards into an anti-stud over
it, and that is what keeps the number of coordinates down. A unit's bottom
course does not have to go first: put one brick of it down, add the brick above
that bridges it to its neighbour, and the neighbour then snaps up into that
bridge. So the order is grown rather than given — take whatever can be joined to
what is already down.

Each piece's **first brick says nothing at all** — no coordinates and no joint.
It is the piece's own origin, and where that goes is for whatever places the
piece to decide, so saying it here would be saying it twice.

Getting to none of them took four things beyond the joints themselves, and each
was a fault in the model rather than a limit of the format:

* **The keep's corners did not bond.** Every course laid its four sides the same
  way, so no brick ever spanned a corner and the keep was four stacks that
  merely touched. The corners alternate now.
* **A course over an opening has to reach past it.** A lancet capped by two
  bricks meeting over the hole ties nothing; the capping course is laid
  whichever way puts one brick across the opening with a bearing either side,
  which is not the same way for a four-stud stretch as for a six-stud one. The
  gateway's lintel got the same treatment and now bears a stud into the wall on
  each side.
* **No stretch ends with a single stud.** Three cells laid greedily come out a
  two and a one, and that trailing one sits on the corner with nothing reaching
  across to it.
* **The keep's spire stood on its own open shaft.** It has a floor now — the
  last course laid solid, six bricks the full width, each crossing the ring
  below at both ends — and a spire built the way the towers' are, since a 3 x 3
  cone cannot be centred on a 6 x 6 keep and was sitting half a stud off the
  grid.

### The pieces join each other too, and the whole thing stands on a plate

A piece is placed by coordinates for the same reason a brick was: nothing says
what holds it. So each piece externalizes the ports it is joined by, with `map:`:

```yaml
assemblies:
  castle/spire:
    type: assy
    map:
      spire_s0-anti-c0r0: [spire_s0, //pub/universe/lego:anti-stud, c0r0]
```

A name of the piece's choosing, against the node inside it, the interface that
node implements, and the instance. The interface is not renamed — it is a
contract — but the instance name is the piece's to pick.

The walls, towers and buttresses were the hard case: they all stand on the
ground side by side, and a stud joins what is above to what is below, so edge to
edge there is nothing to join them by. LEGO's own answer is a baseplate, and the
library has one big enough — `Baseplate 32 x 32` (3811), 1024 studs against a
castle covering 30 × 30. Every piece that reaches the ground is joined to it.

So the baseplate says nothing at all: where it goes decides nothing, since every
other node is placed relative to it, and where the castle as a whole sits is the
container's to say.

### The one `location:` left, and why it stays

```yaml
name: castle
location: [[0, 0, 0], [1, 0, 0], 90]   # set the offset to [100.0, -100.0, 0.0] to read coordinates off the stud grid
```

One `location:` in the whole model, on the container, and it is a **turn rather
than a place**. LDraw draws its parts Y-up and PartCAD's world is Z-up: without
it the castle lies on its side, its baseplate standing up like a wall, and
`front`, `top`, `right` and `iso` all mean something else. No joint can derive
that — it is a fact about the parts library, not about the model.

The offset beside the turn is a knob rather than a fact, and it is not free.
Left at zero the castle sits at the origin, which is where the default views
expect to find it. Set to the figure in the comment it stands where the grid
runs on whole studs from a known corner — worth having while reading the numbers
by hand, and it costs the rendered views their framing, because they look from a
fixed point rather than from one relative to the object.

### Jinja2, and why every step is still written down

An ASSY file has to enumerate every step. PartCAD reads the tree it makes to
work out the bill of materials, and the assembly instructions are that tree
written out a step to a page, so a step that is not in the file is a step
nobody is told to take.

The *text* need not repeat itself, though: every ASSY file is a Jinja2 template,
rendered before it is parsed. A run of parts laid out regularly is written as
the loop it is -

```yaml
{% for i in range(15) %}
- part: //pub/universe/lego/ldraw/Brick:3941
  name: t_c{{ i }}
  location: [[4.0, {{ (9.6 + i * 9.6) | round(3) }}, 4.0], [0, 1, 0], 0]
{% endfor %}
```

- and reaches the parser as the fifteen separate nodes it always was. Where
there is no arithmetic to write, because the sixteen buttresses sit wherever
the bays leave room for them, the loop runs over a table of placements instead.
Between them the thirteen files are **321 nodes of YAML for a 732-part model**,
and every one of those 732 parts is still a step of its own.

## A note on interference

Every part here is placed by `location:` rather than joined by `connect:`, and a
LEGO stud is *meant* to occupy the part above it — that interference is what
makes bricks grip. So `partcad.test.interference` has something true to report
about almost every pair in the model, and nowhere to read that it is intended:
an overlap which is meant to be there is stated on the joint that causes it, and
coordinates are not a joint.

Nothing here turns the check off. The package is `manufacturable: false` —
nobody is ordering a castle — and that is what makes interference report what it
finds rather than fail on it. Giving it a threshold high enough to swallow a
stud would be worse than either: that floor is a rounding tolerance, and making
it carry this would be a number pretending to be one.

What would make the check meaningful is the stud / anti-stud mating in
`//pub/universe/lego/ldraw` declaring `snapIn: true` — a stud in an anti-stud is
an interference fit wherever it occurs — and this assembly being generated with
`connect:` so each brick is joined to the one it sits on. Both are worth doing
and neither is done yet.
