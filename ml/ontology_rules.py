"""[B06] Versioned ontology rules, evidence and valuation explanations.

Pure Python (no pandas/CatBoost). Geographic constants come from the A05 registry
(``data_pipeline.geography``, imported lazily), the interval/``price_status`` logic from B05.

Three kinds of output are kept strictly apart:

* **inferred facts**       -- deterministic consequences of rules (``GEO-PROX-*``), e.g. "the
  nearest metro station is 320 m away". They carry evidence and never a price effect;
* **consistency findings** -- checks between a description, structured fields and coordinates
  (``DESC-*``, ``FEAT-*``, ``GEO-DISTRICT-SUPPORT``) and the calibrated-interval check
  ``PRICE-OUTSIDE-INTERVAL``. A finding is *review evidence*, never proof of fraud;
* **learned price effects** -- feature attributions of the trained model. They are passed in by the
  caller, validated and reported in their own section; this module never derives or edits them.

Rule thresholds are provisional (as in ml/CONTRACT.md) and every rule has its own version. Changing a
parameter requires bumping both the rule version and ``RULES_VERSION``.
"""

from __future__ import annotations

import math
import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ml import intervals as iv

RULES_VERSION = "b06-rules-v1.0.0"
RULE_ENGINE_VERSION = RULES_VERSION          # value for the contract's versions.rule_engine_version

CATEGORY_PRICE_ANOMALY = "price_anomaly"
CATEGORY_RISK_EVIDENCE = "risk_evidence"

FACT_STATUSES = ("holds", "does_not_hold", "unknown")
CHECK_STATUSES = ("flagged", "clear", "unknown")

_SIGNAL_NAMESPACE = uuid.UUID("6f1c2a9e-4b7d-4e55-9a3c-0b6c1f0d2a11")
_SIGNAL_NOTE = "This is review evidence, not a finding of fraud."


# ------------------------------------------------------------------------------- registry


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    version: str
    kind: str                       # inferred_fact | consistency_check | price_anomaly
    title: str
    description: str
    parameters: Dict[str, Any]
    limitations: Tuple[str, ...]
    category: Optional[str] = None  # contract RiskSignal category for rules that raise signals


_STRAIGHT = ("Straight-line (Haversine) distance, not a walking route.",
             "Listing coordinates are approximate map pins (A05), so distances carry tens of metres of error.")

