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

## A note on interference

Every part here is placed by `location:` rather than joined by `connect:`, and a
LEGO stud is *meant* to occupy the part above it — that interference is what
makes bricks grip. So `partcad.test.interference` has something true to report
about almost every pair in the model, and nowhere to read that it is intended:
an overlap which is meant to be there is stated on the joint that causes it, and
coordinates are not a joint.

The check is therefore turned off on this assembly rather than given a threshold
high enough to swallow a stud, which would be a number pretending to be a
tolerance. What would make it meaningful is the stud / anti-stud mating in
`//pub/universe/lego/ldraw` declaring `snapIn: true` — a stud in an anti-stud is
an interference fit wherever it occurs — and this assembly being generated with
`connect:` so each brick is joined to the one it sits on. Both are worth doing
and neither is done yet.
