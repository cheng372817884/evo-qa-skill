"""
Doctor — Environment health check + auto-install for Evo QA v1.0.

Designed for non-technical users (BA/QA): zero command-line required.
- `python -m evo_qa.core.cli doctor` → see what's wrong
- `python -m evo_qa.core.cli setup`  → auto-fix what can be fixed

All output is in English.
"""
from __future__ import annotations

import json
import os
import shutil as _shutil
import socket
import ssl
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

WORKSPACE_ROOT = Path(os.environ.get("EVO_QA_WORKSPACE",
                                     "./qa_workspace")).resolve()


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    fix_hint: str = ""
    auto_fixable: bool = False
    fix_command: str = ""
    severity: str = "error"  # error | warning | info

    def icon(self) -> str:
        if self.ok:
            return "✅"
        if self.severity == "warning":
            return "⚠️"
        if self.auto_fixable:
            return "🔧"
        return "❌"


@dataclass
class DoctorReport:
    ok: bool
    checks: List[CheckResult] = field(default_factory=list)
    summary_human: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [asdict(c) for c in self.checks],
            "summary_human": self.summary_human,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ============================================================
# Individual checks
# ============================================================
def check_python() -> CheckResult:
    v = sys.version_info
    if v >= (3, 9):
        return CheckResult("Python >= 3.9", True, f"{v.major}.{v.minor}.{v.micro}")
    return CheckResult(
        "Python >= 3.9", False,
        f"Found Python {v.major}.{v.minor} (too old)",
        fix_hint="Please install Python 3.9 or newer, then re-run.",
    )


