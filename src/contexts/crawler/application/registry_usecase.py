"""项目注册表用例 — 增量编号 + 存量星数更新

增量逻辑：
  本周在 domain_top_repos / general_top_repos 中出现的 repo，
  若不在 project_registry，则分配下一个 AR-XXX 编号并写入。

存量逻辑：
  对 project_registry 中所有 repo，更新 stars / description / domain_ids
  为当周最新值，并计算 delta_stars（vs 上次 stars）。
"""
from __future__ import annotations
import json
import time
import requests
from src.shared.db import get_conn
from src.shared.config import GITHUB_HEADERS


def _next_ar_id(conn) -> str:
    row = conn.execute("SELECT MAX(id) FROM project_registry").fetchone()
    next_num = (row[0] or 0) + 1
    return f"AR-{next_num:04d}"


def _fetch_gh_meta(repo: str) -> dict:
    """从 GitHub API 拉取仓库元数据，失败时返回空 dict。"""
    url = f"https://api.github.com/repos/{repo}"
    try:
        r = requests.get(url, headers=GITHUB_HEADERS, timeout=10)
        if r.status_code == 200:
            d = r.json()
            return {
                "stars":       d.get("stargazers_count", 0),
                "description": (d.get("description") or "")[:300],
                "language":    d.get("language") or "",
                "homepage":    d.get("homepage") or "",
                "gh_created":  (d.get("created_at") or "")[:10],
            }
    except Exception:
        pass
    return {}


def _collect_this_week_repos(conn, week: str) -> dict[str, dict]:
    """收集本周所有出现的 repo → {repo: {stars, description, domain_ids}}"""
    repos: dict[str, dict] = {}

    # domain_top_repos
    rows = conn.execute(
        "SELECT repo, stars, description, domain_id FROM domain_top_repos WHERE week=?", (week,)
    ).fetchall()
    for r in rows:
        repo = r["repo"]
        if repo not in repos:
            repos[repo] = {"stars": r["stars"] or 0, "description": r["description"] or "", "domain_ids": set()}
        repos[repo]["domain_ids"].add(r["domain_id"])
        if r["stars"] and r["stars"] > repos[repo]["stars"]:
            repos[repo]["stars"] = r["stars"]

    # general_top_repos
    rows2 = conn.execute(
        "SELECT repo, stars, description, language FROM general_top_repos WHERE week=?", (week,)
    ).fetchall()
    for r in rows2:
        repo = r["repo"]
        if repo not in repos:
            repos[repo] = {"stars": r["stars"] or 0, "description": r["description"] or "", "domain_ids": set()}
        if r["stars"] and r["stars"] > repos[repo]["stars"]:
            repos[repo]["stars"] = r["stars"]

    return repos


def run_incremental(week: str, verbose: bool = True) -> int:
    """增量注册：本周新出现的 repo 分配 AR-XXX，返回新增数量。"""
    conn = get_conn()
    this_week = _collect_this_week_repos(conn, week)
    new_count = 0

    for repo, meta in this_week.items():
        exists = conn.execute(
            "SELECT ar_id FROM project_registry WHERE repo=?", (repo,)
        ).fetchone()
        if exists:
            continue
        ar_id = _next_ar_id(conn)
        domain_ids_json = json.dumps(sorted(meta["domain_ids"]), ensure_ascii=False)
        conn.execute(
            """INSERT INTO project_registry
               (ar_id, repo, first_seen, domain_ids, stars, description, updated_at)
               VALUES (?,?,?,?,?,?, datetime('now'))""",
            (ar_id, repo, week, domain_ids_json, meta["stars"], meta["description"]),
        )
        conn.commit()
        new_count += 1
        if verbose:
            print(f"  [registry] +{ar_id}  {repo}")

    conn.close()
    return new_count


def run_full_update(verbose: bool = True) -> int:
    """存量更新：为注册表里所有 repo 重新拉 GitHub 数据并更新 stars / delta。"""
    conn = get_conn()
    rows = conn.execute("SELECT ar_id, repo, stars FROM project_registry ORDER BY id").fetchall()
    updated = 0

    for row in rows:
        ar_id, repo, old_stars = row["ar_id"], row["repo"], row["stars"] or 0
        meta = _fetch_gh_meta(repo)
        if not meta:
            time.sleep(0.5)
            continue

        new_stars = meta["stars"]
        delta = new_stars - old_stars
        conn.execute(
            """UPDATE project_registry
               SET stars=?, delta_stars=?, description=?, language=?, homepage=?,
                   gh_created=?, updated_at=datetime('now')
               WHERE ar_id=?""",
            (new_stars, delta, meta["description"], meta["language"],
             meta["homepage"], meta["gh_created"], ar_id),
        )
        conn.commit()
        updated += 1
        if verbose:
            sign = "+" if delta >= 0 else ""
            print(f"  [registry] {ar_id} {repo}  ⭐{new_stars} ({sign}{delta})")
        time.sleep(0.3)  # 避免触发 GitHub rate limit

    conn.close()
    return updated
