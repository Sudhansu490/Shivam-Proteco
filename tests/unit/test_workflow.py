"""Workflow tests: routing, retries, evidence, human review. Offline."""
from __future__ import annotations

from src.graph.workflow import run_workflow_sync, run_workflow
from src.graph.state import QualityState
from src.graph.nodes import should_retry
from src.models.schemas import BatchValidationResult, InvestigationResult
from src.agents.verification_agent import VerificationAgent


def _row(batch_id="B002", product_type="aluminium_powder", purity="98.6",
         moisture="0.08", particle="25", defects="0", status="FAIL"):
    return {"batch_id": batch_id, "product_type": product_type,
            "purity_pct": purity, "moisture_pct": moisture,
            "particle_size_um": particle, "defect_count": defects,
            "inspection_status": status}


def test_workflow_fail_path_requires_review():
    wf = run_workflow_sync(_row(), max_retries=3)
    assert wf.validation.calculated_status == "FAIL"
    assert wf.requires_human_review is True
    assert wf.iterations >= 1
    assert wf.iterations <= 3
    assert wf.final_disposition in ("FAIL", "REVIEW")


def test_workflow_pass_path():
    wf = run_workflow_sync(_row(batch_id="B001", purity="99.4", moisture="0.05",
                                particle="25", status="PASS"), max_retries=3)
    assert wf.validation.calculated_status == "PASS"
    assert wf.requires_human_review is True  # never auto-release


def test_workflow_review_path():
    wf = run_workflow_sync(_row(batch_id="RX", product_type="unknown_alloy",
                                status="PASS"), max_retries=2)
    assert wf.validation.calculated_status == "REVIEW"
    assert wf.final_disposition == "REVIEW"
    assert wf.requires_human_review is True


def test_retry_bounded():
    wf = run_workflow_sync(_row(), max_retries=3)
    assert wf.iterations <= 3


def test_should_retry_logic():
    s = QualityState(batch_id="X", row={}, max_retries=3, iterations=1)
    s.validation = BatchValidationResult(batch_id="X", product_type="aluminium_powder",
                                         calculated_status="FAIL")
    from src.models.schemas import InvestigationResult as IR, VerificationResult as VR
    s.investigation = IR(batch_id="X", facts=[], hypotheses=[], evidence=[])
    s.verification = VR(batch_id="X", supported=True, reasons=["ok"])
    assert should_retry(s) == "done"
    s.verification = VR(batch_id="X", supported=False, reasons=["no evidence"])
    s.iterations = 3
    assert should_retry(s) == "review"
    s.iterations = 1
    assert should_retry(s) == "retry"


def test_insufficient_evidence_fails_verification():
    inv = InvestigationResult(batch_id="X", facts=["f"], hypotheses=["HYPOTHESIS: x"],
                              evidence=[], summary="s", demo_mode=True)
    v = VerificationAgent().verify(inv)
    assert v.supported is False
    assert any("No SOP evidence" in r for r in v.reasons)


def test_llm_failure_fallback_is_demo_mode():
    # run_workflow never requires an LLM; result must be demo_mode
    wf = run_workflow(_row(), prefer_langgraph=False)
    assert wf.investigation is not None
    assert wf.investigation.demo_mode is True


def test_human_review_always_required():
    for row in [_row(), _row(batch_id="B001", purity="99.4", status="PASS")]:
        wf = run_workflow_sync(row)
        assert wf.requires_human_review is True
