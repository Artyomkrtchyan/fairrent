"""B07: bundle the B04 model, B05 calibration and B06 rule reference into one versioned inference package.

    python -m ml.package_inference --b04 artifacts/b04/<v> --b05 artifacts/b05/<v> \\
        --snapshot data/processed/<dataset> --version <package-version>

Refuses to package when the artifacts do not belong together (checksums, model hash, snapshot hash) or when
B04's decision was not ``ml``. Output: ``artifacts/b07/<version>/`` with SHA256SUMS.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd

from ml import calibrate_intervals as ci
from ml import inference as inf
from ml import intervals as iv
from ml import ontology_rules as rules
from ml import train_compare as tc

LIMITATIONS = (
    "Asking prices, not signed rents; USD per month.",
    "Provisional thresholds: 3 comparables, 60-day source age, coverage box (docs/contract-semantics.md).",
    "Estimates are withheld (abstention) where the serving gate reports extrapolation or sparse local data.",
    "Rule facts (B06) are not price effects; only feature_attributions describe the model.",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_b05(b05_dir: Path) -> dict:
    sums_path = b05_dir / "SHA256SUMS.json"
    if not sums_path.is_file():
        raise ci.ArtifactError(f"{sums_path} not found; is --b05 a B05 artifact directory?")
    for name, digest in json.loads(sums_path.read_text(encoding="utf-8")).items():
        path = b05_dir / name
        if not path.is_file() or _sha256_file(path) != digest:
            raise ci.ArtifactError(f"B05 artifact {name} is missing or does not match SHA256SUMS.json")
    return json.loads((b05_dir / "b05_report.json").read_text(encoding="utf-8"))["metadata"]


def build(b04_dir: Path, b05_dir: Path, snapshot_dir: Path, version: str, output_dir: Path) -> Path:
    meta04, _, _, model_sha = ci.load_b04(b04_dir)              # verifies B04 checksums
    meta05 = _verify_b05(b05_dir)
    if meta04.get("serving_decision") != "ml":
        raise ci.ArtifactError(f"B04 decision is {meta04.get('serving_decision')!r}, not 'ml': "
                               "an ML inference package is not justified")
    if meta05.get("b04_model_sha256") != model_sha:
        raise ci.ArtifactError("B05 calibration was fitted on a different B04 model (model hash mismatch)")
    snapshot_sha = (meta04.get("dataset") or {}).get("snapshot_sha256")
    if meta05.get("snapshot_sha256") != snapshot_sha:
        raise ci.ArtifactError("B04 and B05 artifacts were built from different snapshots")
    ci.verify_snapshot_digest(snapshot_dir)
    splits, manifest = tc.load_snapshot(snapshot_dir)
    if manifest.get("snapshot_sha256") != snapshot_sha:
        raise ci.ArtifactError("--snapshot does not match the snapshot the model was trained on")

    train = splits["train"]
    stamps = pd.concat([pd.to_datetime(f["observation_at"], utc=True, errors="coerce") for f in splits.values()])
    data_as_of = stamps.max().strftime("%Y-%m-%dT%H:%M:%SZ")
    support = rules.DistrictSupport.fit(train.to_dict("records"),
                                        reference_version=str(manifest.get("dataset_version", "unversioned")))

    out = output_dir / version
    if out.exists():
        raise ci.ArtifactError(f"{out} already exists; packages are immutable, choose a new --version")
    out.mkdir(parents=True)
    shutil.copy2(b04_dir / "model.cbm", out / "model.cbm")
    shutil.copy2(b04_dir / "preprocessing.json", out / "preprocessing.json")
    shutil.copy2(b05_dir / "interval_calibration.json", out / "interval_calibration.json")
    (out / "district_support.json").write_text(json.dumps(support.to_json(), indent=2, sort_keys=True), encoding="utf-8")
    calibration = iv.IntervalCalibration.from_json(json.loads((out / "interval_calibration.json").read_text("utf-8")))
    null_rate = {c: round(float(pd.to_numeric(train[c], errors="coerce").isna().mean()), 4)
                 for c in ("area_sqm", "rooms", "floor", "total_floors", "distance_metro_m",
                           "distance_center_m", "distance_university_m")}
    package = {
        "package_schema_version": inf.PACKAGE_SCHEMA_VERSION, "package_version": version,
        "interface_version": inf.INFERENCE_INTERFACE_VERSION,
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_version": meta04["model_version"], "model_sha256": model_sha,
        "calibration_version": calibration.calibration_version, "primary_level": calibration.primary_level,
        "rules_version": rules.RULES_VERSION, "geography_version": _geo_version(),
        "dataset_version": manifest.get("dataset_version"), "snapshot_sha256": snapshot_sha,
        "data_as_of": data_as_of, "evidence_level": meta04.get("evidence_level"),
        "temporal_split": (meta04.get("dataset") or {}).get("temporal_split"),
        "is_synthetic": (meta04.get("dataset") or {}).get("is_synthetic"),
        "serving_decision": meta04.get("serving_decision"),
        "thresholds": {"min_comparables": inf.MIN_COMPARABLES, "max_source_age_days": inf.MAX_SOURCE_AGE_DAYS,
                       "coverage_version": inf.COVERAGE_VERSION, "coverage_bbox": inf.COVERAGE_BBOX},
        "training_null_rate": null_rate, "limitations": list(LIMITATIONS),
        "inputs": {"b04_model_version": meta04["model_version"], "b05_version": meta05.get("version")},
    }
    (out / "package.json").write_text(json.dumps(package, indent=2, sort_keys=True), encoding="utf-8")
    digest = {p.name: _sha256_file(p) for p in sorted(out.iterdir()) if p.name != "SHA256SUMS.json"}
    (out / "SHA256SUMS.json").write_text(json.dumps(digest, indent=2), encoding="utf-8")
    inf.InferencePackage.load(out)                              # the package must load before it is announced
    return out


def _geo_version() -> Optional[str]:
    geo = rules._geography()
    return getattr(geo, "GEOGRAPHY_VERSION", None)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--b04", type=Path, required=True)
    parser.add_argument("--b05", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/b07"))
    args = parser.parse_args(argv)
    try:
        out = build(args.b04, args.b05, args.snapshot, args.version, args.output_dir)
    except (ci.ArtifactError, iv.CalibrationError, inf.PackageError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"package written and verified: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
