"""Validator tests: offline, no API keys, no DB."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from src.quality.validator import QualityValidator

LIMITS = "config/demo_quality_limits.yaml"
CSV = "data/quality_batches.csv"


def test_csv_loads_and_has_expected_columns():
    v = QualityValidator(LIMITS)
    assert Path(CSV).exists(), "quality_batches.csv must be preserved"
    df = v.load_batches(CSV)
    for col in ["batch_id", "product_type", "purity_pct", "moisture_pct",
                "particle_size_um", "defect_count", "inspection_status"]:
        assert col in df.columns
    assert len(df) == 50


def test_pass_scenario():
    v = QualityValidator(LIMITS)
    r = v.validate_row({"batch_id": "T1", "product_type": "aluminium_powder",
                        "purity_pct": "99.4", "moisture_pct": "0.05",
                        "particle_size_um": "25", "defect_count": "0",
                        "inspection_status": "PASS"})
    assert r.calculated_status == "PASS"
    assert r.failed_checks == []
    assert not r.discrepancy


def test_fail_scenarios():
    v = QualityValidator(LIMITS)
    low_purity = v.validate_row({"batch_id": "T2", "product_type": "aluminium_powder",
                                 "purity_pct": "98.6", "moisture_pct": "0.05",
                                 "particle_size_um": "25", "defect_count": "0",
                                 "inspection_status": "FAIL"})
    assert low_purity.calculated_status == "FAIL"
    assert any(f.check == "purity_min" for f in low_purity.failed_checks)

    plastic_fail = v.validate_row({"batch_id": "T3", "product_type": "plastic_component",
                                   "purity_pct": "N/A", "moisture_pct": "N/A",
                                   "particle_size_um": "N/A", "defect_count": "4",
                                   "inspection_status": "FAIL"})
    assert plastic_fail.calculated_status == "FAIL"


def test_review_missing_measurements():
    v = QualityValidator(LIMITS)
    r = v.validate_row({"batch_id": "T4", "product_type": "aluminium_powder",
                        "purity_pct": "N/A", "moisture_pct": "0.05",
                        "particle_size_um": "25", "defect_count": "0",
                        "inspection_status": "PASS"})
    assert r.calculated_status == "REVIEW"
    assert "purity_pct" in r.missing_fields


def test_boundary_values():
    v = QualityValidator(LIMITS)
    # exactly at limits -> PASS
    r = v.validate_row({"batch_id": "B", "product_type": "aluminium_powder",
                        "purity_pct": "99.0", "moisture_pct": "0.10",
                        "particle_size_um": "10", "defect_count": "0",
                        "inspection_status": "PASS"})
    assert r.calculated_status == "PASS"
    r2 = v.validate_row({"batch_id": "B", "product_type": "aluminium_powder",
                         "purity_pct": "99.0", "moisture_pct": "0.10",
                         "particle_size_um": "50", "defect_count": "0",
                         "inspection_status": "PASS"})
    assert r2.calculated_status == "PASS"
    # just outside
    r3 = v.validate_row({"batch_id": "B", "product_type": "aluminium_powder",
                         "purity_pct": "98.99", "moisture_pct": "0.10",
                         "particle_size_um": "25", "defect_count": "0",
                         "inspection_status": "FAIL"})
    assert r3.calculated_status == "FAIL"


def test_na_never_zero():
    v = QualityValidator(LIMITS)
    r = v.validate_row({"batch_id": "T5", "product_type": "plastic_component",
                        "purity_pct": "N/A", "moisture_pct": "N/A",
                        "particle_size_um": "N/A", "defect_count": "0",
                        "inspection_status": "PASS"})
    assert r.calculated_status == "PASS"  # N/A fields ignored for plastic
    # aluminium with N/A must NOT be treated as 0
    r2 = v.validate_row({"batch_id": "T6", "product_type": "aluminium_powder",
                         "purity_pct": "N/A", "moisture_pct": "N/A",
                         "particle_size_um": "N/A", "defect_count": "0",
                         "inspection_status": "REVIEW"})
    assert r2.calculated_status == "REVIEW"


def test_malformed_and_negative():
    v = QualityValidator(LIMITS)
    bad = v.validate_row({"batch_id": "T7", "product_type": "aluminium_powder",
                          "purity_pct": "high", "moisture_pct": "0.05",
                          "particle_size_um": "25", "defect_count": "0",
                          "inspection_status": "REVIEW"})
    assert bad.calculated_status == "REVIEW"
    assert any("Malformed" in e for e in bad.errors)

    neg = v.validate_row({"batch_id": "T8", "product_type": "plastic_component",
                          "purity_pct": "N/A", "moisture_pct": "N/A",
                          "particle_size_um": "N/A", "defect_count": "-1",
                          "inspection_status": "FAIL"})
    assert neg.calculated_status == "FAIL"  # invalid negative flagged, never discarded
    assert any("negative" in e.lower() for e in neg.errors)


def test_unknown_product_type():
    v = QualityValidator(LIMITS)
    r = v.validate_row({"batch_id": "T9", "product_type": "titanium_rod",
                        "purity_pct": "99.9", "moisture_pct": "0.01",
                        "particle_size_um": "20", "defect_count": "0",
                        "inspection_status": "PASS"})
    assert r.calculated_status == "REVIEW"
    assert r.discrepancy  # recorded PASS vs REVIEW


def test_discrepancy_flag():
    v = QualityValidator(LIMITS)
    # B008 in demo CSV: recorded PASS but particle 45 within limits -> actually PASS, no discrepancy.
    # Construct a clear mismatch:
    r = v.validate_row({"batch_id": "TX", "product_type": "aluminium_powder",
                        "purity_pct": "98.0", "moisture_pct": "0.05",
                        "particle_size_um": "25", "defect_count": "0",
                        "inspection_status": "PASS"})
    assert r.calculated_status == "FAIL"
    assert r.discrepancy is True


def test_full_csv_sensible_counts():
    v = QualityValidator(LIMITS)
    results = v.validate_csv(CSV)
    assert len(results) == 50
    counts = {"PASS": 0, "FAIL": 0, "REVIEW": 0}
    for r in results:
        counts[r.calculated_status] += 1
    # With demo limits, expect a mix; plastic defect>0 -> FAIL, aluminium out-of-spec -> FAIL
    assert counts["PASS"] > 10
    assert counts["FAIL"] > 10
    # No silent discards: every row yields a result
    assert sum(counts.values()) == 50
