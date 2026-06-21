"""Post-turn reviewer — distill lessons from each run.

Given the most recent Run and Change, extract learnings into
insights / pitfalls / patterns. Rule-based today; future versions can
plug in an LLM-driven retrospective via the same interface.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any

from ...core.interfaces import Reviewer
from ...core.schemas import Knowledge, KnowledgeSource, Run, Change


class PostTurnReviewer:
    name = "post-turn"
    timing = "post_turn"

    def review(self, context: dict[str, Any]) -> list[Knowledge]:
        runs: list[Run] = context.get("recent_runs", [])
        changes: list[Change] = context.get("recent_changes", [])

        new_knowledge: list[Knowledge] = []

        for run in runs:
            # Rule 1: a failed test → record as a pitfall
            if run.status == "fail" and run.findings:
                for f in run.findings:
                    new_knowledge.append(Knowledge(
                        id=f"pitfall-{run.id}-{f.id}",
                        type="pitfall",
                        scope="project",
                        title=f"Failure: {f.title}",
                        summary=f.actual or f.title,
                        body=(
                            f"Encountered during run `{run.id}`.\n\n"
                            f"**Expected**: {f.expected}\n"
                            f"**Actual**: {f.actual}\n"
                            f"**Severity**: {f.severity}\n"
                            f"**Category**: {f.category}\n"
                        ),
                        tags=["failure", f.category],
                        source=KnowledgeSource(
                            type="derived",
                            ref=f"run:{run.id}, finding:{f.id}",
                        ),
                        confidence=0.7,
                        created_at=Knowledge.now(),
                        updated_at=Knowledge.now(),
                    ))

            # Rule 2: a passing test → record as a pattern (when the task is meaningful)
            if run.status == "pass":
                for ch in changes:
                    if ch.id == run.change_id and ch.tasks:
                        new_knowledge.append(Knowledge(
                            id=f"pattern-{run.change_id}-validated",
                            type="pattern",
                            scope="project",
                            title=f"Validated flow: {ch.title}",
                            summary=f"Tested and passed: {ch.title}",
                            body=(
                                f"This flow was successfully tested in run `{run.id}`.\n\n"
                                f"**Tasks validated**:\n" +
                                "\n".join(f"- {t.text}" for t in ch.tasks) +
                                f"\n\n**Reusable test**: `{run.test_path}`\n"
                            ),
                            tags=["flow", "validated"],
                            source=KnowledgeSource(
                                type="derived",
                                ref=f"run:{run.id}",
                            ),
                            confidence=0.9,
                            created_at=Knowledge.now(),
                            updated_at=Knowledge.now(),
                        ))

        return new_knowledge


__all__ = ["PostTurnReviewer"]
