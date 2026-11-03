"""B06: learned price effects as contract ``Attribution`` objects (CatBoost SHAP).

These describe what the *price model* learned for one prediction. They are kept apart from the ontology's
inferred facts: a rule fact is never an attribution and an attribution never a rule fact.
``*_missing`` indicator columns are folded into the feature they flag.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np


def _base_feature(name: str) -> str:
    return name[: -len("_missing")] if name.endswith("_missing") else name


def attributions_from_shap(feature_names: Sequence[str], shap_values: Sequence[float], *,
                           top_k: int = 5, neutral_eps: float = 1e-9) -> List[Dict[str, Any]]:
    """``impact_pct`` = share of the total absolute SHAP mass (0-100); ``direction`` = sign of the net effect.

    Raises on non-finite values or a length mismatch rather than returning a misleading explanation."""
    values = np.asarray(shap_values, dtype=float)
    if len(feature_names) != len(values):
        raise ValueError("feature_names and shap_values must have the same length")
    if not np.all(np.isfinite(values)):
        raise ValueError("shap_values must be finite")
    grouped: Dict[str, float] = {}
    for name, value in zip(feature_names, values):
        grouped[_base_feature(name)] = grouped.get(_base_feature(name), 0.0) + float(value)
    total = sum(abs(v) for v in grouped.values())
    if total <= 0:
        return []
    out = []
    for feature, value in sorted(grouped.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:top_k]:
        direction = "neutral" if abs(value) <= neutral_eps else ("positive" if value > 0 else "negative")
        out.append({"feature": feature, "impact_pct": round(100.0 * abs(value) / total, 2), "direction": direction})
    return out


def explain_with_catboost(model: Any, features: Any, *, top_k: int = 5,
                          cat_features: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """SHAP attributions for the first row of ``features`` (a preprocessed one-row DataFrame).

    ``cat_features`` names the categorical columns; when omitted, object-dtype columns are used."""
    from catboost import Pool

    names = list(features.columns)
    cat = [i for i, c in enumerate(names)
           if (c in cat_features if cat_features is not None else features[c].dtype == object)]
    shap = model.get_feature_importance(Pool(features.iloc[:1], cat_features=cat), type="ShapValues")[0]
    return attributions_from_shap(names, shap[:-1], top_k=top_k)   # last column is the expected value
