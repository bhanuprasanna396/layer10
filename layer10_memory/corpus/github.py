from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dateutil.parser import isoparse

from layer10_memory.schemas import Artifact
from layer10_memory.utils import stable_id


def load_github_corpus(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def github_to_artifacts(payload: dict[str, Any]) -> list[Artifact]:
    repository = payload["repository"]
    corpus_id = payload.get("corpus_id", f"github:{repository}")
    artifacts: list[Artifact] = []

    for issue in payload.get("issues", []):
        issue_number = issue["number"]
        issue_text = issue.get("body") or ""
        issue_type = "pull_request" if issue.get("is_pull_request", False) else "issue"

        issue_artifact_id = stable_id(
            "art",
            repository,
            str(issue_number),
            "issue",
            str(issue.get("updated_at", "")),
        )

        artifacts.append(
            Artifact(
                artifact_id=issue_artifact_id,
                corpus=corpus_id,
                artifact_type=issue_type,
                source_url=issue["html_url"],
                created_at=isoparse(issue["created_at"]),
                updated_at=isoparse(issue["updated_at"]),
                author=(issue.get("user") or {}).get("login"),
                title=issue.get("title"),
                text=issue_text,
                metadata={
                    "repository": repository,
                    "issue_number": issue_number,
                    "state": issue.get("state"),
                    "labels": [lbl["name"] for lbl in issue.get("labels", [])],
                    "assignees": [a["login"] for a in issue.get("assignees", [])],
                    "raw_issue_id": issue.get("id"),
                },
            )
        )

        for comment in issue.get("comments_data", []):
            comment_text = comment.get("body") or ""
            comment_artifact_id = stable_id(
                "art",
                repository,
                str(issue_number),
                "comment",
                str(comment.get("id")),
                str(comment.get("updated_at", comment.get("created_at", ""))),
            )
            artifacts.append(
                Artifact(
                    artifact_id=comment_artifact_id,
                    corpus=corpus_id,
                    artifact_type="issue_comment",
                    source_url=comment["html_url"],
                    created_at=isoparse(comment["created_at"]),
                    updated_at=isoparse(comment.get("updated_at", comment["created_at"])),
                    author=(comment.get("user") or {}).get("login"),
                    title=f"Comment on #{issue_number}",
                    text=comment_text,
                    metadata={
                        "repository": repository,
                        "issue_number": issue_number,
                        "parent_issue_artifact_id": issue_artifact_id,
                        "parent_issue_state": issue.get("state"),
                        "raw_comment_id": comment.get("id"),
                    },
                )
            )

    return artifacts
