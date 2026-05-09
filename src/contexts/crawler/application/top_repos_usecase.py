"""
Top Repos 用例：
  1. 读 repos.json → 每领域 历史 Top5 + 近一年 Top5 → domain_top_repos
  2. 读 repos.json → 全局 近一年 Top10 → general_top_repos（recent_year）
  3. 读 project_stars delta → 全局 近一周 Top10 → general_top_repos（this_week）
  4. 为 general top 项目抓取 GitHub activity（issues/PRs/commits）
"""
from __future__ import annotations
import json
import datetime
from pathlib import Path

from src.shared.db import get_conn
from src.shared.config import DOMAIN_REPO_KWS

REPOS_JSON = Path("/Users/yoligehude/Desktop/all/openall/projects"
                  "/github-community-finder/report_full.html.cache/repos.json")

_ONE_YEAR_AGO = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()


# ── 工具函数 ──────────────────────────────────────────────────────────

def _score(repo: dict, kws: list[str]) -> int:
    """给单个 repo 打领域相关性分（topics 权重高，description/name 次之）"""
    text_topics = " ".join(repo.get("topics") or []).lower()
    text_desc   = (repo.get("description") or "").lower()
    text_name   = repo.get("name", "").lower()
    score = 0
    for kw in kws:
        kw = kw.lower()
        if kw in text_topics:
            score += 3
        elif kw in text_desc:
            score += 2
        elif kw in text_name:
            score += 1
    return score


def _load_repos() -> list[dict]:
    if not REPOS_JSON.exists():
        return []
    with open(REPOS_JSON, encoding="utf-8") as f:
        return json.load(f)


def _is_recent(repo: dict) -> bool:
    created = (repo.get("created_at") or "")[:10]
    return created >= _ONE_YEAR_AGO


# ── 主流程 ────────────────────────────────────────────────────────────

def run(week: str, verbose: bool = True) -> None:
    repos = _load_repos()
    if not repos:
        print("  ⚠ repos.json 不存在，跳过 top repos 分析")
        return

    # 过滤：去除 fork、archived、awesome-list、纯文档/教程 repo
    _EXCLUDE_NAME = ("awesome", "roadmap", "interview", "tutorial", "learning",
                     "cheatsheet", "resource", "note", "cookbook", "prompt",
                     "skill", "example", "demo", "template", "boilerplate")
    def _is_real_project(r: dict) -> bool:
        name = r.get("name", "").lower()
        desc = (r.get("description") or "").lower()
        if r.get("fork") or r.get("archived"):
            return False
        if r.get("stargazers_count", 0) < 50:
            return False
        if any(kw in name for kw in _EXCLUDE_NAME):
            return False
        # 必须有实质开发活动：有 forks 或 open_issues
        if r.get("forks_count", 0) < 5 and r.get("open_issues_count", 0) < 3:
            return False
        return True

    repos = [r for r in repos if _is_real_project(r)]

    if verbose:
        print(f"  有效 repo 数: {len(repos):,}")

    conn = get_conn()

    # ── 1. 每领域 Top5 ──────────────────────────────────────────────
    for domain_id, kws in DOMAIN_REPO_KWS.items():
        scored = [(r, _score(r, kws)) for r in repos]
        scored = [(r, s) for r, s in scored if s > 0]

        # 历史 Top5（全时间，按 stars）
        hist = sorted(scored, key=lambda x: x[0]["stargazers_count"], reverse=True)[:5]
        for rank, (r, _) in enumerate(hist, 1):
            conn.execute("""
                INSERT INTO domain_top_repos (week,domain_id,category,rank,repo,stars,created_at,description)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(week,domain_id,category,repo) DO UPDATE SET
                    rank=excluded.rank, stars=excluded.stars
            """, (week, domain_id, "historical", rank,
                  r["full_name"], r["stargazers_count"],
                  (r.get("created_at") or "")[:10],
                  (r.get("description") or "")[:120]))

        # 近一年 Top5（created_at 过滤后，按 stars）
        recent = [(r, s) for r, s in scored if _is_recent(r)]
        recent = sorted(recent, key=lambda x: x[0]["stargazers_count"], reverse=True)[:5]
        for rank, (r, _) in enumerate(recent, 1):
            conn.execute("""
                INSERT INTO domain_top_repos (week,domain_id,category,rank,repo,stars,created_at,description)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(week,domain_id,category,repo) DO UPDATE SET
                    rank=excluded.rank, stars=excluded.stars
            """, (week, domain_id, "recent_year", rank,
                  r["full_name"], r["stargazers_count"],
                  (r.get("created_at") or "")[:10],
                  (r.get("description") or "")[:120]))

        if verbose:
            h_names = [r["full_name"] for r, _ in hist]
            print(f"  {domain_id:<12} hist={h_names[:2]}  recent={[r['full_name'] for r,_ in recent[:2]]}")

    conn.commit()

    # ── 2. 全局近一年 Top10：必须有 open issues，证明是真实开发项目 ──
    recent_all = sorted(
        [r for r in repos if _is_recent(r) and r.get("open_issues_count", 0) >= 5],
        key=lambda x: x["stargazers_count"],
        reverse=True,
    )[:10]

    for rank, r in enumerate(recent_all, 1):
        conn.execute("""
            INSERT INTO general_top_repos
                (week,category,rank,repo,stars,delta_stars,description,language,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(week,category,repo) DO UPDATE SET
                rank=excluded.rank, stars=excluded.stars
        """, (week, "recent_year", rank,
              r["full_name"], r["stargazers_count"], 0,
              (r.get("description") or "")[:120],
              r.get("language") or "",
              (r.get("created_at") or "")[:10]))

    if verbose:
        print(f"  近一年 top10: {[r['full_name'] for r in recent_all[:3]]}")

    conn.commit()

    # ── 3. 全局近一周 Top10（project_stars delta）──────────────────
    rows = conn.execute("""
        SELECT repo, stars, delta FROM project_stars
        WHERE week=? AND delta > 0
        ORDER BY delta DESC LIMIT 10
    """, (week,)).fetchall()

    for rank, row in enumerate(rows, 1):
        # 从 repos 列表里找到该 repo 的 meta（若有）
        meta = next((r for r in repos if r["full_name"] == row["repo"]), None)
        conn.execute("""
            INSERT INTO general_top_repos
                (week,category,rank,repo,stars,delta_stars,description,language,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(week,category,repo) DO UPDATE SET
                rank=excluded.rank, delta_stars=excluded.delta_stars, stars=excluded.stars
        """, (week, "this_week", rank, row["repo"], row["stars"], row["delta"],
              (meta.get("description") or "")[:120] if meta else "",
              meta.get("language") or "" if meta else "",
              (meta.get("created_at") or "")[:10] if meta else ""))

    if verbose:
        print(f"  近一周 top{len(rows)}: {[r['repo'] for r in rows[:3]]}")

    conn.commit()
    conn.close()


