"""B06 ontology v1.1: SPARQL competency questions and golden inference examples."""
import json
from pathlib import Path

import pytest

pytest.importorskip("rdflib")

from ml import ontology_graph as og  # noqa: E402
from ml import ontology_rules as rules  # noqa: E402
from ontology import demo_inference as demo  # noqa: E402


@pytest.fixture(scope="module")
def outs():
    return [(e, demo.run_example(e)) for e in demo.EXAMPLES]


def test_golden_examples_match(outs):
    golden = json.loads(demo.GOLDEN.read_text(encoding="utf-8"))
    assert golden["rules_version"] == rules.RULES_VERSION
    current = json.loads(json.dumps([demo.summarise(e, o) for e, o in outs], sort_keys=True))
    assert current == golden["examples"], "rules changed: review, then run `python -m ontology.demo_inference --write`"


def test_three_examples_cover_missing_data(outs):
    assert len(outs) >= 3
    missing = outs[2][1]
    assert all(f["status"] == "unknown" for f in missing["result"]["facts"])
    assert missing["signals"] == [] and missing["explanation"]["learned_price_effects"] == []


def test_competency_questions(outs):
    g = og.build_graph({"listing_id": e["id"], "result": o["result"], "learned": e["learned"]} for e, o in outs)
    cq1 = {r["listing"] for r in og.answer(g, "CQ1")}
    assert any(x.endswith("0001") for x in cq1)
    assert any(r.get("rule") == "PRICE-OUTSIDE-INTERVAL" for r in og.answer(g, "CQ2"))
    assert {r["rule"] for r in og.answer(g, "CQ3")} >= {"GEO-DISTRICT-SUPPORT", "FEAT-AREA-PLAUSIBILITY"}
    assert all(r["listing"].endswith("0003") for r in og.answer(g, "CQ4"))
    assert og.separation_holds(g)


def test_separation_check_detects_violation(outs):
    from rdflib import RDF
    g = og.build_graph([])
    g.add((og.EX.X, RDF.type, og.EX.InferredFact))
    g.add((og.EX.X, RDF.type, og.EX.LearnedPriceEffect))
    assert not og.separation_holds(g)


def test_price_only_high_label_is_gone():
    g = og.load_ontology()
    assert not g.query('ASK { ?s ?p "HIGH" }').askAnswer
    assert og.answer(g, "CQ2") == [{"listing": "Listing_002"}]


def test_fit_district_support_cli(tmp_path):
    import pandas as pd
    from ml import fit_district_support as cli
    snap = tmp_path / "snap"
    snap.mkdir()
    pd.DataFrame({"latitude": [40.18] * 3, "longitude": [44.51] * 3, "district": ["kentron"] * 3}).to_csv(
        snap / "train.csv", index=False)
    (snap / "manifest.json").write_text(json.dumps({"dataset_version": "v-test", "snapshot_sha256": "abc"}))
    out = tmp_path / "o" / "ds.json"
    assert cli.main(["--snapshot", str(snap), "--out", str(out)]) == 0
    loaded = rules.DistrictSupport.from_json(json.loads(out.read_text()))
    assert loaded.reference_version == "v-test" and loaded.n_reference == 3
    assert cli.main(["--snapshot", str(tmp_path), "--out", str(out)]) == 2
