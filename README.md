# agent-radar

> AI/Agent 开源需求周报系统 —— 每周自动爬取 GitHub + PyPI + 本地群聊，更新 12 个应用领域的供需分析，输出含 diff 的 HTML 周报。

## 北极星指标

> **周报准时发布率**：每周一 09:00 前生成新版 HTML，含上周 vs 本周的数据对比。  
> 当前基线：0（尚未自动化）| Q2 2026 目标：100% | 测量频率：weekly

## 技术栈

- 爬虫/分析：Python 3.11
- 调度：macOS launchd（`plist`）
- 存储：SQLite（时序数据 + snapshot）
- 输出：静态 HTML（Jinja2 模板）
- LLM：`yoli_llm`（生成 diff 摘要文案）

## 快速开始

```bash
cd openall/agent-radar
pip install -r requirements.txt

# 手动跑一次完整流程
python src/main.py --run-now

# 查看生成的周报
open output/report_latest.html
```

## 项目状态

- [x] 项目初始化
- [ ] 数据爬虫（GitHub + PyPI）
- [ ] 数据库 schema + 时序存储
- [ ] 评分引擎（统一4维公式）
- [ ] HTML 报告生成器（含 diff section）
- [ ] launchd 调度配置
- [ ] 首次完整运行

## 相关链接

- 原型报告：`../projects/github-community-finder/agent_insight_2026.html`
- 源数据：`../projects/github-community-finder/report_full.html.cache/`
