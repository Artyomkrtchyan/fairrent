"""B07: reproducible check that a package loads and answers the example requests with contract-valid output.

    python -m ml.verify_package --package artifacts/b07/<version>

Runs identically on a developer machine and inside the container (ml/docker/Dockerfile.verify). Exit code 0 only
when the package verifies, every example returns its expected status or error, and (when ``jsonschema`` is
installed) every assembled ``ValuationResponse`` validates against contracts/openapi.json.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ml import inference as inf

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = Path(__file__).resolve().parent / "examples" / "b07_requests.json"
OPENAPI = ROOT / "contracts" / "openapi.json"


def full_response(result: Dict[str, Any], model_input: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """The backend's side of the contract, for validation only: adds request_id, kind, cohort, freshness, price_status."""
    as_of = inf.parse_utc(model_input["as_of"])
    data = {k: result[k] for k in ("coordinates", "versions", "valuation_assessment", "observed_market_statistics",
                                   "ml_prediction_interval", "feature_attributions", "area_reference", "explanation")}
    age = result["observed_market_statistics"]["data_freshness_days"]
    data.update(
        request_id="req_verify_package", kind=inf.kind_for(result),
        cohort={"radius_m": model_input["radius_m"], "period_start": as_of.date().isoformat(),
                "period_end": as_of.date().isoformat(), "minimum_sample_size": inf.MIN_COMPARABLES,
                "selection_version": "verify-fixture",
                "duplicate_policy": "latest_observation_per_duplicate_group",
                "inventory_policy": "active_at_data_as_of"},
        freshness={"data_as_of": model_input["as_of"], "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "is_stale": age is None or age > inf.MAX_SOURCE_AGE_DAYS,
                   "max_age_days": inf.MAX_SOURCE_AGE_DAYS, "policy_version": "verify-fixture"},
        price_status="insufficient_data")
    return data


def _validator() -> Optional[Any]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        return None
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": "#/components/schemas/ValuationResponse", "components": spec["components"]},
                                format_checker=FormatChecker())


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", type=Path, help="package directory (default: $FAIRRENT_MODEL_PACKAGE)")
    args = parser.parse_args(argv)
    try:
        package = inf.load_package(args.package)
    except inf.PackageError as error:
        print(f"FAIL package: {error}")
        return 1
    m = package.manifest
    print(f"python {platform.python_version()} | package {m['package_version']} | model {m['model_version']} | "
          f"calibration {m['calibration_version']} | rules {m['rules_version']} | data_as_of {m['data_as_of']}")
    spec = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(spec["now"].replace("Z", "+00:00"))
    validator, failures = _validator(), 0
    if validator is None:
        print("note: jsonschema not installed; contract validation skipped")
    for case in spec["cases"]:
        result = inf.assess(case["model_input"], comparables=case["comparables"], package=package, now=now)
        status = result["valuation_assessment"]["assessment_status"]
        problems = []
        if status != case["expected_status"]:
            problems.append(f"status {status}, expected {case['expected_status']}")
        if validator is not None:
            problems += [e.message for e in validator.iter_errors(full_response(result, case["model_input"], now))][:3]
        va, iv = result["valuation_assessment"], result["ml_prediction_interval"]
        print(f"{'ok  ' if not problems else 'FAIL'} {case['name']}: {status} estimate={va['estimated_price_usd']} "
              f"interval=[{iv['lower_bound_usd']}, {iv['upper_bound_usd']}] withheld={result['provenance']['interval_withheld_reasons']}")
        for problem in problems:
            print("       " + problem)
        failures += bool(problems)
    for case in spec["errors"]:
        try:
            inf.assess(case["model_input"], package=package, now=now)
            raised = None
        except inf.InferenceError as error:
            raised = type(error).__name__
        ok = raised == case["expected_error"]
        print(f"{'ok  ' if ok else 'FAIL'} {case['name']}: raised {raised}")
        failures += not ok
    print("VERIFIED" if not failures else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
