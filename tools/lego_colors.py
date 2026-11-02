"""The colours these models are built in, and the parts in them, for the generators.

LEGO sells an element - a design in a colour - and so a part of these models is
one: a brick 1 x 2 in Medium Stone Grey is a part of its own, with its own line
on the bill of materials and its own question to a store. The colours are
LEGO's, as //pub/universe/lego declares them (from LDraw's colour table), and
this package names the few it uses by aliases of its own ('colors:' in
partcad.yaml): ':stone' rather than '//pub/universe/lego:Medium Stone Grey'.

A generator names each part it places in a colour by the alias, and is given
back the name of the part that is that design in that colour: an 'enrich' of
the LDraw part with its 'color' fixed, declared in partcad.yaml in a block the
generator writes ('Variants.block'). A shortcut - an assembly of parts, a wheel
with its tyre - is an assembly in a colour the same way: it passes the colour
on to its parts that take it, and its tyre stays the black rubber its own file
says it is.

A link that set the colour itself ('params:') would draw the same picture, and
is not how these are written: CMF set on a link draws the assembly rather than
specifying what is in it, and these parts are things to be bought, in the
colour they are bought in (see "CMF" in the PartCAD documentation).
"""

# The aliases, as partcad.yaml declares them: each LEGO's own name for the
# colour, which LDraw's code beside it is.
ALIASES = {
    "black": ("Black", "0"),
    "green": ("Dark Green", "2"),
    "red": ("Bright Red", "4"),
    "stone": ("Medium Stone Grey", "71"),
    "dark-stone": ("Dark Stone Grey", "72"),
    "dark-red": ("New Dark Red", "320"),
}


class Variants:
    """The designs in colours one model uses, and the 'partcad.yaml' declarations of them."""

    def __init__(self, model):
        self.model = model
        self.parts = {}
        self.assemblies = {}

    def name(self, kind, ref, alias):
        """The name of the part (or, for 'assembly', the assembly) that is 'ref' in colour 'alias'."""
        if alias not in ALIASES:
            raise SystemExit("%s: no such colour among %s" % (alias, ", ".join(sorted(ALIASES))))
        design = ref.rsplit(":", 1)[1]
        variant = "%s/%s-%s" % (self.model, design, alias)
        (self.assemblies if kind == "assembly" else self.parts)[variant] = (ref, alias)
        return variant

    def block(self, kind, begin, end, indent="  "):
        """The declarations of every variant of 'kind' named so far, between 'begin' and 'end'."""
        found = self.assemblies if kind == "assembly" else self.parts
        lines = [begin]
        for variant in sorted(found):
            ref, alias = found[variant]
            name, code = ALIASES[alias]
            lines.append("%s%s:" % (indent, variant))
            lines.append("%s  type: enrich" % indent)
            lines.append("%s  source: %s" % (indent, ref))
            lines.append("%s  desc: \"%s in %s (LDraw %s)\"" % (indent, ref.rsplit(":", 1)[1], name, code))
            lines.append("%s  with:" % indent)
            lines.append('%s    color: ":%s"' % (indent, alias))
        lines.append(end)
        return "\n".join(lines)
