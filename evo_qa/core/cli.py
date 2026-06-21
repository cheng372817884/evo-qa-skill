"""
CLI entry — Evo QA v1.0

Global commands (no project required):
    doctor               Check environment
    setup                Auto-install missing deps
    health               (v1.0 phase 4) Test suite health report

Project commands (require <project>):
    init <project> --url <url>
    ingest <project> <file|url|text>
    design <project> <feature>            (v1.0 phase 3)
    plan <project> "<intent>"
    run <project> [change-id] [--dry-run] [--yes] [--headed]
    explore <project> "<charter>"          (v1.0 phase 3)
    learn <project>
    report <project> <run-id>              (v1.0 phase 5)
    heal <project> <run-id> [--yes]        (v1.0 phase 3)
    revive <project> <knowledge-id>        (v1.0 phase 4)
    status <project>
"""
from __future__ import annotations

import argparse
import json
import sys

# All output goes to stdout as JSON (machine-readable).
# Doctor/setup also have human-readable mode via --human.


def cmd_doctor(args) -> int:
    from . import doctor as D
    rep = D.doctor()
    if args.human:
        print(rep.summary_human)
        print()
        for c in rep.checks:
            print(f"{c.icon()} {c.name:35s} — {c.detail}")
    else:
        print(rep.to_json())
    return 0 if rep.ok else 1


