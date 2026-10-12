"""LangGraph workflow with pure-python fallback.

- Uses LangGraph when installed; otherwise runs identical sequential logic.
- Bounded retries (default max 3). Honest demo_mode labelling.
"""
from __future__ import annotations

from typing import Any, Dict

from src.graph.state import QualityState
from src.graph.nodes import (
    validation_node,
    investigation_node,
    verification_node,
    controller_node,
    should_retry,
)
from src.quality.validator import QualityValidator
from src.agents.investigation_agent import InvestigationAgent
from src.agents.verification_agent import VerificationAgent
from src.models.schemas import WorkflowResult


def _make_agents(limits_path: str, sops_dir: str, chroma_dir: str,
                 provider: str, groq_api_key: str, groq_model: str):
    validator = QualityValidator(limits_path)
    investigator = InvestigationAgent(
        sops_dir=sops_dir, chroma_dir=chroma_dir, provider=provider,
        groq_api_key=groq_api_key, groq_model=groq_model,
    )
    verifier = VerificationAgent()
    return validator, investigator, verifier


def run_workflow_sync(
    row: Dict[str, Any],
    limits_path: str = "config/demo_quality_limits.yaml",
    sops_dir: str = "data/sops",
    max_retries: int = 3,
    chroma_dir: str = "data/chroma",
    provider: str = "none",
    groq_api_key: str = "",
    groq_model: str = "llama-3.1-8b-instant",
) -> WorkflowResult:
    """Deterministic-first workflow path (no LangGraph dependency). Testable offline."""
    validator, investigator, verifier = _make_agents(
        limits_path, sops_dir, chroma_dir, provider, groq_api_key, groq_model)

    state = QualityState(batch_id=str(row.get("batch_id", "UNKNOWN")), row=dict(row), max_retries=max_retries)
    state = validation_node(state, validator)

    # PASS batches: single investigate+verify, no retry loop needed unless unsupported
    # FAIL/REVIEW: bounded retry loop
    for _ in range(max_retries):
        state = investigation_node(state, investigator)
        state = verification_node(state, verifier)
        route = should_retry(state)
        if route == "done":
            break
        if route == "review":
            break
        # route == retry -> loop continues
    state = controller_node(state)

    assert state.validation is not None
    return WorkflowResult(
        batch_id=state.batch_id,
        validation=state.validation,
        investigation=state.investigation,
        verification=state.verification,
        iterations=state.iterations,
        final_disposition=state.final_disposition,  # type: ignore[arg-type]
        requires_human_review=True,  # always true: no autonomous release
        notes=state.notes,
    )


def build_langgraph_workflow(
    limits_path: str = "config/demo_quality_limits.yaml",
    sops_dir: str = "data/sops",
    max_retries: int = 3,
    chroma_dir: str = "data/chroma",
    provider: str = "none",
    groq_api_key: str = "",
    groq_model: str = "llama-3.1-8b-instant",
):
    """Build a LangGraph StateGraph if langgraph is installed, else None."""
    try:
        from langgraph.graph import StateGraph, END
    except Exception:
        return None

    validator, investigator, verifier = _make_agents(
        limits_path, sops_dir, chroma_dir, provider, groq_api_key, groq_model)

    graph = StateGraph(QualityState)

    def _validate(s: QualityState) -> QualityState:
        return validation_node(s, validator)

    def _investigate(s: QualityState) -> QualityState:
        return investigation_node(s, investigator)

    def _verify(s: QualityState) -> QualityState:
        return verification_node(s, verifier)

    def _control(s: QualityState) -> QualityState:
        return controller_node(s)

    graph.add_node("validate", _validate)
    graph.add_node("investigate", _investigate)
    graph.add_node("verify", _verify)
    graph.add_node("control", _control)

    graph.set_entry_point("validate")
    graph.add_edge("validate", "investigate")
    graph.add_edge("investigate", "verify")

    def _route(s: QualityState) -> str:
        return should_retry(s)

    graph.add_conditional_edges("verify", _route, {"retry": "investigate", "done": "control", "review": "control"})
    graph.add_edge("control", END)
    return graph.compile()


def run_workflow(
    row: Dict[str, Any],
    limits_path: str = "config/demo_quality_limits.yaml",
    sops_dir: str = "data/sops",
    max_retries: int = 3,
    prefer_langgraph: bool = True,
    chroma_dir: str = "data/chroma",
    provider: str = "none",
    groq_api_key: str = "",
    groq_model: str = "llama-3.1-8b-instant",
) -> WorkflowResult:
    """Prefer LangGraph when available; fall back to sync path."""
    if prefer_langgraph:
        try:
            app = build_langgraph_workflow(limits_path, sops_dir, max_retries,
                                           chroma_dir, provider, groq_api_key, groq_model)
            if app is not None:
                init = QualityState(batch_id=str(row.get("batch_id", "UNKNOWN")), row=dict(row), max_retries=max_retries)
                final = app.invoke(init)
                if isinstance(final, dict):
                    st = QualityState(**final)
                else:
                    st = final
                assert st.validation is not None
                # ensure controller ran (LangGraph path includes it)
                return WorkflowResult(
                    batch_id=st.batch_id,
                    validation=st.validation,
                    investigation=st.investigation,
                    verification=st.verification,
                    iterations=st.iterations,
                    final_disposition=st.final_disposition,  # type: ignore[arg-type]
                    requires_human_review=True,
                    notes=st.notes,
                )
        except Exception:
            pass
    return run_workflow_sync(row, limits_path, sops_dir, max_retries,
                               chroma_dir, provider, groq_api_key, groq_model)