def check_pip() -> CheckResult:
    try:
        out = subprocess.run([sys.executable, "-m", "pip", "--version"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return CheckResult("pip available", True,
                               out.stdout.strip().split("\n")[0])
    except Exception as e:
        return CheckResult("pip available", False, f"Error: {e}",
                           fix_hint="Please install pip.")
    return CheckResult("pip available", False, "pip not callable",
                       fix_hint="Please install pip.")


def _pip_install_cmd(*pkgs: str) -> str:
    return f"{sys.executable} -m pip install " + " ".join(pkgs)


def check_playwright() -> CheckResult:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return CheckResult(
            "playwright (Python package)", False, "Not installed",
            fix_hint="Auto-install: pip install playwright pytest-playwright",
            auto_fixable=True,
            fix_command=_pip_install_cmd("playwright", "pytest-playwright"),
        )
    try:
        import importlib.metadata as md
        pwv = md.version("playwright")
    except Exception:
        pwv = "unknown"
    return CheckResult("playwright (Python package)", True,
                       f"version {pwv}")


def check_pytest_playwright() -> CheckResult:
    try:
        import pytest_playwright  # noqa: F401
        return CheckResult("pytest-playwright", True, "installed")
    except ImportError:
        return CheckResult(
            "pytest-playwright", False, "Not installed",
            fix_hint="Auto-install: pip install pytest-playwright",
            auto_fixable=True,
            fix_command=_pip_install_cmd("pytest-playwright"),
        )


def check_jinja2() -> CheckResult:
    try:
        import jinja2  # noqa: F401
        return CheckResult("jinja2 (report templating)", True, "installed")
    except ImportError:
        return CheckResult(
            "jinja2 (report templating)", False, "Not installed",
            fix_hint="Auto-install: pip install jinja2",
            auto_fixable=True,
            fix_command=_pip_install_cmd("jinja2"),
        )


def check_pyyaml() -> CheckResult:
    try:
        import yaml  # noqa: F401
        return CheckResult("PyYAML (config parsing)", True, "installed")
    except ImportError:
        return CheckResult(
            "PyYAML (config parsing)", False, "Not installed",
            fix_hint="Auto-install: pip install pyyaml",
            auto_fixable=True,
            fix_command=_pip_install_cmd("pyyaml"),
        )


def check_faker() -> CheckResult:
    """Used by atoms.data.unique() for test data generation."""
    try:
        import faker  # noqa: F401
        return CheckResult("Faker (test data generator)", True, "installed")
    except ImportError:
        return CheckResult(
            "Faker (test data generator)", False, "Not installed",
            fix_hint="Auto-install: pip install Faker",
            auto_fixable=True,
            fix_command=_pip_install_cmd("Faker"),
        )


def check_chromium() -> CheckResult:
    """Try to launch headless Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return CheckResult(
            "Chromium browser", False,
            "playwright package missing — skipping browser check",
            fix_hint="Install playwright first.",
            severity="warning",
        )

    try:
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(headless=True)
                version = b.version
                b.close()
                return CheckResult("Chromium browser", True,
                                   f"version {version}")
            except Exception as e:
                msg = str(e)
                if ("Executable doesn't exist" in msg
                        or "playwright install" in msg):
                    return CheckResult(
                        "Chromium browser", False,
                        "Browser binary not downloaded",
                        fix_hint="Auto-install: playwright install chromium",
                        auto_fixable=True,
                        fix_command=(f"{sys.executable} -m playwright install "
                                     "chromium"),
                    )
                return CheckResult(
                    "Chromium browser", False,
                    f"Launch failed: {msg[:200]}",
                    fix_hint="Try: playwright install chromium",
                    auto_fixable=True,
                    fix_command=(f"{sys.executable} -m playwright install "
                                 "chromium"),
                )
    except Exception as e:
        return CheckResult("Chromium browser", False,
                           f"Unexpected error: {e}")


def check_network() -> CheckResult:
    """Check HTTPS connectivity to common dependency hosts.

    Fail-soft: returns a warning instead of error so users behind strict
    proxies aren't blocked from local-only operations.
    """
    hosts = ["pypi.org", "github.com", "registry.npmjs.org"]
    reachable, failed = [], []

    ctx = ssl.create_default_context()
    # Some corp envs have MITM proxies; fall back to permissive context if
    # strict TLS fails (we still warn, not error).
    permissive = ssl._create_unverified_context()

    for host in hosts:
        ok = False
        for context in (ctx, permissive):
            try:
                req = urllib.request.Request(f"https://{host}/",
                                             method="HEAD")
                with urllib.request.urlopen(req, timeout=5,
                                            context=context) as resp:
                    if resp.status < 500:
                        ok = True
                        break
            except (urllib.error.URLError, socket.timeout, Exception):
                continue
        (reachable if ok else failed).append(host)

    if not failed:
        return CheckResult("Network connectivity", True,
                           f"Reachable: {', '.join(reachable)}")
    if reachable:
        return CheckResult(
            "Network connectivity", False,
            (f"Partial: reachable={reachable} failed={failed}"),
            fix_hint=("Some hosts unreachable — corporate proxy? "
                      "pip/playwright install may need PROXY env vars."),
            severity="warning",
        )
    return CheckResult(
        "Network connectivity", False,
        f"All checked hosts unreachable: {failed}",
        fix_hint=("Check internet/proxy. You can still use the skill "
                  "offline if dependencies are pre-installed."),
        severity="warning",
    )


def check_disk_space(min_gb: float = 1.0) -> CheckResult:
    # Use workspace root's anchor so we measure the right drive on Windows.
    # Falls back to '.' (current directory) if anchor empty.
    _probe = str(WORKSPACE_ROOT.resolve().anchor or ".")
    free_bytes = _shutil.disk_usage(_probe).free
    free_gb = free_bytes / (1024 ** 3)
    if free_gb >= min_gb:
        return CheckResult("Disk space", True, f"{free_gb:.1f} GB free")
    return CheckResult(
        "Disk space", False,
        f"Only {free_gb:.1f} GB free (need >= {min_gb} GB)",
        fix_hint="Free up some disk space, then re-run.",
    )


def check_workspace_root() -> CheckResult:
    root = WORKSPACE_ROOT
    if root.exists():
        n = len([p for p in root.iterdir()
                 if p.is_dir() and not p.name.startswith("_")
                 and not p.name.startswith(".")])
        return CheckResult("Workspace root", True,
                           f"Ready, {n} project(s) so far")
    return CheckResult(
        "Workspace root", False, f"{root} does not exist",
        fix_hint="Auto-create",
        auto_fixable=True, fix_command=f"mkdir -p {root}",
    )


# ============================================================
# Aggregator
# ============================================================
ALL_CHECKS = [
    check_python,
    check_pip,
    check_playwright,
    check_pytest_playwright,
    check_jinja2,
    check_pyyaml,
    check_faker,
    check_chromium,
    check_network,
    check_disk_space,
    check_workspace_root,
]


def doctor() -> DoctorReport:
    """Run all checks and return a DoctorReport."""
    results: List[CheckResult] = []
    for fn in ALL_CHECKS:
        try:
            results.append(fn())
        except Exception as e:
            results.append(CheckResult(fn.__name__, False,
                                       f"Check raised: {e}"))

    # warnings don't fail the overall ok status
    real_failures = [c for c in results
                     if not c.ok and c.severity != "warning"]
    all_ok = len(real_failures) == 0
    bad = [c for c in results if not c.ok]
    fixable = [c for c in bad if c.auto_fixable]

    if all_ok and not bad:
        summary = "✅ Environment ready. You can start testing."
    elif all_ok and bad:
        summary = ("✅ Environment ready (with warnings).\n" +
                   "\n".join(f"  ⚠️ {c.name}: {c.detail}" for c in bad))
    else:
        lines = [f"⚠️ Found {len(real_failures)} issue(s):"]
        for c in real_failures:
            mark = "🔧 Auto-fixable" if c.auto_fixable else "❌ Manual fix"
            lines.append(f"  {mark} - {c.name}: {c.detail}")
            if c.fix_hint:
                lines.append(f"      → {c.fix_hint}")
        if fixable:
            lines.append("")
            lines.append(
                f"💡 Run `python -m evo_qa.core.cli setup` "
                f"to auto-fix {len(fixable)} item(s)."
            )
        summary = "\n".join(lines)

    return DoctorReport(ok=all_ok, checks=results, summary_human=summary)


def setup(auto_yes: bool = True, dry_run: bool = False) -> dict:
    """Auto-install missing dependencies based on doctor() report.

    Returns a dict with fixed/failed/skipped lists and final summary.
    """
    rep = doctor()
    fixed: List[dict] = []
    failed: List[dict] = []
    skipped: List[dict] = []

    if rep.ok:
        return {
            "fixed": [], "failed": [], "skipped": [],
            "final_ok": True,
            "final_summary": rep.summary_human,
            "message": "Nothing to do — environment already ready.",
        }

    for c in rep.checks:
        if c.ok or c.severity == "warning":
            continue
        if not c.auto_fixable or not c.fix_command:
            skipped.append({
                "name": c.name,
                "reason": c.detail,
                "manual_hint": c.fix_hint,
            })
            continue
        if dry_run:
            skipped.append({
                "name": c.name,
                "reason": "dry_run",
                "would_run": c.fix_command,
            })
            continue

        print(f"🔧 Fixing: {c.name} ...")
        print(f"   $ {c.fix_command}")
        try:
            out = subprocess.run(c.fix_command, shell=True,
                                 capture_output=True, text=True,
                                 timeout=600)
            if out.returncode == 0:
                fixed.append({"name": c.name,
                              "stdout_tail": out.stdout[-500:]})
                print("   ✅ done\n")
            else:
                failed.append({
                    "name": c.name,
                    "returncode": out.returncode,
                    "stderr_tail": out.stderr[-500:],
                })
                print(f"   ❌ failed (rc={out.returncode})\n")
        except subprocess.TimeoutExpired:
            failed.append({"name": c.name, "error": "timeout (>10min)"})
        except Exception as e:
            failed.append({"name": c.name, "error": str(e)})

    final = doctor()
    return {
        "fixed": fixed,
        "failed": failed,
        "skipped": skipped,
        "final_ok": final.ok,
        "final_summary": final.summary_human,
    }


# ============================================================
# CLI entry (also reachable via `python -m evo_qa.core.cli doctor`)
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Evo QA — Environment doctor & setup")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("doctor", help="Run health check (read-only)")
    sp = sub.add_parser("setup", help="Auto-fix issues")
    sp.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cmd = args.cmd or "doctor"
    if cmd == "doctor":
        rep = doctor()
        if args.json:
            print(rep.to_json())
        else:
            print(rep.summary_human)
            print()
            for c in rep.checks:
                print(f"{c.icon()} {c.name:35s} — {c.detail}")
        sys.exit(0 if rep.ok else 1)
    elif cmd == "setup":
        result = setup(dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result["final_summary"])
            print(f"\nFixed: {len(result['fixed'])}, "
                  f"Failed: {len(result['failed'])}, "
                  f"Skipped: {len(result['skipped'])}")
        sys.exit(0 if result["final_ok"] else 1)
