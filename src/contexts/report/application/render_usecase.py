"""报告渲染用例 — 把本周数据 + diff 合并，生成 HTML"""
from __future__ import annotations
import datetime
import math
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from src.shared.config import OUTPUT_DIR, TMPL_DIR, REPORT_PATH
from src.contexts.scoring.application.score_usecase import DomainScore, DOMAIN_META
from src.contexts.diff.application.diff_usecase import WeeklyDiff
from src.shared.db import get_conn

def _load_pypi_by_domain() -> list[dict]:
    """
    从 SQLite 读最新 PyPI 数据，按领域分组返回。
    格式：[{domain_id, domain_name, packages: [{pkg, label, downloads, fmt, pct}]}]
    """
    from src.shared.config import DOMAIN_PYPI
    from src.contexts.scoring.application.score_usecase import DOMAIN_META

    conn = get_conn()
    # 拉最新一期所有包的数据
    dl_map: dict[str, int] = {}
    rows = conn.execute("""
        SELECT p1.package, p1.downloads
        FROM pypi_weekly p1
        INNER JOIN (
            SELECT package, MAX(week) AS mw FROM pypi_weekly GROUP BY package
        ) p2 ON p1.package = p2.package AND p1.week = p2.mw
    """).fetchall()
    conn.close()
    for r in rows:
        dl_map[r["package"]] = r["downloads"] or 0

    # 全局最大值（用于 bar 归一化）
    global_max = max(dl_map.values()) if dl_map else 1

    result = []
    for domain_id, entries in DOMAIN_PYPI.items():
        pkgs = []
        for e in entries:
            dl = dl_map.get(e["pkg"], 0)
            pkgs.append({
                "pkg":       e["pkg"],
                "label":     e["label"],
                "downloads": dl,
                "fmt":       _fmt_num(dl) if dl else "—",
                "pct":       round(dl / global_max * 100) if dl else 0,
                "missing":   dl == 0,
            })
        result.append({
            "domain_id":   domain_id,
            "domain_name": DOMAIN_META.get(domain_id, {}).get("name", domain_id),
            "packages":    pkgs,
            "has_data":    any(p["downloads"] > 0 for p in pkgs),
        })
    return result


def _fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def render(week: str, scores: list[DomainScore], diff: WeeklyDiff | None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)))
    tmpl = env.get_template("report.html.j2")

    # 构建模板上下文
    scores_map = {s.domain_id: s for s in scores}
    diff_map = {d.domain_id: d for d in diff.domains} if diff else {}

    domains_ctx = []
    for domain_id, meta in DOMAIN_META.items():
        s = scores_map.get(domain_id)
        d = diff_map.get(domain_id)
        if not s:
            continue
        domains_ctx.append({
            "id":           domain_id,
            "supply":       s.supply,
            "demand":       s.demand,
            "d1":           s.d1, "d1_track": s.d1_track,
            "d2":           s.d2, "d3": s.d3, "d4": s.d4,
            "meta":         meta,
            "demand_delta": d.demand_delta if d else 0,
            "supply_delta": d.supply_delta if d else 0,
            "star_deltas":  d.star_deltas if d else [],
        })

    # PyPI 合并进 domain
    pypi_by_domain = {g["domain_id"]: g for g in _load_pypi_by_domain()}
    for d in domains_ctx:
        group = pypi_by_domain.get(d["id"], {})
        d["pypi"] = [p for p in group.get("packages", []) if not p.get("missing")]

    # Domain top repos
    conn = get_conn()
    for d in domains_ctx:
        for cat in ("historical", "recent_year"):
            rows = conn.execute("""
                SELECT rank, repo, stars, created_at, description
                FROM domain_top_repos
                WHERE week=? AND domain_id=? AND category=?
                ORDER BY rank
            """, (week, d["id"], cat)).fetchall()
            d[f"top_{cat}"] = [dict(r) for r in rows]

    # General top repos
    general = {}
    for cat in ("recent_year", "this_week"):
        rows = conn.execute("""
            SELECT rank, repo, stars, delta_stars, new_issues, new_prs, new_commits,
                   issue_titles, pr_titles, commit_msgs,
                   analysis_progress, analysis_pain, analysis_focus, analysis_verdict,
                   description, language, created_at
            FROM general_top_repos
            WHERE week=? AND category=?
            ORDER BY rank
        """, (week, cat)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            # JSON 字段反序列化
            import json as _json
            for f in ("issue_titles", "pr_titles", "commit_msgs"):
                try:
                    d[f] = _json.loads(d[f] or "[]")
                except Exception:
                    d[f] = []
            result.append(d)
        general[cat] = result
    conn.close()

    ctx = {
        "week":         week,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "domains":      domains_ctx,
        "diff":         diff,
        "has_diff":     diff is not None,
        "general":      general,
    }

    html = tmpl.render(**ctx)

    # 写最新报告
    REPORT_PATH.write_text(html, encoding="utf-8")

    # 同时按 week 归档
    archive = OUTPUT_DIR / f"report_{week}.html"
    shutil.copy(REPORT_PATH, archive)

    return REPORT_PATH
