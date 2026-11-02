"""B06 demo: three representative inferences (including a missing-data case) over ontology v1.1.

    python -m ontology.demo_inference            # print results
    python -m ontology.demo_inference --write    # regenerate ontology/examples/b06_inference_examples.json

Run from the repository root. Needs rdflib. The price interval and learned attributions below are
illustrative fixtures standing in for B05/B04 output; the rules and SPARQL are the real implementation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml import ontology_graph as og
from ml import ontology_rules as rules

GOLDEN = Path(__file__).resolve().parent / "examples" / "b06_inference_examples.json"
NOW = "2026-01-01T00:00:00Z"
INTERVAL = {"lower_bound_usd": 400.0, "upper_bound_usd": 700.0, "confidence_level": 0.9,
            "calibration_version": "demo-fixture"}
# Tiny reference table: Kentron listings around the Republic Square pin only.
SUPPORT = rules.DistrictSupport.fit(
    [{"latitude": 40.1776, "longitude": 44.5126, "district": "kentron"}] * 30, reference_version="demo-fixture")

EXAMPLES = [
    {"id": "11111111-1111-4111-8111-000000000001",
     "title": "Typical: near metro, price inside the calibrated interval",
     "listing": {"latitude": 40.1776, "longitude": 44.5126, "district": "kentron", "area_sqm": 65, "rooms": 2,
                 "asking_price_usd": 550, "title": "2 սենյականոց բնակարան, Կենտրոն, 65 քմ"},
     "learned": [{"feature": "area_sqm", "impact_pct": 52.0, "direction": "positive"},
                 {"feature": "distance_metro_m", "impact_pct": 11.5, "direction": "positive"}]},
    {"id": "11111111-1111-4111-8111-000000000002",
     "title": "Inconsistent: pin contradicts district, implausible area, price above interval",
     "listing": {"latitude": 40.1776, "longitude": 44.5126, "district": "arabkir", "area_sqm": 1670, "rooms": 3,
                 "asking_price_usd": 1800, "title": "3 սենյականոց բնակարան, Արաբկիր, 1670 քմ"},
     "learned": [{"feature": "area_sqm", "impact_pct": 70.0, "direction": "positive"}]},
    {"id": "11111111-1111-4111-8111-000000000003",
     "title": "Missing data: no coordinates, no area, no calibrated interval",
     "listing": {"district": "kentron", "rooms": 2, "asking_price_usd": 600, "title": "Բնակարան Կենտրոնում"},
     "learned": []},
]


def run_example(example: dict) -> dict:
    listing = example["listing"]
    interval = INTERVAL if example["id"].endswith(("1", "2")) else None
    result = rules.evaluate_listing(listing, district_support=SUPPORT, interval=interval)
    signals = rules.listing_signals(result, listing_id=example["id"], created_at=NOW)
    explanation = rules.explain_valuation(listing, district_support=SUPPORT, learned_attributions=example["learned"])
    return {"result": result, "signals": signals, "explanation": explanation}


def summarise(example: dict, out: dict) -> dict:
    return {"id": example["id"], "title": example["title"],
            "facts": {f["rule_id"]: f["status"] for f in out["result"]["facts"]},
            "checks": {c["rule_id"]: c["status"] for c in out["result"]["checks"]},
            "signals": sorted((s["category"], s["rule_id"]) for s in out["signals"]),
            "factor_origins": sorted({f["origin"] for f in out["explanation"]["factors"]}),
            "learned_price_effects": out["explanation"]["learned_price_effects"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    outs = [(e, run_example(e)) for e in EXAMPLES]
    summaries = [summarise(e, o) for e, o in outs]
    if args.write:
        GOLDEN.write_text(json.dumps({"rules_version": rules.RULES_VERSION, "examples": summaries},
                                     ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN}")
    graph = og.build_graph({"listing_id": e["id"], "result": o["result"], "learned": e["learned"]} for e, o in outs)
    for e, o in outs:
        print(f"\n== {e['title']}\n{o['explanation']['text']}")
        for s in o["signals"]:
            print(f"  signal {s['category']}/{s['rule_id']}")
    for key, (question, _) in og.CQ.items():
        print(f"\n{key}: {question}")
        for row in og.answer(graph, key):
            print("  ", row)
    print("\nInferred facts and learned price effects disjoint:", og.separation_holds(graph))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
