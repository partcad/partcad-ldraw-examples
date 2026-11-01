"""LDraw's colours, for the generators to say what colour each part is placed in.

A part of //pub/universe/lego/ldraw has no colour of its own - LDraw draws
nearly every part in '16', the colour of whatever places it - so a model says
what colour each of its parts is, on the link that places it:

    - part: //pub/universe/lego/ldraw/Brick:3005
      name: w_c0_0
      color: "#969696" # LDraw 71, Light_Bluish_Grey

The generators name a colour by its LDraw code, the way LDraw and every LEGO
colour chart do, and the value is LDraw's own: partcad-ldraw's index carries the
library's colour table ('colors.json', read from LDConfig.ldr), and that is what
is read here, so a model and the shortcuts partcad-ldraw serves (a wheel's
tyre, the lids of a battery box) are coloured from the one table.

The index is the one tools/gen_f1.py reads its ports from: a checkout of
partcad-ldraw beside this one, or the file LDRAW_INDEX names.
"""

import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX = os.environ.get("LDRAW_INDEX") or os.path.join(os.path.dirname(ROOT), "partcad-ldraw", "parts-index.zip")
MEMBER = "colors.json"

# The colours these models are built in, by the name LDConfig.ldr gives each.
BLACK = "0"
GREEN = "2"
RED = "4"
LIGHT_BLUISH_GREY = "71"
DARK_BLUISH_GREY = "72"
DARK_RED = "320"

_table = None


def table(path=INDEX):
    """{LDraw colour code: [name, "#RRGGBB" or "#RRGGBBAA"]}, from partcad-ldraw's index."""
    global _table
    if _table is None:
        try:
            with zipfile.ZipFile(path) as z:
                _table = json.loads(z.read(MEMBER))
        except (OSError, KeyError) as e:
            raise SystemExit(
                "%s: no LDraw colour table (%s) - this needs partcad-ldraw's index with its '%s' in it, "
                "in a checkout beside this one or where LDRAW_INDEX says" % (path, e, MEMBER)
            )
    return _table


def color_line(code, indent):
    """The 'color:' line of a link that places its part in LDraw colour 'code', named beside it."""
    name, value = table()[code]
    return '%scolor: "%s" # LDraw %s, %s' % (indent, value, code, name)
