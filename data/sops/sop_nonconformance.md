# SYNTHETIC TRAINING EXAMPLE — NOT an approved company procedure.
# Fictional SOP for demonstration of RAG retrieval only.

# SOP-002 Nonconformance Handling — Synthetic Demo (v1.0)

## 1. Purpose
Fictional steps for investigating and documenting nonconforming demo batches.

## 2. Investigation
1. Summarize deterministic validation facts first (failed checks, missing fields).
2. Retrieve SOP evidence; cite title, section, document ID, version.
3. Propose possible explanations labelled clearly as HYPOTHESIS, not fact.
   - Low purity hypothesis: raw material variation or measurement error — requires lab retest.
   - High moisture hypothesis: storage humidity or incomplete drying — requires drying verification.
   - Particle size hypothesis: milling/sieve drift — requires equipment check.
   - Plastic defects hypothesis: mould wear or process drift — requires visual re-inspection.
4. Never invent a source citation. If retrieval failed, state that no evidence was found.

## 3. Verification
- Verification agent checks that every root-cause claim is supported by retrieved evidence.
- Reject unsupported root-cause claims; mark verification as `supported: false` with reasons.
- Insufficient evidence → send to human review, do not auto-close.
- LLM must never override deterministic numerical validation.

## 4. Retry Bounds
- Maximum 3 investigation→verification iterations (configurable).
- After max attempts, route unresolved cases to human review.

## 5. Human Review and Disposition
- Authorized human records final disposition, comments, and timestamp.
- Persist batch, validation, investigation, verification, and review records in SQLite where configured.
- Without a database, persist to local logs and clearly label demo mode.

---
*Document ID: SOP-002 | Version: 1.0 | Synthetic demo only.*