def fetch_general_activity(week: str, verbose: bool = True) -> None:
    """
    为 general_top_repos 里的项目：
      1. 抓取本周 issues/PRs/commits 标题
      2. 用 LLM 生成四维分析（进展/痛点/重心/判断）
    """
    from src.contexts.crawler.infrastructure.github_activity import get_weekly_activity, get_repo_meta
    from src.contexts.diff.application.activity_analysis import analyze_repo_activity
    import json, time

    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT repo FROM general_top_repos WHERE week=?", (week,)
    ).fetchall()

    for row in rows:
        repo = row["repo"]
        if verbose:
            print(f"  activity + analysis: {repo}")

        # meta
        meta = get_repo_meta(repo)
        if meta:
            conn.execute("""
                UPDATE general_top_repos
                SET stars=?, description=?, language=?, created_at=?
                WHERE week=? AND repo=?
            """, (meta["stars"], meta["description"], meta["language"],
                  meta["created_at"], week, repo))

        # 活动抓取（含标题）
        act = get_weekly_activity(repo)

        # LLM 分析
        analysis = analyze_repo_activity(
            repo,
            act["issue_titles"],
            act["pr_titles"],
            act["commit_msgs"],
        )
        if verbose and analysis.get("verdict"):
            print(f"    → {analysis['verdict']}")

        conn.execute("""
            UPDATE general_top_repos
            SET new_issues=?, new_prs=?, new_commits=?,
                issue_titles=?, pr_titles=?, commit_msgs=?,
                analysis_progress=?, analysis_pain=?,
                analysis_focus=?, analysis_verdict=?
            WHERE week=? AND repo=?
        """, (
            act["new_issues"], act["new_prs"], act["new_commits"],
            json.dumps(act["issue_titles"],  ensure_ascii=False),
            json.dumps(act["pr_titles"],     ensure_ascii=False),
            json.dumps(act["commit_msgs"],   ensure_ascii=False),
            analysis["progress"], analysis["user_pain"],
            analysis["dev_focus"], analysis["verdict"],
            week, repo,
        ))

        time.sleep(1.5)

    conn.commit()
    conn.close()
