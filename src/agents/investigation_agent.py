"""Investigation agent: facts from deterministic validation, hypotheses +
SOP-grounded recommendations, evidence via the Chroma-first Retriever facade.

Rule-based path is the default (demo_mode=True). When provider="groq" with a
valid key, Groq drafts hypothesis/recommendation text — but the deterministic
validation result is never modified by the LLM.
"""
from __future__ import annotations

from typing import List
from src.models.schemas import BatchValidationResult, InvestigationResult
from src.rag.retriever import Retriever


HYPOTHESIS_MAP = {
    "purity_min": "HYPOTHESIS: low purity may indicate raw-material variation or measurement error — requires lab retest (SOP-001 §Additional Inspection).",
    "moisture_max": "HYPOTHESIS: high moisture may indicate storage humidity or incomplete drying — requires drying verification and retest.",
    "particle_size_range": "HYPOTHESIS: particle size out of range may indicate milling/sieve drift — requires equipment check.",
    "defect_count_max": "HYPOTHESIS: plastic defects may indicate mould wear or process drift — requires visual re-inspection.",
    "defect_count_valid": "HYPOTHESIS: invalid defect count suggests data-entry error — requires source record check.",
}

# SOP-grounded next steps per failed check. Recommendations, never decisions:
# final disposition always requires authorized human review.
RECOMMENDATION_MAP = {
    "purity_min": [
        "RECOMMENDED NEXT STEP (requires human approval): quarantine batch and order a lab retest to rule out measurement error (SOP-001 §6 Additional Inspection).",
        "RECOMMENDED NEXT STEP (requires human approval): review raw-material lot records for variation if retest confirms low purity.",
    ],
    "moisture_max": [
        "RECOMMENDED NEXT STEP (requires human approval): run drying verification and retest moisture before any release decision (SOP-001 §6).",
        "RECOMMENDED NEXT STEP (requires human approval): check storage humidity logs for the batch hold area.",
    ],
    "particle_size_range": [
        "RECOMMENDED NEXT STEP (requires human approval): inspect milling/sieve equipment settings and re-sample particle size (SOP-001 §6).",
    ],
    "defect_count_max": [
        "RECOMMENDED NEXT STEP (requires human approval): perform visual re-inspection of the batch and check the mould for wear or process drift (SOP-002 §2).",
    ],
    "defect_count_valid": [
        "RECOMMENDED NEXT STEP (requires human approval): verify the source inspection record for a data-entry error and correct at origin.",
    ],
}


