"""
Ingest FastAPI's GitHub issues into data/raw/issues/.

Each issue is saved as its own JSON file: data/raw/issues/{issue_number}.json,
containing the issue itself plus all its comments.

GitHub's API treats pull requests as a kind of issue, so this filters those out
as I only want real Q&A/bug-report issues for this corpus.

To run:
    python src/ingest_issues.py --max-issues 500 (default set to 100)
"""

import argparse
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()  # reads GITHUB_TOKEN from a local .env file, if present

REPO = "tiangolo/fastapi"
API_URL = f"https://api.github.com/repos/{REPO}/issues"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "issues"


def get_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print(
            "WARNING: no GITHUB_TOKEN found in .env — you're limited to 60 "
            "requests/hour. Set one up for a real pull (see .env.example)."
        )
    return headers


def check_rate_limit(resp: requests.Response):
    """Raise a clear, actionable error if we've hit GitHub's rate limit,
    instead of letting a generic 403 traceback confuse things."""
    if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        reset_ts = int(resp.headers.get("x-ratelimit-reset", 0))
        wait_minutes = max(0, (reset_ts - time.time()) / 60)
        raise RuntimeError(
            f"Hit GitHub's rate limit (limit={resp.headers.get('x-ratelimit-limit')}). "
            f"Resets in ~{wait_minutes:.0f} min. "
            "Fix: add a GITHUB_TOKEN to .env (see .env.example) to raise your "
            "limit from 60/hour to 5,000/hour."
        )


def fetch_issue_list(headers: dict, max_issues: int) -> list[dict]:
    """Page through the issues list endpoint until we have max_issues or run out."""
    issues = []
    page = 1
    per_page = 100

    with tqdm(total=max_issues, desc="Fetching issue list") as pbar:
        while len(issues) < max_issues:
            resp = requests.get(
                API_URL,
                headers=headers,
                params={
                    "state": "all",       # open AND closed — closed issues often
                                            # have the actual resolution
                    "per_page": per_page,
                    "page": page,
                },
                timeout=30,
            )
            check_rate_limit(resp)
            resp.raise_for_status()
            batch = resp.json()

            if not batch:
                break  # no more pages

            # Pull requests show up in this endpoint too; skip them.
            real_issues = [i for i in batch if "pull_request" not in i]
            issues.extend(real_issues)
            pbar.update(len(real_issues))

            page += 1

    return issues[:max_issues]


def fetch_comments(issue: dict, headers: dict) -> list[dict]:
    """Fetch all comments for a single issue."""
    comments_url = issue["comments_url"]
    resp = requests.get(comments_url, headers=headers, timeout=30)
    check_rate_limit(resp)
    resp.raise_for_status()
    return resp.json()


def save_issue(issue: dict, comments: list[dict]):
    record = {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue["body"] or "",
        "state": issue["state"],
        "labels": [label["name"] for label in issue["labels"]],
        "url": issue["html_url"],
        "created_at": issue["created_at"],
        "comments": [
            {"author": c["user"]["login"], "body": c["body"] or ""}
            for c in comments
        ],
    }
    out_path = OUTPUT_DIR / f"{issue['number']}.json"
    out_path.write_text(json.dumps(record, indent=2))


def main(max_issues: int):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    headers = get_headers()

    issues = fetch_issue_list(headers, max_issues)

    for issue in tqdm(issues, desc="Fetching comments + saving"):
        comments = fetch_comments(issue, headers)
        save_issue(issue, comments)
        time.sleep(0.1)  # be polite to the API, avoid hammering rate limits

    print(f"Done. Saved {len(issues)} issues to {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-issues", type=int, default=100,
        help="How many issues to pull (default 100, keep small while testing)",
    )
    args = parser.parse_args()
    main(args.max_issues)