RULES: Dict[str, RuleSpec] = {r.rule_id: r for r in (
    RuleSpec("GEO-PROX-METRO", "1", "inferred_fact", "Near a metro station",
             "The nearest registered metro station is within near_m metres of the property.",
             {"near_m": 500.0, "extended_m": 1000.0},
             _STRAIGHT + ("Thresholds are provisional; the price effect of proximity is measured separately "
                          "(ml/validate_proximity.py), never assumed by this rule.",)),
    RuleSpec("GEO-PROX-UNIVERSITY", "1", "inferred_fact", "Near a university campus",
             "The nearest registered university campus point is within near_m metres of the property.",
             {"near_m": 1000.0, "extended_m": 2000.0},
             _STRAIGHT + ("The A05 university list is a starter set of four main campuses, not a census.",)),
    RuleSpec("GEO-PROX-CENTER", "1", "inferred_fact", "Close to the city-centre anchor",
             "The property is within near_m metres of the Republic Square reference point.",
             {"near_m": 1500.0, "extended_m": 3000.0},
             _STRAIGHT + ("The anchor is one reference point, not the Kentron district.",)),
    RuleSpec("GEO-DISTRICT-SUPPORT", "1", "consistency_check", "Stated district is supported by the location",
             "Flags a property whose stated district never occurs among the reference listings in the 3x3 grid "
             "block around its coordinates, when at least min_reference_listings reference listings exist there.",
             {"cell_size_deg": 0.01, "min_reference_listings": 20},
             ("Not a boundary test: A05 has no district polygons, so this compares the label with where other "
              "listings with that label are located.",
              "Either the label or the map pin can be the wrong one; the check cannot tell which.",
              "Reference listings carry the same label noise as the listing being checked."),
             CATEGORY_RISK_EVIDENCE),
    RuleSpec("DESC-AREA-MATCH", "1", "consistency_check", "Description area equals the structured area",
             "Flags a difference between the area quoted in the text and area_sqm larger than "
             "max(abs_tol_sqm, rel_tol x area_sqm).",
             {"abs_tol_sqm": 0.5, "rel_tol": 0.02},
             ("Meaningful only when the text and the field come from different sources; the current list.am "
              "scrape parses fields from the title, so it almost never fires there.",),
             CATEGORY_RISK_EVIDENCE),
    RuleSpec("DESC-ROOMS-MATCH", "1", "consistency_check", "Description room count equals the structured count",
             "Flags a room count in the text that differs from the structured rooms value.", {},
             ("Same source caveat as DESC-AREA-MATCH.",), CATEGORY_RISK_EVIDENCE),
    RuleSpec("DESC-FLOOR-MATCH", "1", "consistency_check", "Description floor equals the structured floor",
             "Flags a 'floor/total floors' pair in the text that differs from the structured values.", {},
             ("Same source caveat as DESC-AREA-MATCH.",), CATEGORY_RISK_EVIDENCE),
    RuleSpec("DESC-DISTRICT-MATCH", "1", "consistency_check", "Description district equals the structured district",
             "Flags a district named at the end of a text phrase that differs from the structured district.", {},
             ("Only registry district names (Armenian and English, with locative endings) are recognised; "
              "ambiguous or missing mentions yield 'unknown', never a flag.",
              "Same source caveat as DESC-AREA-MATCH."), CATEGORY_RISK_EVIDENCE),
    RuleSpec("FEAT-AREA-PLAUSIBILITY", "1", "consistency_check", "Area is plausible for the room count",
             "Flags an area outside [min_area_sqm, max_area_sqm] or an area per room outside "
             "[min_sqm_per_room, max_sqm_per_room].",
             {"min_area_sqm": 10.0, "max_area_sqm": 600.0, "min_sqm_per_room": 8.0, "max_sqm_per_room": 150.0},
             ("Bounds are conservative domain limits, not fitted to labels.",
              "Typically a parsing or typing error (for example a thousands separator), not an attempt to mislead."),
             CATEGORY_RISK_EVIDENCE),
    RuleSpec("PRICE-OUTSIDE-INTERVAL", "1", "price_anomaly", "Asking price outside the calibrated interval",
             "Flags an asking price above the upper or below the lower bound of the B05 calibrated interval.",
             {"interval_levels": [0.95]},
             ("A price anomaly alone is never evidence of fraud (docs/business-rules.md).",
              "By construction about (1 - coverage) of ordinary listings fall outside a calibrated interval.",
              "Requires a calibrated interval; with none the check is 'unknown'."),
             CATEGORY_PRICE_ANOMALY),
)}


def registry() -> List[Dict[str, Any]]:
    """Machine-readable rule registry (what the backend and the ontology export)."""
    return [{"rule_id": r.rule_id, "version": r.version, "kind": r.kind, "title": r.title,
             "description": r.description, "parameters": dict(r.parameters),
             "limitations": list(r.limitations), "category": r.category, "rules_version": RULES_VERSION}
            for r in RULES.values()]


# -------------------------------------------------------------------------------- helpers


