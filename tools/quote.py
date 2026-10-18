#!/usr/bin/env python3
"""Ask every LEGO store about every model here, and say what each would sell.

For each model and each store under //pub/universe/lego this runs

    pc -q supply quote --json --provider <store> <model>

and prints what came back: the price of the parts the store has, how many of
the model's distinct parts and pieces that is, and which parts it does not
have. A store PartCAD could not get a quote from - one that needs credentials
it was not given, or one that turned the request away - says why on the line
below it, from what 'pc' wrote to its error stream.

Run it from the repository root, with 'pc' on the PATH:

    python tools/quote.py                     # every model at every store
    python tools/quote.py castle              # one model
    python tools/quote.py --store pick-a-brick f1
    python tools/quote.py //pub/examples/lego:castle   # from another package
    python tools/quote.py --extra-param '//pub/universe/lego/pick-a-brick:pick-a-brick.color=Medium Stone Grey' castle
"""

import argparse
import json
import subprocess
import sys

MODELS = ["castle", "f1"]
STORES = ["rebrickable", "pick-a-brick", "bricklink", "brickowl"]


def provider(store):
    return "//pub/universe/lego/%s:%s" % (store, store)


def quote(model, store, extra_params):
    command = ["pc", "--no-ansi", "-q"]
    for extra in extra_params:
        command += ["--extra-param", extra]
    target = model if ":" in model else ":" + model
    command += ["supply", "quote", "--json", "--provider", provider(store), target]
    run = subprocess.run(command, capture_output=True, text=True)
    try:
        return json.loads(run.stdout), run.stderr
    except ValueError:
        return None, run.stderr or run.stdout


def summary(model, store, answer, errors):
    if answer is None:
        return "%-8s %-13s no answer" % (model, store), errors.strip().splitlines()[-1:] or []
    bought, missing = {}, {}
    price, currency = None, None
    for supplier, entry in answer.items():
        parts = {p["name"].split(":", 1)[1]: p["count"] for p in (entry.get("cart") or {}).get("parts", {}).values()}
        if supplier and entry.get("result"):
            bought.update(parts)
            price, currency = entry["result"].get("price"), entry["result"].get("currency")
        else:
            missing.update(parts)
    distinct = len(bought) + len(missing)
    pieces = sum(bought.values()) + sum(missing.values())
    line = "%-8s %-13s %10s %-3s  %2d of %2d parts, %4d of %4d pieces" % (
        model,
        store,
        "%.2f" % price if price is not None else "-",
        currency or "",
        len(bought),
        distinct,
        sum(bought.values()),
        pieces,
    )
    notes = []
    if missing:
        notes.append("not available: " + ", ".join("%s x%d" % item for item in sorted(missing.items())))
    if not bought:
        # Why the store had nothing, where PartCAD logged it. A store that has
        # not been set up says so quietly, so that every LEGO part can name it.
        said = [text for text in errors.splitlines() if "ERROR" in text and "not available from" not in text]
        notes += said[-1:] or ["nothing available: if this store has not been set up, its README says how"]
    return line, notes


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("models", nargs="*", default=MODELS)
    parser.add_argument("--store", action="append", choices=STORES, help="ask this store only (repeatable)")
    parser.add_argument("--extra-param", action="append", default=[], help="passed to pc as it is")
    args = parser.parse_args()
    for model in args.models:
        for store in args.store or STORES:
            line, notes = summary(model, store, *quote(model, store, args.extra_param))
            print(line)
            for note in notes:
                print("    " + note)
            sys.stdout.flush()


if __name__ == "__main__":
    main()