def cmd_setup(args) -> int:
    from . import doctor as D
    if not args.yes and not args.dry_run:
        # Show what will happen first
        rep = D.doctor()
        if rep.ok:
            print("✅ Environment already ready. Nothing to do.")
            return 0
        print(rep.summary_human)
        print()
        try:
            ans = input("Proceed with auto-fix? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 130
        if ans not in ("y", "yes"):
            print("Aborted.")
            return 1

    result = D.setup(dry_run=args.dry_run)
    if args.human:
        print(result["final_summary"])
        print(f"\nFixed: {len(result['fixed'])}, "
              f"Failed: {len(result['failed'])}, "
              f"Skipped: {len(result['skipped'])}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["final_ok"] else 1


def cmd_with_orchestrator(args) -> int:
    """Dispatch to Orchestrator for project-scoped commands."""
    from .workspace import Workspace
    from .orchestrator import Orchestrator
    ws = Workspace(args.project)
    orch = Orchestrator(ws)

    if args.cmd == "init":
        result = orch.cmd_init(url=args.url, industry=args.industry,
                               language=args.language)
    elif args.cmd == "ingest":
        result = orch.cmd_ingest(args.location, kind=args.kind)
    elif args.cmd == "plan":
        result = orch.cmd_plan(args.intent, change_id=args.change_id,
                               explore=not args.no_explore)
    elif args.cmd == "run":
        result = orch.cmd_run_v1(args.change_id, headed=args.headed,
                                 dry_run=getattr(args, "dry_run", False),
                                 auto_yes=getattr(args, "yes", False))
    elif args.cmd == "learn":
        result = orch.cmd_learn()
    elif args.cmd == "status":
        result = orch.cmd_status()
    elif args.cmd == "design":
        result = orch.cmd_design(args.feature)
    elif args.cmd == "explore":
        result = orch.cmd_explore(args.charter,
                                  timebox=args.timebox)
    elif args.cmd == "report":
        result = orch.cmd_report(args.run_id)
    elif args.cmd == "heal":
        result = orch.cmd_heal(args.run_id, auto_yes=args.yes)
    elif args.cmd == "revive":
        result = orch.cmd_revive(args.knowledge_id)
    elif args.cmd == "health":
        result = orch.cmd_health()
    elif args.cmd == "curate":
        result = orch.cmd_curate(force=args.force)
    elif args.cmd == "reflect":
        result = orch.cmd_reflect(force=args.force)
    elif args.cmd == "drain":
        result = orch.cmd_drain()
    elif args.cmd == "validate-ctrf":
        result = orch.cmd_validate_ctrf(args.run_id, strict=args.strict)
    elif args.cmd == "export":
        if args.format == "okf":
            # OKF goes through the dedicated subsystem, not the legacy
            # mem0/ctrf/json exporter. We bypass orch.cmd_export here.
            from . import okf as okf_mod
            from .workspace import Workspace
            try:
                ws_root = Workspace(args.project).root
            except Exception as e:
                result = {"ok": False, "msg": f"workspace lookup failed: {e}"}
            else:
                out_dir = args.out or str(ws_root / "exports" / "okf-bundle")
                try:
                    audit = okf_mod.export_to_bundle(
                        workspace_root=ws_root,
                        out_dir=out_dir,
                        include_single_run=getattr(args, "include_single_run", False),
                        bundle_name=getattr(args, "bundle_name", "") or None,
                    )
                    result = {
                        "ok": True,
                        "format": "okf",
                        "out_dir": out_dir,
                        "audit": audit.get("summary", {}),
                        "redaction_event_count":
                            len(audit.get("redactions", [])),
                        "skipped_low_confidence":
                            audit.get("skipped_low_confidence", 0),
                    }
                except Exception as e:
                    result = {"ok": False, "msg": f"OKF export failed: {e}"}
        else:
            result = orch.cmd_export(args.format, out_dir=args.out or None)
    else:
        result = {"ok": False, "msg": f"Unknown cmd: {args.cmd}"}

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def cmd_brain(args) -> int:
    """v1.4 — OKF brain operations (validate / import).

    `export --format okf` lives under the `export` command, not here, to
    keep symmetry with `export --format mem0` etc.
    """
    from . import okf as okf_mod
    from pathlib import Path

    if args.brain_cmd == "validate":
        bundle = Path(args.bundle)
        issues = okf_mod.validate_bundle(bundle)
        result = {
            "ok": len(issues) == 0,
            "bundle": str(bundle),
            "issues": issues,
            "issue_count": len(issues),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1

    if args.brain_cmd == "import":
        from .workspace import Workspace
        try:
            ws_root = Workspace(args.project).root
        except Exception as e:
            print(json.dumps({"ok": False, "msg": f"workspace lookup failed: {e}"},
                            indent=2, ensure_ascii=False))
            return 1
        report = okf_mod.import_bundle(
            bundle_root=args.bundle,
            workspace_root=ws_root,
            bundle_label=args.label or None,
            strict=args.strict,
        )
        result = {"ok": report.get("status") == "imported", **report}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1

    print(json.dumps({"ok": False, "msg": f"unknown brain cmd: {args.brain_cmd}"},
                    indent=2, ensure_ascii=False))
    return 1


def cmd_creds(args) -> int:
    """User-level credential store. Not project-scoped."""
    from .credentials import get_default_store
    from .credentials.interactive import (
        list_credentials, remove_credential, wizard_add,
        add_credential_noninteractive, select_for_url,
    )

    store = get_default_store()
    sub = getattr(args, "creds_cmd", None)

    if sub == "list":
        items = list_credentials(store=store, url=getattr(args, "url", None))
        print(json.dumps({"ok": True, "count": len(items),
                          "entries": items},
                         indent=2, ensure_ascii=False))
        return 0

    if sub == "add":
        if getattr(args, "url", None) and getattr(args, "username", None) \
                and getattr(args, "password", None):
            # Non-interactive path (script-friendly).
            res = add_credential_noninteractive(
                url=args.url, username=args.username,
                password=args.password,
                label=getattr(args, "label", "") or "",
                prefer_backend=getattr(args, "backend", "auto"),
                consented_plaintext=getattr(args, "yes_plaintext", False),
                store=store,
            )
        else:
            # Interactive wizard.
            res = wizard_add(store=store,
                             default_url=getattr(args, "url", None),
                             human=True)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("ok") else 1

    if sub == "remove":
        res = remove_credential(args.entry_id, store=store)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("ok") else 1

    if sub == "suggest":
        sel = select_for_url(url=getattr(args, "url", None), store=store)
        print(json.dumps({"ok": True, **sel},
                         indent=2, ensure_ascii=False))
        return 0

    print(json.dumps({"ok": False, "msg": "Unknown creds sub-command."},
                     indent=2))
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="evo_qa",
        description="Evo QA v1.0 — A QA agent that learns and grows")
    p.add_argument("--human", action="store_true",
                   help="Human-readable output (default: JSON)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # ---- Global ----
    sp = sub.add_parser("doctor", help="Check environment health")
    sp.add_argument("--human", action="store_true", dest="human_sub",
                    help="Human-readable output")

    sp = sub.add_parser("setup", help="Auto-install missing dependencies")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--yes", action="store_true",
                    help="Skip confirmation prompt")
    sp.add_argument("--human", action="store_true", dest="human_sub",
                    help="Human-readable output")

    # ---- Global: creds (user-level credential store) ----
    sp = sub.add_parser("creds",
                        help="Manage saved credentials (URL/user/password)")
    creds_sub = sp.add_subparsers(dest="creds_cmd", required=True)

    cs = creds_sub.add_parser("list", help="List saved credentials "
                                            "(no passwords)")
    cs.add_argument("--url", default=None,
                    help="Filter by URL")

    cs = creds_sub.add_parser("add",
                              help="Add a credential. Interactive by default; "
                                   "pass --url/--username/--password for "
                                   "non-interactive use.")
    cs.add_argument("--url", default=None)
    cs.add_argument("--username", default=None)
    cs.add_argument("--password", default=None,
                    help="WARNING: visible in shell history. Prefer "
                         "interactive mode.")
    cs.add_argument("--label", default=None)
    cs.add_argument("--backend", default="auto",
                    choices=["auto", "keyring", "plaintext_file"])
    cs.add_argument("--yes-plaintext", action="store_true",
                    help="Required to consent to plaintext storage in "
                         "non-interactive mode.")

    cs = creds_sub.add_parser("remove", help="Delete a credential")
    cs.add_argument("entry_id")

    cs = creds_sub.add_parser("suggest",
                              help="Show ranked credential suggestions for "
                                   "an optional URL")
    cs.add_argument("--url", default=None)

    # ---- Project: init ----
    sp = sub.add_parser("init", help="Initialize a project workspace")
    sp.add_argument("project")
    sp.add_argument("--url", required=True)
    sp.add_argument("--industry", default="")
    sp.add_argument("--language", default="auto",
                    choices=["python", "typescript", "auto"])

    # ---- Project: ingest ----
    sp = sub.add_parser("ingest", help="Ingest reference material")
    sp.add_argument("project")
    sp.add_argument("location")
    sp.add_argument("--kind", default=None,
                    choices=["file", "directory", "url", "text"])

    # ---- Project: design (Pillar 1 of v1.0) ----
    sp = sub.add_parser("design",
                        help="Design test cases using QA heuristics")
    sp.add_argument("project")
    sp.add_argument("feature", help="What to design tests for")

    # ---- Project: plan ----
    sp = sub.add_parser("plan", help="Plan tests for an intent")
    sp.add_argument("project")
    sp.add_argument("intent")
    sp.add_argument("--change-id", default=None)
    sp.add_argument("--no-explore", action="store_true")

    # ---- Project: run ----
    sp = sub.add_parser("run", help="Execute the plan")
    sp.add_argument("project")
    sp.add_argument("change_id", nargs="?", default=None)
    sp.add_argument("--headed", action="store_true")
    sp.add_argument("--dry-run", action="store_true",
                    help="Show steps without executing")
    sp.add_argument("--yes", action="store_true",
                    help="Skip confirmation prompt")

    # ---- Project: explore (Pillar 3 of v1.0) ----
    sp = sub.add_parser("explore", help="Exploratory testing session")
    sp.add_argument("project")
    sp.add_argument("charter")
    sp.add_argument("--timebox", type=int, default=30,
                    help="Session timebox in minutes (default 30)")

    # ---- Project: learn ----
    sp = sub.add_parser("learn", help="Deep retrospective + derive patterns")
    sp.add_argument("project")

    # ---- Project: report (Pillar 5) ----
    sp = sub.add_parser("report", help="Generate HTML report")
    sp.add_argument("project")
    sp.add_argument("run_id")

    # ---- Project: heal ----
    sp = sub.add_parser("heal", help="Re-run with selector healing")
    sp.add_argument("project")
    sp.add_argument("run_id")
    sp.add_argument("--yes", action="store_true")

    # ---- Project: revive (pseudo-forgetting) ----
    sp = sub.add_parser("revive",
                        help="Restore a deprecated/archived knowledge entry")
    sp.add_argument("project")
    sp.add_argument("knowledge_id")

    # ---- Project: health (Pillar 8) ----
    sp = sub.add_parser("health", help="Test suite health report")
    sp.add_argument("project")

    # ---- Scheduler: curate (apply brain state transitions) ----
    sp = sub.add_parser("curate",
                        help="Run brain CuratorJob (apply state transitions)")
    sp.add_argument("project")
    sp.add_argument("--force", action="store_true",
                    help="Bypass throttle and run now")

    # ---- Scheduler: reflect (LLM stub) ----
    sp = sub.add_parser("reflect",
                        help="Run ReflectionJob (LLM stub for v1.0.2)")
    sp.add_argument("project")
    sp.add_argument("--force", action="store_true",
                    help="Bypass run-count threshold")

    # ---- Bus: drain (synchronous backlog processing) ----
    sp = sub.add_parser("drain",
                        help="Synchronously drain RunBus backlog")
    sp.add_argument("project")

    # ---- Project: status ----
    sp = sub.add_parser("status", help="Show project workspace status")
    sp.add_argument("project")

    # ---- v1.1: Validate CTRF report ----
    sp = sub.add_parser(
        "validate-ctrf",
        help="Validate result.ctrf.json against the v1.0 contract",
    )
    sp.add_argument("project")
    sp.add_argument("run_id",
                    help="Run id to validate (looks for runs/<id>/result.ctrf.json)")
    sp.add_argument("--strict", action="store_true",
                    help="Treat Evo-QA-specific MUSTs as hard errors "
                         "(default: warnings, for backwards compat).")

    # ---- v1.1: Export brain (mem0 / ctrf / json) ----
    sp = sub.add_parser(
        "export",
        help="Export brain or runs in a portable format",
    )
    sp.add_argument("project")
    sp.add_argument("--format", required=True,
                    choices=["mem0", "ctrf", "json", "okf"],
                    help="mem0: agent-memory portable format. "
                         "ctrf: bundle all run CTRF docs. "
                         "json: raw brain dump. "
                         "okf: Open Knowledge Format v0.1 bundle "
                         "(★[P6], cross-org sharing, REQUIREMENTS-v1.4 §20).")
    sp.add_argument("--out", default="",
                    help="Output path (default: <workspace>/exports/<format>/)")
    sp.add_argument("--include-single-run", action="store_true",
                    help="OKF only: include single-run observations "
                         "(NOT recommended; bypasses §18.2 Gate 1).")
    sp.add_argument("--bundle-name", default="",
                    help="OKF only: display name for the bundle README.")

    # ---- v1.4: brain subcommand group (OKF import + future doctor/promote) ----
    sp = sub.add_parser(
        "brain",
        help="Brain governance: import OKF bundles, doctor (audit), promote",
    )
    brain_sub = sp.add_subparsers(dest="brain_cmd", required=True)

    bs = brain_sub.add_parser(
        "import",
        help="Import an OKF bundle into brain/_imported/ staging "
             "(REQUIREMENTS-v1.4 §20.3.B).",
    )
    bs.add_argument("project",
                    help="Target workspace (project name).")
    bs.add_argument("bundle",
                    help="Path to the OKF bundle directory.")
    bs.add_argument("--label", default="",
                    help="Subdirectory name under brain/_imported/. "
                         "Default: <bundle-basename>-<YYYYMMDD>.")
    bs.add_argument("--strict", action="store_true",
                    help="Reject non-conformant bundles. "
                         "Default: best-effort (per OKF SPEC §9).")

    bs = brain_sub.add_parser(
        "validate",
        help="Validate an OKF bundle for SPEC §9 conformance "
             "(read-only; nothing imported).",
    )
    bs.add_argument("bundle",
                    help="Path to the OKF bundle directory.")

    args = p.parse_args(argv)
    # Allow --human at top level OR after subcommand
    args.human = getattr(args, "human", False) or getattr(args, "human_sub", False)

    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "setup":
        return cmd_setup(args)
    if args.cmd == "creds":
        return cmd_creds(args)
    if args.cmd == "brain":
        return cmd_brain(args)
    return cmd_with_orchestrator(args)


if __name__ == "__main__":
    sys.exit(main())
