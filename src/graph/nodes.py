"""Workflow nodes: deterministic validation -> investigation -> verification -> controller."""
from __future__ import annotations

from src.graph.state import QualityState
from src.quality.validator import QualityValidator
from src.agents.investigation_agent import InvestigationAgent
from src.agents.verification_agent import VerificationAgent


def validation_node(state: QualityState, validator: QualityValidator) -> QualityState:
    result = validator.validate_row(state.row)
    state.validation = result
    state.notes.append(f"Validated {result.batch_id}: {result.calculated_status}")
    return state


def investigation_node(state: QualityState, agent: InvestigationAgent) -> QualityState:
    assert state.validation is not None, "validation must run first"
    attempt = state.iterations + 1  # 1-based: later attempts broaden retrieval
    state.investigation = agent.investigate(state.validation, attempt=attempt)
    state.iterations += 1
    state.notes.append(f"Investigation attempt {state.iterations} (demo_mode={state.investigation.demo_mode})")
    return state


def verification_node(state: QualityState, agent: VerificationAgent) -> QualityState:
    assert state.investigation is not None, "investigation must run first"
    state.verification = agent.verify(state.investigation)
    state.notes.append(f"Verification supported={state.verification.supported}")
    return state


def controller_node(state: QualityState) -> QualityState:
    """Bounded retry controller. Never auto-releases batches."""
    assert state.validation is not None
    calc = state.validation.calculated_status
    verified = state.verification.supported if state.verification else False

    if calc == "PASS" and verified:
        # Even PASS requires human review for release; workflow marks PASS but review required.
        state.final_disposition = "PASS"
        state.requires_human_review = True
        state.notes.append("PASS with evidence; human review still required for release.")
    elif calc == "PASS" and not verified:
        if state.iterations < state.max_retries:
            state.notes.append("PASS but unverified; retry investigation.")
        else:
            state.final_disposition = "REVIEW"
            state.requires_human_review = True
            state.notes.append("Max retries reached; routed to human review.")
    else:  # FAIL or REVIEW
        if verified and calc == "FAIL":
            state.final_disposition = "FAIL"
            state.requires_human_review = True
            state.notes.append("FAIL with evidence; human review required.")
        else:
            if state.iterations < state.max_retries and state.verification and not state.verification.supported:
                state.notes.append("Unsupported claims; retry investigation (bounded).")
            else:
                state.final_disposition = "REVIEW" if calc == "REVIEW" else "FAIL"
                state.requires_human_review = True
                state.notes.append("Unresolved or max retries; routed to human review.")
    return state


def should_retry(state: QualityState) -> str:
    """Routing predicate for conditional edges."""
    if state.validation is None or state.verification is None:
        return "review"
    if state.verification.supported:
        return "done"
    if state.iterations >= state.max_retries:
        return "review"
    # Only retry when there is something to fix and attempts remain
    if state.validation.calculated_status in ("PASS", "FAIL", "REVIEW"):
        return "retry" if state.iterations < state.max_retries else "review"
    return "review"
