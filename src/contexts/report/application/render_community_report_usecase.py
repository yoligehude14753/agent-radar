"""
render_community_report_usecase.py
====================================
直接复用 github_radar.report.render() 生成社区群聊专版报告。

输入：results.jsonl（github-community-finder 生成的原始结果）
输出：output/community.html（含压缩 QR 码、可加入群聊的项目卡片）

不重新发明轮子——github_radar.report 已经实现：
  - _compress_image_b64 压缩 QR 图
  - _extract_joinable_items 过滤有效群聊
  - _repo_to_json 序列化
  - render() 生成完整 HTML（内嵌 JSON + 前端 CSR）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from src.shared.config import OUTPUT_DIR

COMMUNITY_FINDER_DIR = Path(
    "/Users/yoligehude/Desktop/all/openall/projects/github-community-finder"
)
RESULTS_JSONL = COMMUNITY_FINDER_DIR / "report_full.html.cache" / "results.jsonl"
COMMUNITY_HTML = OUTPUT_DIR / "community.html"

# 加入 github-community-finder 的 sys.path 以复用其模块
if str(COMMUNITY_FINDER_DIR) not in sys.path:
    sys.path.insert(0, str(COMMUNITY_FINDER_DIR))


def render_community_report(verbose: bool = True) -> Path:
    """
    从 results.jsonl 读取数据，调用 github_radar.report.render() 生成社区报告。
    返回生成文件路径。
    """
    from github_radar.models import result_from_dict
    from github_radar.report import render

    if verbose:
        print("  [community] 加载 results.jsonl ...")

    results = []
    try:
        with open(RESULTS_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    r = result_from_dict(d)
                    results.append(r)
                except Exception:
                    continue
    except FileNotFoundError:
        if verbose:
            print(f"  [community] ⚠ 找不到 {RESULTS_JSONL}，跳过")
        return COMMUNITY_HTML

    if verbose:
        print(f"  [community] 共 {len(results):,} 条，开始渲染...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    count = render(results, str(COMMUNITY_HTML))

    if verbose:
        size_mb = COMMUNITY_HTML.stat().st_size / 1024 / 1024
        print(f"  [community] 已生成 {COMMUNITY_HTML}（{count:,} 个有群聊项目，{size_mb:.1f} MB）")

    return COMMUNITY_HTML
