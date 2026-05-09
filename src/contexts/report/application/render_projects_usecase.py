"""项目库渲染用例 — 生成 projects.html"""
from __future__ import annotations
import datetime
import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from src.shared.config import OUTPUT_DIR, TMPL_DIR
from src.shared.db import get_conn
from src.contexts.scoring.application.score_usecase import DOMAIN_META


def render_projects() -> Path:
    conn = get_conn()
    rows = conn.execute(
        """SELECT ar_id, repo, first_seen, domain_ids, stars, delta_stars,
                  description, language, homepage, gh_created
           FROM project_registry
           ORDER BY id"""
    ).fetchall()
    conn.close()

    projects = []
    for r in rows:
        try:
            domain_ids = json.loads(r["domain_ids"] or "[]")
        except Exception:
            domain_ids = []
        domain_names = [DOMAIN_META.get(d, {}).get("name", d) for d in domain_ids]
        delta = r["delta_stars"] or 0
        projects.append({
            "ar_id":        r["ar_id"],
            "repo":         r["repo"],
            "repo_url":     f"https://github.com/{r['repo']}",
            "first_seen":   r["first_seen"] or "",
            "domain_ids":   domain_ids,
            "domain_names": domain_names,
            "stars":        r["stars"] or 0,
            "delta_stars":  delta,
            "delta_sign":   "+" if delta > 0 else ("" if delta == 0 else "−"),
            "delta_abs":    abs(delta),
            "description":  r["description"] or "",
            "language":     r["language"] or "",
            "homepage":     r["homepage"] or "",
            "gh_created":   (r["gh_created"] or "")[:7],
        })

    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=True)
    tmpl = env.get_template("projects.html.j2")
    html = tmpl.render(
        projects=projects,
        total=len(projects),
        generated_at=datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        domain_meta=DOMAIN_META,
    )

    out_path = OUTPUT_DIR / "projects.html"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
