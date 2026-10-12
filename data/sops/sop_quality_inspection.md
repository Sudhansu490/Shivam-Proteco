# SYNTHETIC TRAINING EXAMPLE — NOT an approved company procedure.
# Fictional SOP for demonstration of RAG retrieval only.

# SOP-001 Quality Inspection — Synthetic Demo (v1.0)

## 1. Purpose
Describe fictional inspection data validation steps for training the demo app.

## 2. Scope
Applies to demo batches of `aluminium_powder` and `plastic_component` in `quality_batches.csv`.

## 3. Inspection Data Validation
1. Verify every required measurement is present. Parse `N/A` as missing / not applicable, never as zero.
2. Check configured specifications in `config/demo_quality_limits.yaml`:
   - Aluminium powder: `purity_min_pct >= 99.0`, `moisture_max_pct <= 0.10`, particle size `10–50 um`.
   - Plastic component: `defect_count_max == 0`.
3. Missing required measurements → disposition `REVIEW`.
4. Unknown product types or missing configuration → `REVIEW` and escalate.
5. Reject invalid negative counts and malformed numerics safely; never silently discard records.
6. Compare calculated status against recorded `inspection_status`; flag discrepancies for review.

## 4. Documenting Failed Measurements
- Record batch ID, failed check name, measured value, limit, and units.
- Example: `B002 purity 98.6 < 99.0 FAIL`.
- Keep original raw values; do not overwrite source data.

## 5. Retrieving Relevant Evidence
- Retrieve this SOP and SOP-002 Nonconformance before writing root-cause hypotheses.
- Cite source title, section, document ID and version for every claim.
- Distinguish observed facts from hypotheses.

## 6. Additional Inspection
- If purity is low, re-check moisture and particle size for correlated deviations.
- If moisture is high (> 0.10%), recommend drying verification and retest.
- If particle size is out of 10–50 um, recommend sieve / milling review.

## 7. Escalation and Authorized Human Review
- The system must NOT autonomously release manufacturing batches.
- All FAIL and REVIEW batches require authorized human review for final disposition.
- Human reviewer records decision (PASS / FAIL / REVIEW) and comments.

---
*Document ID: SOP-001 | Version: 1.0 | Synthetic demo only.*
