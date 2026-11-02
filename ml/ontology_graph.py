"""B06: materialise rule results as RDF (ontology v1.1) and answer competency questions with SPARQL.

Requires ``rdflib`` (ml/requirements-train.txt). The graph is derived from ``ontology_rules`` output; it
adds a queryable view, not new logic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace

from ml import ontology_rules as rules

EX = Namespace("http://example.org/fairrent#")
ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "ontology" / "real_estate_ontology.ttl"

CQ = {
    "CQ1": ("Which listings have an inferred metro-proximity fact?",
            "PREFIX : <http://example.org/fairrent#> SELECT ?listing ?node WHERE { ?listing :hasInferredFact ?f . "
            "?f :derivedByRule ?r ; :hasStatus \"holds\" ; :aboutNode ?n . ?r :hasRuleId \"GEO-PROX-METRO\" . "
            "?n rdfs:label ?node } ORDER BY ?listing"),
    "CQ2": ("Which listings carry a price-anomaly finding?",
            "PREFIX : <http://example.org/fairrent#> SELECT ?listing ?rule WHERE { ?listing :flagsRisk ?e . "
            "?e a :PriceAnomalyFinding . OPTIONAL { ?e :derivedByRule/:hasRuleId ?rule } } ORDER BY ?listing"),
    "CQ3": ("Which listings have a description/location/feature consistency finding?",
            "PREFIX : <http://example.org/fairrent#> SELECT ?listing ?rule WHERE { ?listing :flagsRisk ?e . "
            "?e a :ConsistencyFinding ; :derivedByRule/:hasRuleId ?rule } ORDER BY ?listing ?rule"),
    "CQ4": ("Which facts could not be determined because data is missing?",
            "PREFIX : <http://example.org/fairrent#> SELECT ?listing ?rule ?reason WHERE { ?listing :hasInferredFact ?f . "
            "?f :hasStatus \"unknown\" ; :hasReason ?reason ; :derivedByRule/:hasRuleId ?rule } ORDER BY ?listing ?rule"),
}
# Disjointness check: nothing may be both a rule-derived fact and a learned price effect.
CQ_SEPARATION = ("PREFIX : <http://example.org/fairrent#> ASK { ?x a :InferredFact . ?x a :LearnedPriceEffect }")


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def load_ontology(path: Path = ONTOLOGY_PATH) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def _rule_node(g: Graph, rule_id: str):
    node = EX[f"Rule_{_slug(rule_id)}"]
    if (node, RDF.type, EX.Rule) not in g:
        g.add((node, RDF.type, EX.Rule))
        g.add((node, EX.hasRuleId, Literal(rule_id)))
        g.add((node, EX.hasRuleVersion, Literal(rules.RULES[rule_id].version)))
    return node


def add_listing(g: Graph, listing_id: str, result: Mapping[str, Any],
                learned: Optional[Sequence[Mapping[str, Any]]] = None) -> None:
    """Add one ``evaluate_listing`` result (and optional learned attributions) to ``g``."""
    lst = EX[f"Listing_{_slug(listing_id)}"]
    g.add((lst, RDF.type, EX.Listing))
    for fact in result["facts"]:
        node = EX[f"Fact_{_slug(listing_id)}_{_slug(fact['rule_id'])}"]
        g.add((node, RDF.type, EX.InferredFact))
        g.add((lst, EX.hasInferredFact, node))
        g.add((node, EX.derivedByRule, _rule_node(g, fact["rule_id"])))
        g.add((node, EX.hasStatus, Literal(fact["status"])))
        if fact.get("reason"):
            g.add((node, EX.hasReason, Literal(fact["reason"])))
        if fact.get("value_m") is not None:
            g.add((node, EX.hasDistanceMeters, Literal(float(fact["value_m"]), datatype=XSD.float)))
        if fact.get("subject"):
            subject = EX[f"Node_{_slug(fact['subject']['name'])}"]
            g.add((subject, RDF.type, EX.MetroStation if fact["rule_id"] == "GEO-PROX-METRO" else EX.InfrastructureNode))
            g.add((subject, RDFS.label, Literal(fact["subject"]["name"])))
            g.add((node, EX.aboutNode, subject))
        for line in fact["evidence"]:
            g.add((node, EX.hasEvidence, Literal(line)))
    for check in result["findings"]:
        spec = rules.RULES[check["rule_id"]]
        cls = EX.PriceAnomalyFinding if spec.category == "price_anomaly" else EX.ConsistencyFinding
        node = EX[f"Finding_{_slug(listing_id)}_{_slug(check['rule_id'])}"]
        g.add((node, RDF.type, cls))
        g.add((node, EX.hasCategory, Literal(spec.category)))
        g.add((node, EX.derivedByRule, _rule_node(g, check["rule_id"])))
        g.add((node, RDFS.comment, Literal(check["explanation"])))
        for line in check["evidence"]:
            g.add((node, EX.hasEvidence, Literal(line)))
        g.add((lst, EX.flagsRisk, node))
    if learned:
        estimate = EX[f"Estimate_{_slug(listing_id)}"]
        g.add((estimate, RDF.type, EX.ValuationEstimate))
        g.add((lst, EX.evaluatedBy, estimate))
        for item in learned:
            eff = EX[f"Effect_{_slug(listing_id)}_{_slug(item['feature'])}"]
            g.add((eff, RDF.type, EX.LearnedPriceEffect))
            g.add((eff, EX.hasFeature, Literal(item["feature"])))
            g.add((eff, EX.hasImpactPct, Literal(float(item["impact_pct"]), datatype=XSD.float)))
            g.add((eff, EX.hasDirection, Literal(item["direction"])))
            g.add((estimate, EX.hasLearnedEffect, eff))


def build_graph(items: Iterable[Mapping[str, Any]], *, with_ontology: bool = True) -> Graph:
    """``items``: dicts with ``listing_id``, ``result`` (evaluate_listing) and optional ``learned``."""
    g = load_ontology() if with_ontology else Graph()
    for item in items:
        add_listing(g, item["listing_id"], item["result"], item.get("learned"))
    return g


def answer(g: Graph, key: str) -> list:
    rows = []
    for row in g.query(CQ[key][1]):
        rows.append({str(k): str(v).rsplit("#", 1)[-1] for k, v in row.asdict().items()})
    return rows


def separation_holds(g: Graph) -> bool:
    return not bool(g.query(CQ_SEPARATION).askAnswer)
