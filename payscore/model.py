"""Model loading, scoring, risk bands and the clearly-labelled development fallback."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import __version__
from .features import FEATURE_NAMES, build_features
from .schema import ScoreRequest

MODEL_FILE = "payscore_lgbm.txt"
META_FILE = "model_metadata.json"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"

SCORE_MIN, SCORE_MAX = 300, 850
BASE_SCORE, BASE_ODDS, PDO = 600, 12.0, 50.0  # 600 pts at 12:1 good:bad odds; +50 pts doubles the odds
# Score cut-offs for risk bands (documented in README).
BAND_CUTOFFS = [(720, "low"), (650, "moderate"), (560, "elevated")]

CAVEAT_SYNTHETIC = (
    "Model trained on a SYNTHETIC development dataset, not real Home Credit or PayPal data. "
    "Scores are for demonstration and integration testing only; not for real lending decisions."
)
CAVEAT_HOMECREDIT = (
    "Model trained on a partial mapping of the Home Credit Default Risk data (few overlapping fields). "
    "Not validated on PayPal-derived inputs; not for real lending decisions."
)
CAVEAT_FALLBACK = (
    "DEVELOPMENT FALLBACK: deterministic rule-of-thumb formula, NOT a trained-model prediction. "
    "For frontend/agent integration testing only; not for real lending decisions."
)


class ModelArtifactError(RuntimeError):
    """Artifact exists but is unusable (corrupt or incompatible)."""


class ModelUnavailableError(RuntimeError):
    """No trained model and the development fallback is disabled."""


@dataclass
class TrainedModel:
    booster: lgb.Booster
    metadata: dict[str, Any]

    def predict_pd(self, records: pd.DataFrame) -> np.ndarray:
        X = build_features(records)[self.metadata["feature_names"]]
        return self.booster.predict(X)


def load_model(model_dir: Path | str) -> Optional[TrainedModel]:
    """Return the trained model, or None if no artifact is present."""
    d = Path(model_dir)
    model_path, meta_path = d / MODEL_FILE, d / META_FILE
    if not model_path.exists() and not meta_path.exists():
        return None
    if not (model_path.exists() and meta_path.exists()):
        raise ModelArtifactError(f"Incomplete model artifact in {d}: need both {MODEL_FILE} and {META_FILE}")
    try:
        metadata = json.loads(meta_path.read_text())
        booster = lgb.Booster(model_file=str(model_path))
    except Exception as exc:  # noqa: BLE001
        raise ModelArtifactError(f"Could not load model artifact from {d}: {exc}") from exc
    if metadata.get("feature_names") != FEATURE_NAMES:
        raise ModelArtifactError("Model features do not match this code version; retrain with `python -m payscore.train`.")
    return TrainedModel(booster=booster, metadata=metadata)


def fallback_pd(records: pd.DataFrame) -> np.ndarray:
    """Deterministic rule-of-thumb default probability. NOT a trained model.

    Coefficients are hand-picked (loosely scaled by eye so the demo personas span the bands);
    they are not fitted to any data.
    """
    f = build_features(records).fillna(0.0)  # missing -> neutral contribution
    income = records["monthly_income_inr"].astype(float).clip(lower=1.0)
    z = (
        -4.2
        + 1.8 * f["debt_to_income"].clip(0, 1.5)
        + 1.5 * f["installment_to_income"].clip(0, 2)
        + 1.0 * f["revenue_volatility_cv"].clip(0, 2)
        + 5.0 * f["refund_rate_90d"]
        + 20.0 * f["dispute_rate_12m"]
        + 0.7 * f["prior_defaults_count"]
        - 0.01 * f["business_age_months"].clip(0, 120)
        - 0.4 * (np.log(income) - 10.5)
    )
    return (1.0 / (1.0 + np.exp(-z))).to_numpy()


def pd_to_score(p: float) -> int:
    p = min(max(p, 1e-6), 1 - 1e-6)
    factor = PDO / math.log(2)
    offset = BASE_SCORE - factor * math.log(BASE_ODDS)
    score = offset + factor * math.log((1 - p) / p)
    return int(min(max(round(score), SCORE_MIN), SCORE_MAX))


def risk_band(score: int) -> str:
    for cutoff, name in BAND_CUTOFFS:
        if score >= cutoff:
            return name
    return "high"


class Scorer:
    """Scores one normalised request using the trained model or the explicit fallback."""

    def __init__(self, trained: Optional[TrainedModel], allow_fallback: bool = True):
        self.trained = trained
        self.allow_fallback = allow_fallback

    @classmethod
    def from_dir(cls, model_dir: Path | str, allow_fallback: bool = True) -> "Scorer":
        return cls(load_model(model_dir), allow_fallback)

    @property
    def available(self) -> bool:
        return self.trained is not None or self.allow_fallback

    def model_info(self) -> dict[str, Any]:
        if self.trained is not None:
            m = self.trained.metadata
            return {"name": m["model_name"], "version": m["model_version"], "type": "lightgbm",
                    "is_trained_model": True, "training_data": m["training_data"]["kind"]}
        return {"name": "payscore-dev-fallback", "version": __version__, "type": "development_fallback",
                "is_trained_model": False, "training_data": None}

    def _caveat(self) -> str:
        if self.trained is None:
            return CAVEAT_FALLBACK
        return CAVEAT_HOMECREDIT if self.trained.metadata["training_data"]["kind"] == "homecredit" else CAVEAT_SYNTHETIC

    def score(self, req: ScoreRequest) -> dict[str, Any]:
        if not self.available:
            raise ModelUnavailableError("No trained model artifact found and the development fallback is disabled.")
        record = req.model_dump(mode="json")
        df = pd.DataFrame([record])
        p = float((self.trained.predict_pd(df) if self.trained else fallback_pd(df))[0])
        s = pd_to_score(p)
        optional_missing = [k for k, v in record.items() if v is None]
        return {
            "applicant_id": req.applicant_id,
            "score": s,
            "score_range": {"min": SCORE_MIN, "max": SCORE_MAX},
            "risk_band": risk_band(s),
            "probability_of_default": round(p, 4),
            "model": self.model_info(),
            "evaluation_caveat": self._caveat(),
            "missing_inputs": optional_missing,
        }
