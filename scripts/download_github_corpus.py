#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

DEFAULT_API = "https://api.github.com"


def _headers(token: str | None) -> dict[str, str]:
    hdrs = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "layer10-takehome-downloader",
    }
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    return hdrs


def _get_json(
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    retries: int = 4,
) -> Any:
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException:
            if attempt >= retries:
                raise
            time.sleep(min(2**attempt, 8))
            continue

        if resp.status_code in {502, 503, 504}:
            if attempt >= retries:
                resp.raise_for_status()
            time.sleep(min(2**attempt, 8))
            continue

        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset_at = resp.headers.get("X-RateLimit-Reset")
            raise RuntimeError(f"GitHub rate limit exceeded. reset={reset_at}")

        resp.raise_for_status()
        return resp.json()

    raise RuntimeError("unexpected download failure")


def fetch_issues(
    owner: str,
    repo: str,
    max_issues: int,
    include_prs: bool,
    include_timeline: bool,
    token: str | None,
    sleep_seconds: float,
) -> list[dict[str, Any]]:
    headers = _headers(token)
    issues: list[dict[str, Any]] = []
    page = 1

    while len(issues) < max_issues:
        data = _get_json(
            f"{DEFAULT_API}/repos/{owner}/{repo}/issues",
            headers=headers,
            params={"state": "all", "per_page": 100, "page": page, "direction": "desc"},
        )
        if not data:
            break

        for raw in data:
            is_pr = "pull_request" in raw
            if is_pr and not include_prs:
                continue

            issue = {
                "id": raw["id"],
                "number": raw["number"],
                "title": raw.get("title"),
                "state": raw.get("state"),
                "created_at": raw.get("created_at"),
                "updated_at": raw.get("updated_at"),
                "closed_at": raw.get("closed_at"),
                "html_url": raw.get("html_url"),
                "body": raw.get("body") or "",
                "user": raw.get("user"),
                "labels": raw.get("labels", []),
                "assignees": raw.get("assignees", []),
                "comments": raw.get("comments", 0),
                "is_pull_request": is_pr,
            }

            comments_data = _get_json(
                f"{DEFAULT_API}/repos/{owner}/{repo}/issues/{raw['number']}/comments",
                headers=headers,
                params={"per_page": 100},
            )
            issue["comments_data"] = comments_data

            if include_timeline:
                tl_headers = headers | {"Accept": "application/vnd.github+json"}
                timeline = _get_json(
                    f"{DEFAULT_API}/repos/{owner}/{repo}/issues/{raw['number']}/timeline",
                    headers=tl_headers,
                    params={"per_page": 100},
                )
                issue["timeline"] = timeline
            else:
                issue["timeline"] = []

            issues.append(issue)
            if len(issues) >= max_issues:
                break

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        page += 1
        if not include_prs and len(data) < 100:
            break

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a reproducible GitHub Issues corpus")
    parser.add_argument("--repo", required=True, help="owner/repo, e.g. pallets/flask")
    parser.add_argument("--max-issues", type=int, default=120)
    parser.add_argument("--include-prs", action="store_true")
    parser.add_argument("--include-timeline", action="store_true")
    parser.add_argument(
        "--out",
        default="data/raw/github_corpus.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional delay between issue fetches to avoid rate limiting",
    )
    args = parser.parse_args()

    if "/" not in args.repo:
        raise SystemExit("--repo must be in owner/repo format")

    owner, repo = args.repo.split("/", maxsplit=1)
    token = os.environ.get("GITHUB_TOKEN")

    issues = fetch_issues(
        owner=owner,
        repo=repo,
        max_issues=args.max_issues,
        include_prs=args.include_prs,
        include_timeline=args.include_timeline,
        token=token,
        sleep_seconds=args.sleep_seconds,
    )

    payload = {
        "corpus_id": f"github:{owner}/{repo}",
        "repository": f"{owner}/{repo}",
        "downloaded_at": datetime.now(tz=UTC).isoformat(),
        "max_issues": args.max_issues,
        "include_prs": args.include_prs,
        "include_timeline": args.include_timeline,
        "source": "GitHub REST API v2022-11-28",
        "issues": issues,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(issues)} issues to {out_path}")


if __name__ == "__main__":
    main()