def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _fmt(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _result(rule_id: str, status: str, evidence: Sequence[str], *, reason: Optional[str] = None,
            **extra: Any) -> Dict[str, Any]:
    spec = RULES[rule_id]
    out = {"rule_id": rule_id, "rule_version": spec.version, "status": status,
           "evidence": list(evidence), "reason": reason, "limitations": list(spec.limitations)}
    out.update(extra)
    return out


def _geography() -> Any:
    try:
        from data_pipeline import geography
        return geography
    except Exception:            # the backend image may not ship data_pipeline
        return None


def _valid_point(lat: Optional[float], lon: Optional[float]) -> bool:
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def _district_id(value: Any) -> Optional[str]:
    geo = _geography()
    if geo is None or not isinstance(value, str):
        return None
    canonical = value.strip()
    if canonical in geo.DISTRICTS:          # registry keys such as "nor-nork" are accepted as they are
        return canonical
    return geo.normalize_district(value)


# -------------------------------------------------------------------------- proximity facts

_PROXIMITY = (  # (rule_id, fact code, distance key, nearest-id key, registry listing, subject label)
    ("GEO-PROX-METRO", "near_metro", "distance_metro_m", "nearest_metro_id", "METRO_STATIONS", "metro station"),
    ("GEO-PROX-UNIVERSITY", "near_university", "distance_university_m", "nearest_university_id",
     "UNIVERSITIES", "university campus"),
    ("GEO-PROX-CENTER", "central_location", "distance_center_m", None, None, "city-centre anchor"),
)


def proximity_facts(latitude: Any = None, longitude: Any = None, *, distances: Optional[Mapping[str, Any]] = None,
                    coordinate_confidence: Optional[str] = None) -> List[Dict[str, Any]]:
    """Inferred proximity facts. With valid coordinates they are computed from the A05 registry (single
    source of truth, nearest station named); otherwise the supplied ``distances`` are used and no
    station is named; with neither, each fact is ``unknown`` with a reason (never silently omitted)."""
    lat, lon = _num(latitude), _num(longitude)
    geo = _geography()
    computed: Dict[str, Any] = {}
    if _valid_point(lat, lon) and geo is not None:
        computed = geo.proximity_features(lat, lon)
    supplied = distances or {}
    facts: List[Dict[str, Any]] = []
    for rule_id, code, dist_key, id_key, registry_attr, label in _PROXIMITY:
        spec = RULES[rule_id]
        near_m, ext_m = spec.parameters["near_m"], spec.parameters["extended_m"]
        value = _num(computed.get(dist_key))
        origin = "computed from coordinates (A05 registry)"
        if value is None:
            value, origin = _num(supplied.get(dist_key)), "supplied by the caller"
        if value is None:
            if lat is None or lon is None:
                reason = "missing_coordinates"
            elif not _valid_point(lat, lon):
                reason = "invalid_coordinates"
            elif geo is None:
                reason = "geography_registry_unavailable"
            else:
                reason = "distance_unavailable"
            facts.append(_result(rule_id, "unknown", [f"{dist_key}=null"], reason=reason, code=code,
                                 tier=None, value_m=None, subject=None))
            continue
        subject = None
        nearest = computed.get(id_key) if id_key else None
        if nearest and geo is not None and registry_attr:
            for row in getattr(geo, registry_attr):
                if row[0] == nearest:
                    subject = {"id": row[0], "name": row[1]}
        elif code == "central_location":
            subject = {"id": "republic-square", "name": "Republic Square"}
        tier = "near" if value <= near_m else "extended" if value <= ext_m else "far"
        evidence = [f"{dist_key}={_fmt(value)} ({origin}; straight-line)"]
        if subject:
            evidence.append(f"nearest_{'metro' if code == 'near_metro' else 'university' if code == 'near_university' else 'anchor'}"
                            f"={subject['name']} ({subject['id']})")
        evidence.append(f"near_m={_fmt(near_m)}")
        evidence.append(f"extended_m={_fmt(ext_m)}")
        if geo is not None:
            evidence.append(f"geography_version={geo.GEOGRAPHY_VERSION}")
        evidence.append(f"coordinate_confidence={coordinate_confidence or 'unknown'}")
        facts.append(_result(rule_id, "holds" if tier == "near" else "does_not_hold", evidence, code=code,
                             tier=tier, value_m=round(value, 1), subject=subject))
    return facts


# --------------------------------------------------------------------- district support


class DistrictSupport:
    """Reference table: how many reference listings of each district fall in each ~1 km grid cell.

    Fitted on the **training** split only and stored as aggregate counts (no raw coordinates).
    """

    def __init__(self, cells: Dict[str, Dict[str, int]], *, cell_size_deg: float, min_reference_listings: int,
                 reference_version: str = "unversioned", n_reference: Optional[int] = None):
        self.cells = cells
        self.cell_size_deg = float(cell_size_deg)
        self.min_reference_listings = int(min_reference_listings)
        self.reference_version = reference_version
        self.n_reference = int(n_reference if n_reference is not None
                               else sum(sum(c.values()) for c in cells.values()))

    @classmethod
    def fit(cls, rows: Iterable[Mapping[str, Any]], *, reference_version: str = "unversioned",
            cell_size_deg: Optional[float] = None, min_reference_listings: Optional[int] = None) -> "DistrictSupport":
        params = RULES["GEO-DISTRICT-SUPPORT"].parameters
        size = float(cell_size_deg if cell_size_deg is not None else params["cell_size_deg"])
        minimum = int(min_reference_listings if min_reference_listings is not None else params["min_reference_listings"])
        cells: Dict[str, Dict[str, int]] = {}
        for row in rows:
            lat, lon = _num(row.get("latitude")), _num(row.get("longitude"))
            district = _district_id(row.get("district"))
            if district is None or not _valid_point(lat, lon):
                continue
            key = f"{math.floor(lat / size)},{math.floor(lon / size)}"
            cells.setdefault(key, {})[district] = cells.setdefault(key, {}).get(district, 0) + 1
        return cls(cells, cell_size_deg=size, min_reference_listings=minimum, reference_version=reference_version)

    def block_counts(self, lat: float, lon: float) -> Dict[str, int]:
        ix, iy = math.floor(lat / self.cell_size_deg), math.floor(lon / self.cell_size_deg)
        counts: Dict[str, int] = {}
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for district, n in self.cells.get(f"{ix + dx},{iy + dy}", {}).items():
                    counts[district] = counts.get(district, 0) + n
        return counts

    def check(self, latitude: Any, longitude: Any, district: Any, *, exclude_self: bool = False) -> Dict[str, Any]:
        """``exclude_self=True`` when the listing is itself part of the reference data (leave-one-out)."""
        rid = "GEO-DISTRICT-SUPPORT"
        lat, lon = _num(latitude), _num(longitude)
        stated = _district_id(district)
        if lat is None or lon is None:
            return _result(rid, "unknown", ["coordinates=null"], reason="missing_coordinates")
        if not _valid_point(lat, lon):
            return _result(rid, "unknown", [f"coordinates=({lat},{lon})"], reason="invalid_coordinates")
        if stated is None:
            return _result(rid, "unknown", [f"stated_district={district!r}"], reason="district_unresolved")
        counts = self.block_counts(lat, lon)
        if exclude_self and counts.get(stated, 0) > 0:
            counts[stated] -= 1
        total = sum(counts.values())
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        evidence = [f"stated_district={stated}", f"reference_listings_nearby={total}",
                    "nearby_districts=" + (", ".join(f"{d}:{n}" for d, n in top) or "none"),
                    f"stated_district_nearby={counts.get(stated, 0)}",
                    f"cell_size_deg={self.cell_size_deg}", f"min_reference_listings={self.min_reference_listings}",
                    f"reference_version={self.reference_version}"]
        if total < self.min_reference_listings:
            return _result(rid, "unknown", evidence, reason="sparse_reference_data")
        if counts.get(stated, 0) == 0:
            leader = top[0][0]
            return _result(rid, "flagged", evidence,
                           explanation=(f"The listing states district '{stated}', but none of the {total} reference "
                                        f"listings around its coordinates have that district (mostly '{leader}'). "
                                        f"Either the district label or the map pin may be wrong. {_SIGNAL_NOTE}"))
        return _result(rid, "clear", evidence)

    def to_json(self) -> Dict[str, Any]:
        return {"rule_id": "GEO-DISTRICT-SUPPORT", "rule_version": RULES["GEO-DISTRICT-SUPPORT"].version,
                "rules_version": RULES_VERSION, "cell_size_deg": self.cell_size_deg,
                "min_reference_listings": self.min_reference_listings, "reference_version": self.reference_version,
                "n_reference": self.n_reference, "cells": self.cells, "fitted_on": "train split only"}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "DistrictSupport":
        if payload.get("rule_id") != "GEO-DISTRICT-SUPPORT":
            raise ValueError("not a GEO-DISTRICT-SUPPORT reference table")
        return cls({k: {d: int(n) for d, n in v.items()} for k, v in payload["cells"].items()},
                   cell_size_deg=payload["cell_size_deg"], min_reference_listings=payload["min_reference_listings"],
                   reference_version=payload.get("reference_version", "unversioned"),
                   n_reference=payload.get("n_reference"))


# --------------------------------------------------------------- description consistency

_AREA_RE = re.compile(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*(?:քմ|քառ\.?\s*մ|sq\.?\s*m|m2|m²)", re.I)
_ROOMS_RE = re.compile(r"(\d+)[\s\-]*(?:սենյականոց|սենյակային|room)", re.I)
_FLOOR_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*(?:հարկ|floor|fl\b)", re.I)
_LOCATIVE_SUFFIXES = ("յում", "ում", "")


def _parse_area(text: str) -> Optional[float]:
    match = _AREA_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    raw = raw.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw) else raw.replace(",", ".")
    return _num(raw)


def district_from_text(text: str) -> Tuple[Optional[str], str]:
    """The district named at the end of a text phrase, as (district_id|None, 'found'|'none'|'ambiguous').

    Only phrases before the one that quotes the area are inspected (the street/district part of a list.am
    title); the district must end the phrase, optionally with an Armenian locative ending."""
    geo = _geography()
    if geo is None or not text:
        return None, "none"
    found = set()
    for segment in text.split(","):
        if _AREA_RE.search(segment):
            break
        folded = unicodedata.normalize("NFKC", segment).casefold().strip()
        for district_id, aliases in geo.DISTRICTS.items():
            for alias in aliases:
                needle = unicodedata.normalize("NFKC", alias).casefold()
                for suffix in _LOCATIVE_SUFFIXES:
                    if re.search(r"(?<!\w)" + re.escape(needle + suffix) + r"$", folded):
                        found.add(district_id)
    if not found:
        return None, "none"
    return (next(iter(found)), "found") if len(found) == 1 else (None, "ambiguous")


def description_checks(text: Optional[str], *, area_sqm: Any = None, rooms: Any = None, floor: Any = None,
                       total_floors: Any = None, district: Any = None) -> List[Dict[str, Any]]:
    """Compare what the description says with the structured fields. Missing data gives ``unknown``."""
    out: List[Dict[str, Any]] = []
    text = text if isinstance(text, str) else ""
    area, rooms_v = _num(area_sqm), _num(rooms)
    floor_v, total_v = _num(floor), _num(total_floors)

    spec = RULES["DESC-AREA-MATCH"].parameters
    text_area = _parse_area(text)
    if text_area is None or area is None:
        out.append(_result("DESC-AREA-MATCH", "unknown",
                           [f"text_area_sqm={'null' if text_area is None else _fmt(text_area)}",
                            f"area_sqm={'null' if area is None else _fmt(area)}"],
                           reason="no_area_in_text" if text_area is None else "area_field_missing"))
    else:
        tolerance = max(spec["abs_tol_sqm"], spec["rel_tol"] * area)
        evidence = [f"text_area_sqm={_fmt(text_area)}", f"area_sqm={_fmt(area)}", f"tolerance_sqm={_fmt(tolerance)}"]
        if abs(text_area - area) > tolerance:
            out.append(_result("DESC-AREA-MATCH", "flagged", evidence, explanation=(
                f"The description quotes {_fmt(text_area)} m2 but the structured area is {_fmt(area)} m2. {_SIGNAL_NOTE}")))
        else:
            out.append(_result("DESC-AREA-MATCH", "clear", evidence))

    match = _ROOMS_RE.search(text)
    if match is None or rooms_v is None:
        out.append(_result("DESC-ROOMS-MATCH", "unknown",
                           [f"text_rooms={'null' if match is None else match.group(1)}",
                            f"rooms={'null' if rooms_v is None else _fmt(rooms_v)}"],
                           reason="no_rooms_in_text" if match is None else "rooms_field_missing"))
    else:
        text_rooms = int(match.group(1))
        evidence = [f"text_rooms={text_rooms}", f"rooms={_fmt(rooms_v)}"]
        if text_rooms != int(rooms_v):
            out.append(_result("DESC-ROOMS-MATCH", "flagged", evidence, explanation=(
                f"The description says {text_rooms} rooms but the structured room count is {_fmt(rooms_v)}. {_SIGNAL_NOTE}")))
        else:
            out.append(_result("DESC-ROOMS-MATCH", "clear", evidence))

    match = _FLOOR_RE.search(text)
    if match is None or floor_v is None or total_v is None:
        out.append(_result("DESC-FLOOR-MATCH", "unknown",
                           [f"text_floor={'null' if match is None else match.group(1) + '/' + match.group(2)}",
                            f"floor={'null' if floor_v is None else _fmt(floor_v)}",
                            f"total_floors={'null' if total_v is None else _fmt(total_v)}"],
                           reason="no_floor_in_text" if match is None else "floor_field_missing"))
    else:
        text_pair, field_pair = (int(match.group(1)), int(match.group(2))), (int(floor_v), int(total_v))
        evidence = [f"text_floor={text_pair[0]}/{text_pair[1]}", f"floor={field_pair[0]}/{field_pair[1]}"]
        if text_pair != field_pair:
            out.append(_result("DESC-FLOOR-MATCH", "flagged", evidence, explanation=(
                f"The description gives floor {text_pair[0]}/{text_pair[1]} but the structured values are "
                f"{field_pair[0]}/{field_pair[1]}. {_SIGNAL_NOTE}")))
        else:
            out.append(_result("DESC-FLOOR-MATCH", "clear", evidence))

    text_district, mention = district_from_text(text)
    stated = _district_id(district)
    if text_district is None or stated is None:
        reason = ("district_field_unresolved" if text_district is not None and stated is None
                  else "ambiguous_district_in_text" if mention == "ambiguous" else "no_district_in_text")
        out.append(_result("DESC-DISTRICT-MATCH", "unknown",
                           [f"text_district={text_district or 'null'}", f"stated_district={stated or 'null'}"],
                           reason=reason))
    else:
        evidence = [f"text_district={text_district}", f"stated_district={stated}"]
        if text_district != stated:
            out.append(_result("DESC-DISTRICT-MATCH", "flagged", evidence, explanation=(
                f"The description places the property in '{text_district}' but the structured district is "
                f"'{stated}'. {_SIGNAL_NOTE}")))
        else:
            out.append(_result("DESC-DISTRICT-MATCH", "clear", evidence))
    return out


def description_checks_by_source(sources: Mapping[str, Optional[str]], *, area_sqm: Any = None, rooms: Any = None,
                                 floor: Any = None, total_floors: Any = None,
                                 district: Any = None) -> List[Dict[str, Any]]:
    """Run ``description_checks`` on each text source (e.g. title, description) separately and merge per rule.

    A contradiction in *any* source is flagged, so an independent description cannot be masked by a title
    that matches the structured fields. Evidence lines are prefixed with ``source=<name>``."""
    per_source = {name: description_checks(text, area_sqm=area_sqm, rooms=rooms, floor=floor,
                                           total_floors=total_floors, district=district)
                  for name, text in sources.items()}
    merged: List[Dict[str, Any]] = []
    for index in range(len(next(iter(per_source.values()), []))):
        candidates = [(name, checks[index]) for name, checks in per_source.items()]
        flagged = [(n, c) for n, c in candidates if c["status"] == "flagged"]
        clear = [(n, c) for n, c in candidates if c["status"] == "clear"]
        chosen = flagged or clear or candidates
        base = dict(chosen[0][1])
        base["evidence"] = [f"source={n}; {e}" for n, c in chosen for e in c["evidence"]]
        if flagged:
            base["status"] = "flagged"
            base["explanation"] = " ".join(f"[{n}] {c['explanation']}" for n, c in flagged)
        elif clear:
            base["status"] = "clear"
        else:
            base["status"] = "unknown"
            base["reason"] = chosen[0][1].get("reason")
        merged.append(base)
    return merged


def area_plausibility(area_sqm: Any = None, rooms: Any = None) -> Dict[str, Any]:
    rid, p = "FEAT-AREA-PLAUSIBILITY", RULES["FEAT-AREA-PLAUSIBILITY"].parameters
    area, rooms_v = _num(area_sqm), _num(rooms)
    if area is None:
        return _result(rid, "unknown", ["area_sqm=null"], reason="area_missing")
    problems: List[str] = []
    evidence = [f"area_sqm={_fmt(area)}", f"rooms={'null' if rooms_v is None else _fmt(rooms_v)}",
                f"area_bounds_sqm=[{_fmt(p['min_area_sqm'])}, {_fmt(p['max_area_sqm'])}]"]
    if not p["min_area_sqm"] <= area <= p["max_area_sqm"]:
        problems.append(f"an area of {_fmt(area)} m2 is outside the plausible residential range")
    if rooms_v is not None and rooms_v >= 1:
        per_room = area / rooms_v
        evidence.append(f"sqm_per_room={_fmt(per_room)}")
        evidence.append(f"sqm_per_room_bounds=[{_fmt(p['min_sqm_per_room'])}, {_fmt(p['max_sqm_per_room'])}]")
        if not p["min_sqm_per_room"] <= per_room <= p["max_sqm_per_room"]:
            problems.append(f"{_fmt(per_room)} m2 per room for {_fmt(rooms_v)} room(s) is implausible")
    if problems:
        return _result(rid, "flagged", evidence, explanation=(
            "; ".join(problems).capitalize() + ". This usually indicates a typing or parsing error "
            f"(for example a thousands separator). {_SIGNAL_NOTE}"))
    return _result(rid, "clear", evidence)


# ----------------------------------------------------------------------- price anomaly


def price_anomaly_check(asking_price_usd: Any, interval: Optional[Mapping[str, Any]],
                        *, estimated_price_usd: Any = None) -> Dict[str, Any]:
    """Asking price versus the calibrated interval (B05). Never fraud evidence by itself."""
    rid = "PRICE-OUTSIDE-INTERVAL"
    status = iv.price_status(_num(asking_price_usd), interval)
    if status == "insufficient_data":
        return _result(rid, "unknown", [f"asking_price_usd={_fmt(_num(asking_price_usd)) if _num(asking_price_usd) is not None else 'null'}",
                                        "interval=null" if not interval or interval.get("lower_bound_usd") is None else "interval=present"],
                       reason="no_asking_price_or_no_calibrated_interval", price_status=status)
    asking = _num(asking_price_usd)
    evidence = [f"asking_price_usd={_fmt(asking)}", f"lower_bound_usd={_fmt(interval['lower_bound_usd'])}",
                f"upper_bound_usd={_fmt(interval['upper_bound_usd'])}",
                f"confidence_level={interval.get('confidence_level')}",
                f"calibration_version={interval.get('calibration_version')}"]
    if _num(estimated_price_usd) is not None:
        evidence.append(f"estimated_price_usd={_fmt(_num(estimated_price_usd))}")
    if status == "within_range":
        return _result(rid, "clear", evidence, price_status=status)
    side = "above" if status == "above_range" else "below"
    return _result(rid, "flagged", evidence, price_status=status, explanation=(
        f"The asking price (${_fmt(asking)}) is {side} the calibrated "
        f"{int(round(100 * float(interval.get('confidence_level') or 0)))}% interval for comparable properties "
        f"(${_fmt(interval['lower_bound_usd'])}-${_fmt(interval['upper_bound_usd'])}). A price anomaly alone is not "
        "evidence of fraud; asking prices are not signed rents."))


# --------------------------------------------------------------------- signal mapping


def to_risk_signal(check: Mapping[str, Any], *, listing_id: str, created_at: str) -> Dict[str, Any]:
    """Map a *flagged* check to the contract's ``RiskSignal``.

    ``id`` is a deterministic UUID over (listing, rule, rules version, evidence), so replaying the same
    evidence cannot create a second queue entry (docs/contract-semantics.md). ``created_at`` is supplied by
    the caller so results stay reproducible."""
    if check.get("status") != "flagged":
        raise ValueError("only flagged checks become signals")
    try:
        uuid.UUID(str(listing_id))
    except ValueError as error:
        raise ValueError("listing_id must be a UUID") from error
    if not (isinstance(created_at, str) and created_at.endswith("Z")):
        raise ValueError("created_at must be an ISO 8601 UTC timestamp ending in Z")
    spec = RULES[check["rule_id"]]
    if spec.category is None:
        raise ValueError(f"{spec.rule_id} does not raise signals")
    evidence = list(check["evidence"])
    key = "|".join([str(listing_id), spec.rule_id, RULES_VERSION, *evidence])
    return {"id": str(uuid.uuid5(_SIGNAL_NAMESPACE, key)), "listing_id": str(listing_id),
            "category": spec.category, "rule_id": spec.rule_id, "rules_version": RULES_VERSION,
            "evidence": evidence, "created_at": created_at, "explanation": check["explanation"]}


def evaluate_listing(listing: Mapping[str, Any], *, district_support: Optional[DistrictSupport] = None,
                     interval: Optional[Mapping[str, Any]] = None, in_reference: bool = False) -> Dict[str, Any]:
    """All listing-level rules. ``listing`` keys: latitude, longitude, district, area_sqm, rooms, floor,
    total_floors, title/description (text), asking_price_usd, coordinate_confidence, distances."""
    sources = {k: listing[k] for k in ("title", "description") if isinstance(listing.get(k), str)}
    facts = proximity_facts(listing.get("latitude"), listing.get("longitude"), distances=listing.get("distances"),
                            coordinate_confidence=listing.get("coordinate_confidence"))
    checks: List[Dict[str, Any]] = []
    if district_support is not None:
        checks.append(district_support.check(listing.get("latitude"), listing.get("longitude"),
                                             listing.get("district"), exclude_self=in_reference))
    checks.extend(description_checks_by_source(sources or {"text": None}, area_sqm=listing.get("area_sqm"), rooms=listing.get("rooms"),
                                     floor=listing.get("floor"), total_floors=listing.get("total_floors"),
                                     district=listing.get("district")))
    checks.append(area_plausibility(listing.get("area_sqm"), listing.get("rooms")))
    checks.append(price_anomaly_check(listing.get("asking_price_usd"), interval))
    return {"rules_version": RULES_VERSION, "facts": facts, "checks": checks,
            "findings": [c for c in checks if c["status"] == "flagged"]}


def listing_signals(result: Mapping[str, Any], *, listing_id: str, created_at: str) -> List[Dict[str, Any]]:
    """Contract ``RiskSignal`` objects for every flagged finding of ``evaluate_listing``."""
    return [to_risk_signal(f, listing_id=listing_id, created_at=created_at) for f in result["findings"]]


# ----------------------------------------------------------------------- explanation


def _validate_attributions(items: Optional[Sequence[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    out = []
    for item in items or []:
        if set(item) != {"feature", "impact_pct", "direction"}:
            raise ValueError(f"attribution must have exactly feature, impact_pct, direction: {dict(item)}")
        if not isinstance(item["feature"], str) or not item["feature"]:
            raise ValueError("attribution feature must be a non-empty string")
        impact = _num(item["impact_pct"])
        if impact is None or impact < 0:
            raise ValueError("attribution impact_pct must be a non-negative number")
        if item["direction"] not in ("positive", "negative", "neutral"):
            raise ValueError("attribution direction must be positive, negative or neutral")
        out.append({"feature": item["feature"], "impact_pct": impact, "direction": item["direction"]})
    return out


def explain_valuation(model_input: Mapping[str, Any], *, district_support: Optional[DistrictSupport] = None,
                      learned_attributions: Optional[Sequence[Mapping[str, Any]]] = None,
                      max_model_factors: int = 3) -> Dict[str, Any]:
    """Structured explanation for the backend, with three separate sections.

    * ``inferred_facts`` / ``consistency_checks`` come only from the rules and ``model_input``;
    * ``learned_price_effects`` is the caller's model attribution, validated and passed through untouched
      (this function never turns a rule fact into a price effect or the reverse);
    * ``factors`` is the contract ``Factor`` list: origin ``ontology`` for facts that hold or checks that
      flagged, origin ``model`` for the top learned effects. ``text`` is a readable summary.
    """
    learned = _validate_attributions(learned_attributions)
    facts = proximity_facts(model_input.get("latitude"), model_input.get("longitude"),
                            distances={k: model_input.get(k) for k in
                                       ("distance_metro_m", "distance_university_m", "distance_center_m")},
                            coordinate_confidence=model_input.get("coordinate_confidence"))
    checks: List[Dict[str, Any]] = []
    if district_support is not None:
        checks.append(district_support.check(model_input.get("latitude"), model_input.get("longitude"),
                                             model_input.get("district")))
    checks.append(area_plausibility(model_input.get("area_sqm"), model_input.get("rooms")))

    factors: List[Dict[str, Any]] = []
    for fact in facts:
        if fact["status"] == "holds":
            subject = f" ({fact['subject']['name']})" if fact.get("subject") else ""
            factors.append({"code": fact["code"], "origin": "ontology", "evidence": list(fact["evidence"]),
                            "explanation": f"{RULES[fact['rule_id']].title}: {_fmt(fact['value_m'])} m{subject}, "
                                           "an inferred location fact, not a price effect."})
    for check in checks:
        if check["status"] == "flagged":
            factors.append({"code": check["rule_id"].lower().replace("-", "_"), "origin": "ontology",
                            "evidence": list(check["evidence"]), "explanation": check["explanation"]})
    for item in sorted(learned, key=lambda a: (-a["impact_pct"], a["feature"]))[:max_model_factors]:
        factors.append({"code": item["feature"], "origin": "model", "evidence": [
            f"impact_pct={_fmt(item['impact_pct'])}", f"direction={item['direction']}"],
            "explanation": f"Learned by the price model: {item['feature']} {_direction_phrase(item['direction'])} "
                           f"the estimate ({_fmt(item['impact_pct'])}% of the explained variation)."})

    holds = [f for f in facts if f["status"] == "holds"]
    unknown = [f for f in facts if f["status"] == "unknown"]
    parts = []
    if holds:
        label = {"GEO-PROX-METRO": "metro station", "GEO-PROX-UNIVERSITY": "university",
                 "GEO-PROX-CENTER": "city centre"}
        parts.append("Inferred by rules " + RULES_VERSION + ": " + "; ".join(
            f"{_fmt(f['value_m'])} m from the {label.get(f['rule_id'], 'landmark')}"
            + (f" ({f['subject']['name']})" if f.get("subject") else "") for f in holds) + " (straight-line).")
    else:
        parts.append("No proximity fact holds under rules " + RULES_VERSION + ".")
    if unknown:
        parts.append("Not determinable: " + ", ".join(f"{f['code']} ({f['reason']})" for f in unknown) + ".")
    flagged = [c for c in checks if c["status"] == "flagged"]
    if flagged:
        parts.append("Consistency findings: " + " ".join(c["explanation"] for c in flagged))
    if learned:
        top = sorted(learned, key=lambda a: (-a["impact_pct"], a["feature"]))[:max_model_factors]
        parts.append("Learned by the price model (separate from the rule facts above): " + ", ".join(
            f"{a['feature']} ({_direction_phrase(a['direction'])}, {_fmt(a['impact_pct'])}%)" for a in top) + ".")
    parts.append("Rule facts are not price effects; only the learned section quantifies influence on the estimate.")
    return {"rules_version": RULES_VERSION, "inferred_facts": facts, "consistency_checks": checks,
            "learned_price_effects": learned, "factors": factors, "text": " ".join(parts)}


def _direction_phrase(direction: str) -> str:
    return {"positive": "raises", "negative": "lowers", "neutral": "does not move"}[direction]
