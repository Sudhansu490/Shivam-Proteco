"""Primary CLI entry point. Base validation works without LLM key or database."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.settings import get_settings
from src.services.quality_service import QualityService


def cmd_validate(args) -> int:
    settings = get_settings()
    svc = QualityService(settings)
    csv_path = args.csv or settings.csv_path
    try:
        summary = svc.summary(csv_path)
    except FileNotFoundError:
        print(f"CSV not found: {csv_path}")
        print("Expected data/quality_batches.csv with batch_id,product_type,purity_pct,moisture_pct,particle_size_um,defect_count,inspection_status")
        return 2
    print("=== Manufacturing Quality Intelligence — CSV Validation (fictional demo data) ===")
    print(f"CSV: {csv_path} | Limits: {settings.limits_path}")
    print(f"Total: {summary['total']} | PASS={summary['counts'].get('PASS',0)} "
          f"FAIL={summary['counts'].get('FAIL',0)} REVIEW={summary['counts'].get('REVIEW',0)} "
          f"| Discrepancies: {summary['discrepancies']}")
    for r in summary["results"]:
        flag = " [DISCREPANCY]" if r.discrepancy else ""
        print(f"- {r.batch_id} {r.product_type}: calc={r.calculated_status} recorded={r.recorded_status}{flag}")
        for fc in r.failed_checks:
            print(f"    FAIL {fc.check}: {fc.message}")
        if r.missing_fields:
            print(f"    missing: {', '.join(r.missing_fields)}")
        if r.errors:
            for e in r.errors:
                print(f"    note: {e}")
    if args.batch:
        print(f"\n--- Detail for {args.batch} ---")
        try:
            wf = svc.investigate(args.batch, csv_path)
            print(f"iterations={wf.iterations} final={wf.final_disposition} human_review={wf.requires_human_review}")
            if wf.investigation:
                print(f"summary: {wf.investigation.summary}")
                for e in wf.investigation.evidence:
                    print(f"  evidence: {e.source_title} §{e.section} ({e.document_id} v{e.version})")
            if wf.verification:
                print(f"verification supported={wf.verification.supported}: {wf.verification.reasons}")
        except KeyError as e:
            print(str(e))
            return 1
    return 0


def cmd_test(_args) -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=str(ROOT))
    return r.returncode


def cmd_api(args) -> int:
    settings = get_settings()
    host = args.host or settings.api_host
    port = args.port or settings.api_port
    print(f"Starting FastAPI at http://{host}:{port} (docs: /docs). Synthetic demo only.")
    import uvicorn
    uvicorn.run("src.api.app:app", host=host, port=port, reload=False)
    return 0


def cmd_dashboard(args) -> int:
    """Serve the HTML/CSS/JS frontend (via the API server) and open it in a browser."""
    import threading
    import webbrowser
    settings = get_settings()
    host = getattr(args, "host", "") or settings.api_host
    port = getattr(args, "port", 0) or settings.api_port
    url = f"http://{host}:{port}/"
    print(f"Starting web frontend at {url} (API docs: http://{host}:{port}/docs). Synthetic demo only.")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    import uvicorn
    uvicorn.run("src.api.app:app", host=host, port=port, reload=False)
    return 0


def cmd_ingest(_args) -> int:
    from src.rag.ingestion import ingest_sops_dir, chunks_to_dicts
    from src.database.connection import get_engine, init_schema
    from src.database.repositories import DocumentRepository
    settings = get_settings()
    chunks = ingest_sops_dir(settings.sops_dir)
    print(f"Ingested {len(chunks)} chunks from {settings.sops_dir} (fictional SOPs).")
    docs = sorted({c.document_id for c in chunks})
    print(f"Documents: {docs}")
    engine = get_engine(settings.database_url) if settings.has_database else None
    if engine is not None:
        init_schema(engine)
    try:
        n = DocumentRepository(engine, chroma_dir=settings.chroma_dir).upsert_chunks(chunks_to_dicts(chunks))
        print(f"Persisted {n} chunks to ChromaDB at {settings.chroma_dir}.")
    except Exception as e:
        print(f"ChromaDB ingest failed ({e}); file/keyword mode only.")
    return 0


def cmd_demo(args) -> int:
    settings = get_settings()
    svc = QualityService(settings)
    batch = args.batch or "B002"
    print(f"Demo workflow for {batch} (rule-based demo mode unless LLM configured).")
    try:
        wf = svc.investigate(batch, args.csv or settings.csv_path)
    except (FileNotFoundError, KeyError) as e:
        print(str(e))
        return 1
    print(f"validation: {wf.validation.calculated_status} (recorded {wf.validation.recorded_status})")
    print(f"iterations: {wf.iterations} final: {wf.final_disposition} human_review: {wf.requires_human_review}")
    if wf.investigation:
        print("facts:"); [print(f" - {f}") for f in wf.investigation.facts]
        print("hypotheses:"); [print(f" - {h}") for h in wf.investigation.hypotheses]
        print("recommendations:"); [print(f" - {r}") for r in wf.investigation.recommendations]
        print(f"evidence (demo_mode={wf.investigation.demo_mode}, llm_model={wf.investigation.llm_model or 'n/a'}):")
        for e in wf.investigation.evidence:
            print(f" - {e.source_title} §{e.section} [{e.document_id} v{e.version}] score={e.score}")
        if not wf.investigation.evidence:
            print(" - (none retrieved)")
    if wf.verification:
        print(f"verification: supported={wf.verification.supported} reasons={wf.verification.reasons}")
    print(f"notes: {wf.notes}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manufacturing Quality Intelligence (fictional demo)")
    sub = p.add_subparsers(dest="command")
    pv = sub.add_parser("validate", help="Validate CSV (default)")
    pv.add_argument("--csv", default="")
    pv.add_argument("--batch", default="")
    pv.set_defaults(func=cmd_validate)
    pt = sub.add_parser("test", help="Run pytest")
    pt.set_defaults(func=cmd_test)
    pa = sub.add_parser("api", help="Start FastAPI")
    pa.add_argument("--host", default="")
    pa.add_argument("--port", type=int, default=0)
    pa.set_defaults(func=cmd_api)
    pd = sub.add_parser("dashboard", help="Serve HTML/CSS/JS frontend + open browser")
    pd.add_argument("--host", default="")
    pd.add_argument("--port", type=int, default=0)
    pd.set_defaults(func=cmd_dashboard)
    pi = sub.add_parser("ingest", help="Ingest SOPs")
    pi.set_defaults(func=cmd_ingest)
    pdemo = sub.add_parser("demo", help="Run demo workflow for one batch")
    pdemo.add_argument("--batch", default="B002")
    pdemo.add_argument("--csv", default="")
    pdemo.set_defaults(func=cmd_demo)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # default: validate all
        args.csv = getattr(args, "csv", "") or ""
        args.batch = getattr(args, "batch", "") or ""
        return cmd_validate(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
