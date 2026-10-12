"""Live-path tests: provider threading, Groq fallback, adaptive retry. Offline-safe."""
from __future__ import annotations

from src.agents.investigation_agent import InvestigationAgent
from src.graph.workflow import run_workflow_sync
from src.models.schemas import BatchValidationResult


def _fail_validation() -> BatchValidationResult:
    return BatchValidationResult(
        batch_id="B002", product_type="aluminium_powder",
        calculated_status="FAIL", recorded_status="FAIL", discrepancy=False,
        failed_checks=[{"check": "purity_min", "measured": 98.6,
                        "limit": 99.0, "message": "purity 98.6 < min 99.0"}],
        missing_fields=[], limits_used={"purity_min_pct": 99.0}, errors=[],
    )


def test_rule_recommendations_present(tmp_path):
    agent = InvestigationAgent(sops_dir="data/sops", chroma_dir=str(tmp_path / "c"))
    inv = agent.investigate(_fail_validation())
    assert inv.demo_mode is True
    assert len(inv.recommendations) >= 1
    assert all("human approval" in r for r in inv.recommendations)


def test_groq_without_key_falls_back_honestly(tmp_path):
    # provider=groq but no key (and/or no groq package): must NOT pretend LLM ran.
    agent = InvestigationAgent(sops_dir="data/sops", chroma_dir=str(tmp_path / "c"),
                               provider="groq", groq_api_key="")
    inv = agent.investigate(_fail_validation())
    assert inv.demo_mode is True
    assert inv.llm_model == ""
    assert len(inv.recommendations) >= 1


def test_retry_broadens_retrieval(tmp_path):
    agent = InvestigationAgent(sops_dir="data/sops", chroma_dir=str(tmp_path / "c"))
    first = agent.investigate(_fail_validation(), attempt=1)
    second = agent.investigate(_fail_validation(), attempt=2)
    # Attempt 2 uses a wider query/top_k; both stay honest about evidence.
    assert first.demo_mode and second.demo_mode
    assert len(second.evidence) >= len(first.evidence)


def test_workflow_provider_threading(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/w.db")
    row = {"batch_id": "B002", "product_type": "aluminium_powder",
           "purity_pct": "98.6", "moisture_pct": "0.08",
           "particle_size_um": "25", "defect_count": "0",
           "inspection_status": "FAIL"}
    wf = run_workflow_sync(row, chroma_dir=str(tmp_path / "c"), provider="none")
    assert wf.investigation is not None
    assert len(wf.investigation.recommendations) >= 1
    assert wf.requires_human_review is True
