"""Diff 用例 — 对比本周 vs 上周快照，生成结构化变化列表"""
from __future__ import annotations
from dataclasses import dataclass, field
from src.shared.db import get_conn


@dataclass
class DomainDiff:
    domain_id: str
    demand_delta: int       # 正负变化
    supply_delta: int
    new_repos: list[dict] = field(default_factory=list)   # 本周新出现的追踪项目
    star_deltas: list[dict] = field(default_factory=list) # 追踪项目星数变化


@dataclass
class WeeklyDiff:
    week: str
    prev_week: str
    domains: list[DomainDiff]
    top_star_gains: list[dict]   # 全局 star 增量 top5
    pypi_changes: list[dict]     # PyPI 周环比变化


def compute_diff(week: str) -> WeeklyDiff | None:
    conn = get_conn()

    # 找上一周
    prev_row = conn.execute("""
        SELECT DISTINCT week FROM domain_snapshots
        WHERE week < ? ORDER BY week DESC LIMIT 1
    """, (week,)).fetchone()
    if not prev_row:
        conn.close()
        return None
    prev_week = prev_row["week"]

    domain_diffs: list[DomainDiff] = []

    cur_rows = {r["domain_id"]: r for r in conn.execute(
        "SELECT * FROM domain_snapshots WHERE week=?", (week,)
    ).fetchall()}
    prev_rows = {r["domain_id"]: r for r in conn.execute(
        "SELECT * FROM domain_snapshots WHERE week=?", (prev_week,)
    ).fetchall()}

    for domain_id in cur_rows:
        cur = cur_rows[domain_id]
        prev = prev_rows.get(domain_id)

        demand_delta = cur["demand"] - prev["demand"] if prev else 0
        supply_delta = cur["supply"] - prev["supply"] if prev else 0

        # 本周星数变化
        star_rows = conn.execute("""
            SELECT repo, stars, delta FROM project_stars
            WHERE week=? AND domain_id=?
            ORDER BY delta DESC
        """, (week, domain_id)).fetchall()

        star_deltas = [{"repo": r["repo"], "stars": r["stars"], "delta": r["delta"]}
                       for r in star_rows if r["delta"] != 0]

        domain_diffs.append(DomainDiff(
            domain_id=domain_id,
            demand_delta=demand_delta,
            supply_delta=supply_delta,
            star_deltas=star_deltas,
        ))

    # 全局 star 增量 top5
    top5 = conn.execute("""
        SELECT repo, domain_id, stars, delta
        FROM project_stars WHERE week=? AND delta > 0
        ORDER BY delta DESC LIMIT 5
    """, (week,)).fetchall()
    top_star_gains = [dict(r) for r in top5]

    # PyPI 周环比
    pypi_changes = []
    for row in conn.execute("SELECT package, downloads FROM pypi_weekly WHERE week=?", (week,)):
        prev_dl = conn.execute(
            "SELECT downloads FROM pypi_weekly WHERE package=? AND week=? LIMIT 1",
            (row["package"], prev_week)
        ).fetchone()
        if prev_dl and prev_dl["downloads"]:
            pct = round((row["downloads"] - prev_dl["downloads"]) / prev_dl["downloads"] * 100, 1)
            pypi_changes.append({"package": row["package"], "downloads": row["downloads"],
                                  "delta_pct": pct})

    conn.close()
    return WeeklyDiff(
        week=week, prev_week=prev_week,
        domains=domain_diffs,
        top_star_gains=top_star_gains,
        pypi_changes=sorted(pypi_changes, key=lambda x: abs(x["delta_pct"]), reverse=True),
    )
