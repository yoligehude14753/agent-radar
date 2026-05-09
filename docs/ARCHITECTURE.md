# Architecture — agent-radar

## 目录结构

```
agent-radar/
├── src/
│   ├── main.py                  # 入口：编排全流程
│   ├── contexts/
│   │   ├── crawler/             # 数据爬取
│   │   │   ├── domain/          # GithubRepo, PypiPackage, WechatSignal 模型
│   │   │   ├── application/     # CrawlUseCase
│   │   │   └── infrastructure/  # GithubClient, PypiClient, WechatDbReader
│   │   ├── scoring/             # 评分引擎
│   │   │   ├── domain/          # Domain, DemandScore, SupplyScore
│   │   │   ├── application/     # ScoreUseCase
│   │   │   └── infrastructure/  # SnapshotRepository (SQLite)
│   │   ├── diff/                # 差异对比
│   │   │   ├── domain/          # WeeklyDiff, DomainDiff
│   │   │   ├── application/     # DiffUseCase
│   │   │   └── infrastructure/  # LLMSummaryClient (via yoli_llm)
│   │   └── report/              # 报告生成
│   │       ├── domain/          # ReportData
│   │       ├── application/     # RenderUseCase
│   │       └── infrastructure/  # JinjaRenderer
│   └── shared/
│       ├── db.py                # SQLite session (via yoli_db)
│       └── config.py            # 配置（路径、API keys）
├── templates/
│   └── report.html.j2           # Jinja2 报告模板
├── output/
│   └── report_latest.html       # 每次覆盖（也按 week 归档）
├── data/
│   └── agent_radar.db           # SQLite 时序数据库
├── logs/
├── launchd/
│   └── com.yoli.agent-radar.plist  # macOS 调度配置
├── tests/
│   ├── arch/                    # Fitness Functions
│   ├── unit/
│   └── e2e/
├── docs/
│   ├── PRD.md
│   └── ARCHITECTURE.md (本文件)
├── requirements.txt
└── README.md
```

## 数据流

```
GitHub API ──┐
PyPI API ────┤──► CrawlUseCase ──► SQLite (时序) ──► ScoreUseCase
WechatDB ────┘                                           │
                                                         ▼
                                                   DiffUseCase ──► LLM摘要
                                                         │
                                                         ▼
                                                   RenderUseCase ──► HTML
```

## SQLite Schema

```sql
-- 领域评分快照（每周一条/领域）
CREATE TABLE domain_snapshots (
    id        INTEGER PRIMARY KEY,
    week      TEXT NOT NULL,          -- '2026-W19'
    domain_id TEXT NOT NULL,
    supply    INTEGER,
    demand    INTEGER,
    d1        INTEGER, d1_track TEXT,
    d2        INTEGER,
    d3        INTEGER,
    d4        INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 追踪项目的每周 star 数
CREATE TABLE project_stars (
    id        INTEGER PRIMARY KEY,
    week      TEXT NOT NULL,
    repo      TEXT NOT NULL,          -- 'browser-use/browser-use'
    domain_id TEXT NOT NULL,
    stars     INTEGER,
    delta     INTEGER                 -- 与上周差值
);

-- PyPI 框架每周下载量
CREATE TABLE pypi_weekly (
    id        INTEGER PRIMARY KEY,
    week      TEXT NOT NULL,
    package   TEXT NOT NULL,
    downloads INTEGER
);

-- 每次运行日志
CREATE TABLE run_log (
    id         INTEGER PRIMARY KEY,
    week       TEXT,
    started_at TEXT,
    finished_at TEXT,
    status     TEXT,                  -- 'ok' | 'partial' | 'error'
    notes      TEXT
);
```

## 关键决策

### ADR-001：输出为静态 HTML，不做 Web 服务
- 原因：避免服务器运维成本；HTML 文件可直接共享、打印、存档
- 代价：无实时访问；多人同时看需手动发文件
- 后续：v2 可加 GitHub Pages 自动发布

### ADR-002：LLM 仅用于 diff 摘要文案，不用于数据分析
- 原因：评分逻辑必须可复现，不能依赖 LLM 黑盒；LLM 只做自然语言转化
- 具体：输入 structured diff JSON → 输出 1 句中文摘要

### ADR-003：GitHub API 限流策略
- 使用 GITHUB_TOKEN（5000 req/h）
- 每领域只追踪 top-5 项目的实时 star 数（减少 API 调用）
- 新项目搜索使用 Search API（30 req/min），每领域 1 次查询
- 失败时使用上次缓存数据，在报告中标注「数据可能滞后」
