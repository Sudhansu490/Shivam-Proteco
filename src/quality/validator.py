"""Deterministic quality validator. No LLM. No database required."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from src.models.schemas import BatchValidationResult, FailedCheck

MISSING_TOKENS = {"", "N/A", "NA", "NULL", "NONE", "NAN", "NAN%", "N/A%"}
STATUS_VALUES = {"PASS", "FAIL", "REVIEW"}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    s = str(value).strip().upper()
    return s in MISSING_TOKENS


def _parse_float(value: Any, field_name: str, errors: List[str]) -> Optional[float]:
    if _is_missing(value):
        return None
    try:
        s = str(value).strip().replace("%", "")
        num = float(s)
        # NaN / inf are malformed for our purposes
        if num != num or num in (float("inf"), float("-inf")):
            errors.append(f"Malformed numeric measurement for {field_name}: {value!r}")
            return None
        return num
    except (ValueError, TypeError):
        errors.append(f"Malformed numeric measurement for {field_name}: {value!r}")
        return None


def _parse_int(value: Any, field_name: str, errors: List[str]) -> Optional[int]:
    if _is_missing(value):
        return None
    try:
        s = str(value).strip()
        # allow "3.0" style
        num = float(s)
        if num != num or num in (float("inf"), float("-inf")):
            errors.append(f"Malformed numeric measurement for {field_name}: {value!r}")
            return None
        if not num.is_integer():
            errors.append(f"Malformed numeric measurement for {field_name}: {value!r} (expected integer)")
            return None
        return int(num)
    except (ValueError, TypeError):
        errors.append(f"Malformed numeric measurement for {field_name}: {value!r}")
        return None


class QualityValidator:
    """Validate batch measurements against fictional demo limits."""

    def __init__(self, limits_path: str | Path = "config/demo_quality_limits.yaml") -> None:
        self.limits_path = Path(limits_path)
        self.limits: Dict[str, Any] = self._load_limits()

    def _load_limits(self) -> Dict[str, Any]:
        if not self.limits_path.exists():
            return {}
        with open(self.limits_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data

    def load_batches(self, csv_path: str | Path) -> pd.DataFrame:
        # keep_default_na=False so "N/A" stays a string we control; empty stays ""
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        # normalize column names
        df.columns = [c.strip() for c in df.columns]
        return df

    def validate_row(self, row: Dict[str, Any]) -> BatchValidationResult:
        batch_id = str(row.get("batch_id", "")).strip() or "UNKNOWN"
        product_type = str(row.get("product_type", "")).strip()
        recorded_raw = str(row.get("inspection_status", "")).strip().upper() or None
        recorded_status = recorded_raw if recorded_raw in STATUS_VALUES else recorded_raw

        failed: List[FailedCheck] = []
        missing: List[str] = []
        errors: List[str] = []
        limits_used: Dict[str, Any] = {}

        if not product_type or product_type not in self.limits:
            missing.append("product_type_configuration")
            errors.append(f"Unknown product type or missing configuration: {product_type!r}")
            result = BatchValidationResult(
                batch_id=batch_id,
                product_type=product_type or "UNKNOWN",
                calculated_status="REVIEW",
                recorded_status=recorded_status,
                discrepancy=bool(recorded_status and recorded_status != "REVIEW"),
                failed_checks=failed,
                missing_fields=missing,
                limits_used={},
                errors=errors,
            )
            return result

        cfg = self.limits[product_type] or {}
        limits_used = dict(cfg)

        if product_type == "aluminium_powder":
            purity = _parse_float(row.get("purity_pct"), "purity_pct", errors)
            moisture = _parse_float(row.get("moisture_pct"), "moisture_pct", errors)
            particle = _parse_float(row.get("particle_size_um"), "particle_size_um", errors)

            if purity is None:
                missing.append("purity_pct")
            if moisture is None:
                missing.append("moisture_pct")
            if particle is None:
                missing.append("particle_size_um")

            p_min = cfg.get("purity_min_pct")
            m_max = cfg.get("moisture_max_pct")
            s_min = cfg.get("particle_size_min_um")
            s_max = cfg.get("particle_size_max_um")

            if purity is not None and p_min is not None:
                try:
                    if purity < float(p_min):
                        failed.append(FailedCheck(check="purity_min", measured=purity, limit=float(p_min),
                                                  message=f"purity {purity} < min {p_min}"))
                except (ValueError, TypeError):
                    errors.append(f"Invalid configured limit purity_min_pct: {p_min!r}")
            if moisture is not None and m_max is not None:
                try:
                    if moisture > float(m_max):
                        failed.append(FailedCheck(check="moisture_max", measured=moisture, limit=float(m_max),
                                                  message=f"moisture {moisture} > max {m_max}"))
                except (ValueError, TypeError):
                    errors.append(f"Invalid configured limit moisture_max_pct: {m_max!r}")
            if particle is not None and s_min is not None and s_max is not None:
                try:
                    lo, hi = float(s_min), float(s_max)
                    if particle < lo or particle > hi:
                        failed.append(FailedCheck(check="particle_size_range", measured=particle, limit=hi,
                                                  message=f"particle_size {particle} outside [{lo}, {hi}]"))
                except (ValueError, TypeError):
                    errors.append(f"Invalid configured particle limits: {s_min!r}, {s_max!r}")

        elif product_type == "plastic_component":
            defects = _parse_int(row.get("defect_count"), "defect_count", errors)
            if defects is None:
                # defect_count is required for plastic; treat unparseable/missing as REVIEW
                if "defect_count" not in [e for e in missing]:
                    missing.append("defect_count")
            else:
                if defects < 0:
                    errors.append(f"Invalid negative defect_count: {defects}")
                    failed.append(FailedCheck(check="defect_count_valid", measured=float(defects),
                                              limit=0, message=f"negative defect_count {defects} invalid"))
                else:
                    d_max = cfg.get("defect_count_max", 0)
                    try:
                        if defects > int(d_max):
                            failed.append(FailedCheck(check="defect_count_max", measured=float(defects),
                                                      limit=float(d_max),
                                                      message=f"defect_count {defects} > max {d_max}"))
                    except (ValueError, TypeError):
                        errors.append(f"Invalid configured limit defect_count_max: {d_max!r}")
        else:
            errors.append(f"Unhandled product type: {product_type!r}")
            missing.append("product_type_configuration")

        # Disposition logic
        if errors and any("negative" in e or "Malformed" in e for e in errors):
            # malformed/negative measurements are not silently discarded -> REVIEW if no hard fail,
            # but negative defect already recorded as failed check; keep FAIL if failed checks exist
            pass
        if failed:
            status = "FAIL"
        elif missing or errors:
            status = "REVIEW"
        else:
            status = "PASS"

        # Negative defect_count with failed check -> FAIL (already). Malformed numeric with no failed -> REVIEW.
        discrepancy = bool(recorded_status and recorded_status != status)

        return BatchValidationResult(
            batch_id=batch_id,
            product_type=product_type,
            calculated_status=status,  # type: ignore[arg-type]
            recorded_status=recorded_status,
            discrepancy=discrepancy,
            failed_checks=failed,
            missing_fields=missing,
            limits_used=limits_used,
            errors=errors,
        )

    def validate_csv(self, csv_path: str | Path) -> List[BatchValidationResult]:
        df = self.load_batches(csv_path)
        results: List[BatchValidationResult] = []
        for _, r in df.iterrows():
            row = {k: (None if pd.isna(v) else v) for k, v in r.to_dict().items()}
            # pd with keep_default_na=False won't produce NaN, but be safe
            results.append(self.validate_row(row))
        return results