class InvestigationAgent:
    def __init__(self, sops_dir: str = "data/sops", chroma_dir: str = "data/chroma",
                 provider: str = "none", groq_api_key: str = "",
                 groq_model: str = "llama-3.1-8b-instant") -> None:
        self.sops_dir = sops_dir
        self.chroma_dir = chroma_dir
        self.provider = (provider or "none").lower()
        self.groq_api_key = groq_api_key
        self.groq_model = groq_model
        # Chroma-first vector retrieval with keyword fallback (never invents citations).
        self.retriever = Retriever(sops_dir=sops_dir, chroma_dir=chroma_dir)

    @property
    def llm_enabled(self) -> bool:
        return self.provider == "groq" and bool(self.groq_api_key)

    def _query(self, validation: BatchValidationResult, attempt: int) -> str:
        terms = [validation.product_type] + [fc.check for fc in validation.failed_checks]
        if validation.calculated_status == "REVIEW":
            terms.append("nonconformance human review missing measurement")
        else:
            terms.append("inspection specification failed measurement")
        if attempt > 1:
            # Adaptive retry: broaden the query so later attempts can surface
            # different evidence instead of repeating attempt 1 verbatim.
            terms.append("corrective action retest additional inspection")
        return " ".join(terms)

    def _rule_hypotheses(self, validation: BatchValidationResult) -> List[str]:
        hypotheses: List[str] = []
        for fc in validation.failed_checks:
            h = HYPOTHESIS_MAP.get(fc.check)
            if h and h not in hypotheses:
                hypotheses.append(h)
        if validation.calculated_status == "REVIEW" and not hypotheses:
            hypotheses.append("HYPOTHESIS: incomplete or unknown data — requires additional inspection and human review per SOP-002.")
        if validation.calculated_status == "PASS":
            hypotheses.append("No failure hypothesis needed; batch meets demo limits. Human review still required for release.")
        return hypotheses

    def _rule_recommendations(self, validation: BatchValidationResult) -> List[str]:
        recs: List[str] = []
        for fc in validation.failed_checks:
            for r in RECOMMENDATION_MAP.get(fc.check, []):
                if r not in recs:
                    recs.append(r)
        if validation.calculated_status == "REVIEW" and not recs:
            recs.append("RECOMMENDED NEXT STEP (requires human approval): complete the missing measurements and re-run validation before disposition (SOP-002 §5).")
        if validation.calculated_status == "PASS" and not recs:
            recs.append("RECOMMENDED NEXT STEP (requires human approval): routine release review by an authorized human; no corrective action indicated.")
        return recs

    def investigate(self, validation: BatchValidationResult, attempt: int = 1) -> InvestigationResult:
        facts: List[str] = [
            f"Batch {validation.batch_id} ({validation.product_type}) calculated as {validation.calculated_status}."
        ]
        for fc in validation.failed_checks:
            facts.append(f"FACT: {fc.check}: {fc.message} (measured={fc.measured}, limit={fc.limit}).")
        for m in validation.missing_fields:
            facts.append(f"FACT: missing required field: {m}.")
        for e in validation.errors:
            facts.append(f"FACT: validation note: {e}.")
        if validation.discrepancy:
            facts.append(
                f"FACT: recorded status {validation.recorded_status} disagrees with calculated {validation.calculated_status}."
            )

        top_k = 3 if attempt <= 1 else 5  # wider net on retries
        evidence = self.retriever.retrieve(self._query(validation, attempt), top_k=top_k)

        hypotheses = self._rule_hypotheses(validation)
        recommendations = self._rule_recommendations(validation)
        llm_model = ""
        llm_note = ""

        if self.llm_enabled:
            try:
                from src.agents.llm import SYSTEM_PROMPT, groq_complete, split_draft
                user = "Validation facts:\n" + "\n".join(f"- {f}" for f in facts)
                user += "\n\nSOP evidence:\n"
                for ev in evidence:
                    user += f"- [{ev.document_id} §{ev.section} v{ev.version}] {ev.text_excerpt[:400]}\n"
                draft = groq_complete(self.groq_api_key, self.groq_model, SYSTEM_PROMPT, user)
                llm_hyps, llm_recs = split_draft(draft)
                if llm_hyps:
                    hypotheses = llm_hyps
                if llm_recs:
                    recommendations = llm_recs
                llm_model = self.groq_model
            except Exception as e:
                llm_note = f"LLM call failed ({e}); used rule-based fallback."

        demo_mode = not bool(llm_model)
        if not evidence:
            summary = (
                f"{'Rule-based demo' if demo_mode else 'LLM-assisted'} investigation for {validation.batch_id}: "
                f"{len(facts)} facts, {len(hypotheses)} hypotheses, "
                f"{len(recommendations)} recommendations, no SOP evidence retrieved."
            )
        else:
            cites = "; ".join(f"{e.document_id} §{e.section}" for e in evidence)
            summary = (
                f"{'Rule-based demo' if demo_mode else 'LLM-assisted (' + llm_model + ')'} investigation "
                f"for {validation.batch_id}: {validation.calculated_status} based on "
                f"{len(validation.failed_checks)} failed checks. Evidence: {cites}."
            )
        if llm_note:
            summary += f" {llm_note}"
        return InvestigationResult(
            batch_id=validation.batch_id,
            facts=facts,
            hypotheses=hypotheses,
            recommendations=recommendations,
            evidence=evidence,
            summary=summary,
            demo_mode=demo_mode,
            llm_model=llm_model,
        )

    def try_llm_summary(self, investigation: InvestigationResult, provider: str = "none") -> str:
        """Legacy hook kept for backwards compatibility. Prefers the live path
        used by investigate(); never called automatically."""
        if provider == "none" or not investigation.llm_model:
            return investigation.summary
        return investigation.summary + f" [LLM provider '{provider}' noted.]"
