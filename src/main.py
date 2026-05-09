"""
agent-radar 主入口
用法：
  python src/main.py              # 当前周
  python src/main.py --week 2026-W20
  python src/main.py --skip-crawl # 跳过爬虫，直接用库中最新数据重新评分渲染
"""
import argparse
import datetime
import sys
import traceback
from pathlib import Path

# 确保 src/ 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.shared.db import init_db, get_conn
from src.contexts.crawler.application.crawl_usecase import run as crawl, iso_week
from src.contexts.crawler.application.top_repos_usecase import run as crawl_top_repos, fetch_general_activity
from src.contexts.crawler.infrastructure.wechat_reader import count_messages_this_week
from src.contexts.scoring.application.score_usecase import compute_scores
from src.contexts.diff.application.diff_usecase import compute_diff
from src.contexts.report.application.render_usecase import render
from src.shared.config import LOG_DIR, REPORT_PATH


def _log_run(week: str, status: str, notes: str = "") -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE run_log SET finished_at=datetime('now'), status=?, notes=? WHERE week=? AND finished_at IS NULL",
        (status, notes, week)
    )
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="agent-radar weekly report generator")
    parser.add_argument("--week", default=None, help="目标周，格式 2026-W19")
    parser.add_argument("--skip-crawl", action="store_true", help="跳过爬虫，用已有数据重渲染")
    args = parser.parse_args()

    week = args.week or iso_week()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"  agent-radar  周期：{week}")
    print(f"{'='*50}\n")

    # 初始化数据库
    init_db()

    # 记录本次运行
    conn = get_conn()
    conn.execute(
        "INSERT INTO run_log (week, started_at, status) VALUES (?,datetime('now'),'running')",
        (week,)
    )
    conn.commit()
    conn.close()

    try:
        # Step 1: 爬取
        wechat_counts = {}
        if not args.skip_crawl:
            print("▶ Step 1/4  爬取数据 ...")
            crawl_log = crawl(week=week, verbose=True)
            wechat_counts = crawl_log.get("wechat", {})
        else:
            print("▶ Step 1/4  跳过爬取（--skip-crawl）")
            from src.contexts.crawler.infrastructure.wechat_reader import count_messages_this_week
            wechat_counts = count_messages_this_week("2000-01-01")

        # Step 1b: Top repos 分析（从 repos.json）
        print("\n▶ Step 1b/4  分析 Top Repos ...")
        crawl_top_repos(week=week, verbose=True)
        print("  抓取 General Top 项目活动 ...")
        fetch_general_activity(week=week, verbose=True)

        # Step 2: 评分
        print("\n▶ Step 2/4  计算评分 ...")
        scores = compute_scores(week, wechat_counts)
        for s in scores:
            track_badge = f"[Track-{s.d1_track}]"
            print(f"  {s.domain_id:<12}  supply={s.supply:>3}  demand={s.demand:>3}  {track_badge}")

        # Step 3: Diff
        print("\n▶ Step 3/4  生成 Diff ...")
        diff = compute_diff(week)
        if diff:
            print(f"  对比上周 {diff.prev_week}")
            for d in diff.domains:
                if abs(d.demand_delta) > 0 or abs(d.supply_delta) > 0:
                    print(f"  {d.domain_id:<12}  demand {d.demand_delta:+d}  supply {d.supply_delta:+d}")
        else:
            print("  首次运行，无历史对比")

        # Step 4: 渲染报告
        print("\n▶ Step 4/4  渲染 HTML ...")
        out = render(week, scores, diff)
        print(f"\n✅ 报告已生成：{out}")

        _log_run(week, "ok")

        # 打开报告
        import subprocess
        subprocess.Popen(["open", str(out)])

    except Exception as e:
        tb = traceback.format_exc()
        print(f"\n❌ 出错：{e}\n{tb}")
        _log_run(week, "error", str(e)[:500])
        sys.exit(1)


if __name__ == "__main__":
    main()
