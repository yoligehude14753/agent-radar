"""爬取用例 — 编排 GitHub + PyPI + WeChat 并存入 SQLite"""
import datetime
from src.shared.db import get_conn
from src.shared.config import TRACKED_REPOS, PYPI_PACKAGES
from ..infrastructure.github_client import get_repo_stars, search_new_repos
from ..infrastructure.pypi_client import get_weekly_downloads
from ..infrastructure.wechat_reader import count_messages_this_week


def iso_week(dt: datetime.date = None) -> str:
    d = dt or datetime.date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def run(week: str = None, verbose: bool = True) -> dict:
    """
    执行一次完整爬取，存储结果，返回本次采集摘要。
    week: '2026-W19'（默认当前周）
    """
    week = week or iso_week()
    since_date = _week_start_date(week).isoformat()

    log = {"week": week, "repos": {}, "pypi": {}, "wechat": {}, "new_repos": {}}

    # 1. 追踪项目 star 数
    conn = get_conn()
    for domain_id, repos in TRACKED_REPOS.items():
        for repo in repos:
            stars = get_repo_stars(repo)
            if stars is None:
                if verbose:
                    print(f"  ⚠ GitHub API failed: {repo}")
                continue
            # 计算 delta（与上周对比）
            prev = conn.execute(
                "SELECT stars FROM project_stars WHERE repo=? ORDER BY week DESC LIMIT 1",
                (repo,)
            ).fetchone()
            delta = stars - prev["stars"] if prev else 0

            conn.execute("""
                INSERT INTO project_stars (week, repo, domain_id, stars, delta)
                VALUES (?,?,?,?,?)
                ON CONFLICT(week, repo) DO UPDATE SET stars=excluded.stars, delta=excluded.delta
            """, (week, repo, domain_id, stars, delta))

            log["repos"][repo] = {"stars": stars, "delta": delta}
            if verbose:
                print(f"  ★ {repo}: {stars:,} ({delta:+,})")

    conn.commit()

    # 2. PyPI 下载量
    for pkg in PYPI_PACKAGES:
        dl = get_weekly_downloads(pkg)
        if dl is not None:
            conn.execute("""
                INSERT INTO pypi_weekly (week, package, downloads) VALUES (?,?,?)
                ON CONFLICT(week, package) DO UPDATE SET downloads=excluded.downloads
            """, (week, pkg, dl))
            log["pypi"][pkg] = dl
            if verbose:
                print(f"  📦 {pkg}: {dl:,}/week")

    conn.commit()

    # 3. 微信群聊统计
    wechat_counts = count_messages_this_week(since_date)
    log["wechat"] = wechat_counts
    if verbose:
        for d, c in wechat_counts.items():
            print(f"  💬 {d}: {c} msgs")

    conn.close()
    return log


def _week_start_date(week_str: str) -> datetime.date:
    """'2026-W19' → 该周的周一"""
    year, w = week_str.split("-W")
    return datetime.date.fromisocalendar(int(year), int(w), 1)
