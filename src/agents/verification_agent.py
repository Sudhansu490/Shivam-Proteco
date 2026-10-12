"""Verification agent: checks evidence support, rejects unsupported claims."""
from __future__ import annotations

from typing import List
from src.models.schemas import InvestigationResult, VerificationResult


class VerificationAgent:
    def verify(self, investigation: InvestigationResult) -> VerificationResult:
        reasons: List[str] = []
        unsupported: List[str] = []

        if not investigation.evidence:
            reasons.append("No SOP evidence retrieved; cannot support root-cause claims.")
            for h in investigation.hypotheses:
                if h.startswith("HYPOTHESIS"):
                    unsupported.append(h)
            return VerificationResult(
                batch_id=investigation.batch_id,
                supported=False,
                reasons=reasons,
                unsupported_claims=unsupported,
            )

        # Check that each hypothesis topic appears in evidence text
        blob = " ".join((e.text_excerpt + " " + e.section).lower() for e in investigation.evidence)
        for h in investigation.hypotheses:
            hl = h.lower()
            # Pass-through note is not a causal claim
            if "no failure hypothesis needed" in hl:
                continue
            keywords = []
            if "purity" in hl:
                keywords = ["purity", "specification", "inspection"]
            elif "moisture" in hl:
                keywords = ["moisture", "drying"]
            elif "particle" in hl:
                keywords = ["particle", "sieve", "milling"]
            elif "defect" in hl or "mould" in hl or "mold" in hl:
                keywords = ["defect", "inspection"]
            elif "incomplete" in hl or "unknown" in hl:
                keywords = ["review", "human", "missing", "nonconformance"]
            elif "data-entry" in hl or "data entry" in hl:
                keywords = ["validation", "documenting"]
            else:
                keywords = []
            if keywords and not any(k in blob for k in keywords):
                unsupported.append(h)

        if unsupported:
            reasons.append(f"{len(unsupported)} claim(s) lack evidence support.")
            # hypotheses stay labelled as hypotheses; verification fails
            return VerificationResult(
                batch_id=investigation.batch_id,
                supported=False,
                reasons=reasons,
                unsupported_claims=unsupported,
            )

        cites = ", ".join(e.document_id for e in investigation.evidence)
        reasons.append(f"All causal hypotheses have keyword support in retrieved evidence ({cites}).")
        # Even when supported, FAIL/REVIEW still requires human review (enforced by workflow)
        return VerificationResult(
            batch_id=investigation.batch_id,
            supported=True,
            reasons=reasons,
            unsupported_claims=[],
        )
