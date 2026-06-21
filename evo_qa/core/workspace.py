"""
Workspace — project workspace path management + config IO.

Each project under test gets a workspace directory like this:

    qa_workspace/<project>/
    ├── config.yaml          # WorkspaceConfig
    ├── brain/               # L3 project brain
    │   ├── ingested/        # raw materials
    │   ├── digest/          # distilled notes
    │   └── insights.md      # agent's opinions
    ├── openqa/
    │   ├── specs/           # project "current state" knowledge (grows)
    │   ├── changes/         # in-flight work
    │   └── archive/         # completed work
    ├── tests/               # artifacts (humans can run them too)
    └── reports/             # test reports

The default root is `./qa_workspace/` relative to the current working
directory. Override via the EVO_QA_WORKSPACE environment variable,
or pass an explicit `root` to the Workspace constructor.

See references/VISION.md for the full design.
"""

from __future__ import annotations
import os
import yaml
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .schemas import WorkspaceConfig


# Default workspace root. Resolution order:
#   1. explicit `root` arg to Workspace(...)
#   2. EVO_QA_WORKSPACE env var
#   3. ./qa_workspace/ (relative to CWD)
DEFAULT_ROOT = Path(
    os.environ.get("EVO_QA_WORKSPACE", "./qa_workspace")
).resolve()


class Workspace:
    """One project's workspace."""

    def __init__(self, project: str, root: Optional[Path] = None):
        self.project = project
        self.root = (root or DEFAULT_ROOT) / project

    # ---- paths ----

    @property
    def config_path(self) -> Path:
        return self.root / "config.yaml"

    @property
    def brain_dir(self) -> Path:
        return self.root / "brain"

    @property
    def ingested_dir(self) -> Path:
        return self.brain_dir / "ingested"

    @property
    def digest_dir(self) -> Path:
        return self.brain_dir / "digest"

    @property
    def insights_path(self) -> Path:
        return self.brain_dir / "insights.md"

    @property
    def openqa_dir(self) -> Path:
        return self.root / "openqa"

    @property
    def specs_dir(self) -> Path:
        return self.openqa_dir / "specs"

    @property
    def changes_dir(self) -> Path:
        return self.openqa_dir / "changes"

    @property
    def archive_dir(self) -> Path:
        return self.openqa_dir / "archive"

    @property
    def tests_dir(self) -> Path:
        return self.root / "tests"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def selectors_path(self) -> Path:
        return self.specs_dir / "_global" / "selectors.json"

    @property
    def pages_path(self) -> Path:
        return self.specs_dir / "_global" / "pages.md"

    # ---- operations ----

    def exists(self) -> bool:
        return self.config_path.exists()

    def init(self, config: WorkspaceConfig) -> None:
        """Initialize the directory structure and write config."""
        for d in [
            self.root, self.brain_dir, self.ingested_dir, self.digest_dir,
            self.openqa_dir, self.specs_dir, self.specs_dir / "_global",
            self.changes_dir, self.archive_dir,
            self.tests_dir, self.tests_dir / "flows", self.tests_dir / "specs",
            self.reports_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self.write_config(config)

        # Initialize a few placeholder files
        if not self.insights_path.exists():
            self.insights_path.write_text(
                "# Project Insights\n\n"
                "_Agent's observations about this project. Updated automatically as work progresses._\n\n"
                "## No observations yet\n\n"
                "Run `python -m evo_qa.core.cli plan <project> \"<intent>\"` "
                "and `python -m evo_qa.core.cli run <project> <change-id>` "
                "to start building insights.\n"
            )
        if not self.pages_path.exists():
            self.pages_path.write_text("# Pages Map\n\n_Discovered pages and their key elements._\n\n")
        if not self.selectors_path.exists():
            import json
            self.selectors_path.write_text(json.dumps({"selectors": {}}, indent=2))

        # README gives a project overview
        readme = self.root / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# QA Workspace: {self.project}\n\n"
                f"- **URL**: {config.url}\n"
                f"- **Industry**: {config.industry or '_unspecified_'}\n"
                f"- **Language**: {config.language}\n\n"
                "Managed by `evo_qa` skill. "
                "Run `python -m evo_qa.core.cli status <project>` "
                "for current state.\n"
            )

    def write_config(self, config: WorkspaceConfig) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w") as f:
            yaml.safe_dump(asdict(config), f, sort_keys=False, allow_unicode=True)

    def read_config(self) -> WorkspaceConfig:
        with self.config_path.open() as f:
            data = yaml.safe_load(f) or {}
        return WorkspaceConfig(**data)

    def list_changes(self) -> list[str]:
        if not self.changes_dir.exists():
            return []
        return sorted(p.name for p in self.changes_dir.iterdir() if p.is_dir())

    def get_change_dir(self, change_id: str) -> Path:
        return self.changes_dir / change_id

    def __repr__(self) -> str:
        return f"Workspace({self.project} @ {self.root})"


def find_workspace(name_or_path: str) -> Workspace:
    """Accepts a project name (e.g. 'saucedemo') or a full path."""
    p = Path(name_or_path)
    if p.is_absolute() and p.exists():
        return Workspace(p.name, root=p.parent)
    return Workspace(name_or_path)


__all__ = ["Workspace", "find_workspace", "DEFAULT_ROOT"]
