"""GitHub Activity — 抓取 repo 近一周 issues / PRs / commits 内容 + 数量"""
from __future__ import annotations
import time
import datetime
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[5] / ".env")

def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    return {"Authorization": f"token {token}"} if token else {}

_BASE = "https://api.github.com"


def _since_iso(days: int = 7) -> str:
    dt = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_repo_meta(repo: str) -> dict | None:
    """获取 stars + description + language + created_at"""
    try:
        r = requests.get(f"{_BASE}/repos/{repo}", headers=_headers(), timeout=10)
        if r.status_code == 200:
            d = r.json()
            return {
                "stars":       d.get("stargazers_count", 0),
                "description": (d.get("description") or "")[:120],
                "language":    d.get("language") or "",
                "created_at":  (d.get("created_at") or "")[:10],
            }
        return None
    except Exception:
        return None


def get_weekly_activity(repo: str) -> dict:
    """
    获取过去 7 天的活动内容：
      issues_titles:  新建 issue 标题列表（最多 30 条）
      pr_titles:      新建 PR 标题列表（最多 30 条）
      commit_msgs:    新 commit message 列表（最多 30 条）
      以及对应的数量统计
    """
    since = _since_iso(7)
    result = {
        "new_issues": 0, "new_prs": 0, "new_commits": 0,
        "issue_titles": [], "pr_titles": [], "commit_msgs": [],
    }

    try:
        # Issues + PRs（GitHub API /issues 同时返回两者）
        r = requests.get(
            f"{_BASE}/repos/{repo}/issues",
            headers=_headers(),
            params={"state": "all", "since": since, "per_page": 100},
            timeout=12,
        )
        if r.status_code == 200:
            items = r.json()
            for item in items:
                title = (item.get("title") or "").strip()
                labels = [lb["name"] for lb in (item.get("labels") or [])]
                label_str = f" [{', '.join(labels)}]" if labels else ""
                if "pull_request" in item:
                    result["pr_titles"].append(title + label_str)
                else:
                    result["issue_titles"].append(title + label_str)
            result["new_issues"] = len(result["issue_titles"])
            result["new_prs"]    = len(result["pr_titles"])
            # 截断到 30 条
            result["issue_titles"] = result["issue_titles"][:30]
            result["pr_titles"]    = result["pr_titles"][:30]

        time.sleep(0.5)

        # Commits
        r2 = requests.get(
            f"{_BASE}/repos/{repo}/commits",
            headers=_headers(),
            params={"since": since, "per_page": 100},
            timeout=12,
        )
        if r2.status_code == 200:
            commits = r2.json()
            result["new_commits"] = len(commits)
            result["commit_msgs"] = [
                (c.get("commit", {}).get("message") or "").split("\n")[0][:120]
                for c in commits[:30]
            ]

    except Exception:
        pass

    return result
