"""
agent-radar 日更轻量入口

设计哲学：
  - 周更 (main.py)  跑全量 42k 项目 + 12 领域评分 + 群聊爬取 + HTML 渲染（耗时 2-4h）
  - 日更 (本入口)   只跑 Top 500 + general trending refresh（耗时 < 10min，单 token 内）

每日产出：
  - daily_snapshots 表写入今日快照（含 delta_stars_24h）
  - daily_run_log   写入运行记录
  - 检测 P0 即时事件（单项目 ≥500★/24h，或新爆款 ≥5000★）→ POST zero :7070/notify
  - 不渲染 HTML（HTML 留给周更）

用法：
  python src/main_daily.py             # 默认 Top 500
  python src/main_daily.py --top 200   # 限制爬取数量
  python src/main_daily.py --dry-run   # 只打印不写库不推送
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src.shared.config import GITHUB_HEADERS, LOG_DIR
from src.shared.db import init_db, get_conn
from src.contexts.crawler.infrastructure.github_client import get_repo_stars


# ── 配置 ────────────────────────────────────────────────────────────────────

ZERO_NOTIFY_URL = os.environ.get("ZERO_NOTIFY_URL", "http://localhost:7070/notify")

# P0 即时推送阈值
P0_DAY_DELTA_THRESHOLD = int(os.environ.get("AR_P0_DAY_DELTA", 500))
P0_NEW_HOT_STARS = int(os.environ.get("AR_P0_NEW_HOT", 5000))

# 每次跑爬多少个项目（按 stars 降序 + Top 500 默认）
DEFAULT_TOP_N = int(os.environ.get("AR_DAILY_TOP_N", 500))

# 主动限速：每 N 个 API 调用 sleep 1s（保险）
SLEEP_EVERY = 50


# ── 选目标项目 ──────────────────────────────────────────────────────────────

def _select_targets(conn, top_n: int) -> List[dict]:
    """从 project_registry 中按 stars 降序选 Top N，作为日更扫描目标"""
    rows = conn.execute(
        """SELECT ar_id, repo, stars, language, description
           FROM project_registry
           ORDER BY stars DESC
           LIMIT ?""",
        (top_n,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── 抓取单 repo ──────────────────────────────────────────────────────────────

def _fetch_repo_today(repo: str) -> dict:
    """
    获取单 repo 今日数据。返回 dict：
      {stars, language, description, issues_24h, prs_24h, success}
    如果失败 success=False，其他字段尽量保留。
    """
    out = {
        "stars": None, "language": "", "description": "",
        "issues_24h": 0, "prs_24h": 0, "success": False,
    }
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}",
                         headers=GITHUB_HEADERS, timeout=10)
        if r.status_code != 200:
            return out
        data = r.json()
        out["stars"] = data.get("stargazers_count")
        out["language"] = data.get("language") or ""
        out["description"] = (data.get("description") or "")[:200]
        out["success"] = True
        # 注意：repos endpoint 已包含 open_issues_count（含 PR）；
        # 单独抓 issue/PR 24h 太贵（每 repo 2 次 API），跳过；
        # 周更全量爬时已经有 new_issues/new_prs。
    except Exception:
        pass
    return out


# ── 取昨日基线 ──────────────────────────────────────────────────────────────

def _prev_stars(conn, repo: str, today: str) -> Optional[int]:
    """
    取该 repo 的"昨日 daily_snapshots.stars"。
    如果没有日快照（首次跑），fallback 到 project_registry.stars。
    """
    row = conn.execute(
        """SELECT stars FROM daily_snapshots
           WHERE repo = ? AND date < ?
           ORDER BY date DESC LIMIT 1""",
        (repo, today),
    ).fetchone()
    if row and row["stars"] is not None:
        return row["stars"]
    reg = conn.execute(
        "SELECT stars FROM project_registry WHERE repo = ?", (repo,)
    ).fetchone()
    return reg["stars"] if reg else None


def _week_baseline_stars(conn, repo: str) -> Optional[int]:
    """周一全量基线（project_registry 的 stars 是周一更新的）"""
    row = conn.execute(
        "SELECT stars FROM project_registry WHERE repo = ?", (repo,)
    ).fetchone()
    return row["stars"] if row else None


# ── P0 即时推送 ──────────────────────────────────────────────────────────────

def _push_p0(title: str, body: str, level: str = "warn") -> bool:
    """单条 P0 立即推送到 zero notify bus"""
    try:
        payload = {
            "event_type": "notification",
            "title": title,
            "body": body,
            "channels": ["wechat", "desktop"],
            "priority": "high" if level == "warn" else "urgent",
            "level": level,
        }
        r = requests.post(ZERO_NOTIFY_URL, json=payload, timeout=8)
        return 200 <= r.status_code < 300
    except Exception as exc:
        print(f"  [P0 推送失败] {exc!r}")
        return False


def _evaluate_p0(snap: dict, prev_stars: Optional[int]) -> Optional[dict]:
    """
    决定是否触发 P0 即时推送。返回 None 表示不推；返回 dict 表示要推。
    P0 触发条件：
      1) 单项目日增 stars >= P0_DAY_DELTA_THRESHOLD
      2) 项目当前 stars >= P0_NEW_HOT_STARS 且 prev 为 None（首次见，可能是新爆款）
    """
    cur = snap.get("stars") or 0
    delta = (cur - (prev_stars or 0)) if prev_stars is not None else 0

    if delta >= P0_DAY_DELTA_THRESHOLD:
        return {
            "kind": "day_surge",
            "title": f"[GitHub 日增] {snap['repo']} +{delta:,}★",
            "body":  (
                f"{snap['repo']}  +{delta:,}★ / 24h\n"
                f"现在 ★{cur:,} (语言: {snap.get('language') or 'N/A'})\n"
                f"{(snap.get('description') or '')[:120]}\n"
                f"https://github.com/{snap['repo']}"
            ),
            "level": "error",   # urgent
        }

    if prev_stars is None and cur >= P0_NEW_HOT_STARS:
        return {
            "kind": "new_hot",
            "title": f"[GitHub 新爆款] {snap['repo']} ★{cur:,}",
            "body":  (
                f"{snap['repo']} 首次进入跟踪表，★{cur:,}\n"
                f"语言: {snap.get('language') or 'N/A'}\n"
                f"{(snap.get('description') or '')[:120]}\n"
                f"https://github.com/{snap['repo']}"
            ),
            "level": "warn",
        }

    return None


# ── 主流程 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="agent-radar daily incremental crawler")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N,
                        help=f"扫描 Top N 项目（默认 {DEFAULT_TOP_N}）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印不写库不推送")
    args = parser.parse_args()

    today = datetime.date.today().isoformat()
    started_at = datetime.datetime.now().isoformat(timespec="seconds")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    conn = get_conn()

    # 写运行日志
    if not args.dry_run:
        conn.execute(
            "INSERT INTO daily_run_log (date, started_at, status) VALUES (?, ?, 'running')",
            (today, started_at),
        )
        conn.commit()
    run_log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    print(f"\n{'='*55}")
    print(f"  agent-radar DAILY  日期：{today}")
    print(f"  Top N: {args.top}   dry-run: {args.dry_run}")
    print(f"{'='*55}\n")

    targets = _select_targets(conn, args.top)
    print(f"▶ 选中 {len(targets)} 个目标项目")
    if not targets:
        print("  [警告] project_registry 是空的；先跑一次周更 python src/main.py")
        return 1

    crawled = 0
    api_calls = 0
    p0_events: List[dict] = []
    surge_rows: List[dict] = []

    for i, t in enumerate(targets):
        repo = t["repo"]
        snap = _fetch_repo_today(repo)
        api_calls += 1
        if snap["success"]:
            crawled += 1

        prev = _prev_stars(conn, repo, today)
        week_base = _week_baseline_stars(conn, repo)
        cur = snap["stars"] or 0
        delta_24h = (cur - (prev or 0)) if prev is not None else 0
        delta_week = (cur - (week_base or 0)) if week_base is not None else 0

        if not args.dry_run and snap["success"]:
            conn.execute(
                """INSERT OR REPLACE INTO daily_snapshots
                   (date, repo, ar_id, stars, delta_stars_24h, delta_stars_week,
                    language, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (today, repo, t["ar_id"], cur, delta_24h, delta_week,
                 snap["language"], snap["description"]),
            )

        if delta_24h > 0:
            surge_rows.append({
                "repo": repo, "stars": cur, "delta_24h": delta_24h,
                "delta_week": delta_week, "language": snap["language"],
                "description": snap["description"],
            })

        # P0 即时推送
        p0 = _evaluate_p0({**snap, "repo": repo}, prev)
        if p0 and not args.dry_run:
            pushed = _push_p0(p0["title"], p0["body"], p0["level"])
            if pushed:
                print(f"  [P0 已推送] {p0['kind']}  {repo}  +{delta_24h:,}★")
                p0_events.append({**p0, "repo": repo, "delta": delta_24h})

        if (i + 1) % SLEEP_EVERY == 0:
            time.sleep(1.0)
            print(f"  ...已处理 {i+1}/{len(targets)}")

    # 计算当日 rank_daily（按 delta_stars_24h 降序）
    if not args.dry_run:
        rows = conn.execute(
            """SELECT id FROM daily_snapshots WHERE date = ?
               ORDER BY delta_stars_24h DESC""",
            (today,),
        ).fetchall()
        for rank, r in enumerate(rows, start=1):
            conn.execute(
                "UPDATE daily_snapshots SET rank_daily = ? WHERE id = ?",
                (rank, r["id"]),
            )
        conn.commit()

    # 控制台 Top 10 报告
    surge_rows.sort(key=lambda x: -x["delta_24h"])
    print(f"\n▶ 今日 Top 10 暴涨：")
    for r in surge_rows[:10]:
        lang = f" ({r['language']})" if r['language'] else ""
        print(f"  +{r['delta_24h']:,}★  {r['repo']}{lang}  (总 ★{r['stars']:,})")

    print(f"\n▶ P0 即时推送数：{len(p0_events)}")

    # 完成 run_log
    if not args.dry_run:
        finished_at = datetime.datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """UPDATE daily_run_log
               SET finished_at = ?, status = 'ok',
                   tracked = ?, crawled = ?, api_calls = ?, notes = ?
               WHERE id = ?""",
            (finished_at, len(targets), crawled, api_calls,
             json.dumps({"p0": len(p0_events), "surge": len(surge_rows)}),
             run_log_id),
        )
        conn.commit()
    conn.close()

    print(f"\n✅ 日更完成（tracked={len(targets)}, crawled={crawled}, api={api_calls}, P0={len(p0_events)}）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[中断]")
        sys.exit(130)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"\n[错误] {e}\n{tb}")
        sys.exit(1)
