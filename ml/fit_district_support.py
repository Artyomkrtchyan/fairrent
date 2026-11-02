"""B06: fit the GEO-DISTRICT-SUPPORT reference table on a snapshot's **train** split only.

    python -m ml.fit_district_support --snapshot data/processed/v1.0.0 --out artifacts/b06/district_support.json

Stores aggregate ~1 km cell counts per district, not raw coordinates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd

from ml import ontology_rules as rules


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    train_path = args.snapshot / "train.csv"
    manifest_path = args.snapshot / "manifest.json"
    if not train_path.is_file() or not manifest_path.is_file():
        print(f"{args.snapshot} is not an A06 snapshot (train.csv / manifest.json missing)", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    train = pd.read_csv(train_path)
    support = rules.DistrictSupport.fit(train.to_dict("records"),
                                        reference_version=str(manifest.get("dataset_version", "unversioned")))
    payload = support.to_json()
    payload["snapshot_sha256"] = manifest.get("snapshot_sha256")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"fitted on {support.n_reference} train listings in {len(support.cells)} cells -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
