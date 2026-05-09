# PRD — agent-radar

## 6W2H

| 维度 | 内容 |
|------|------|
| **Who** | 主用户：产品经理/投资人/开发者负责人（需要每周了解 AI 开源生态动向的决策者）。反面用户：需要实时监控的场景（本产品是周维度，非实时）。 |
| **What** | 每周自动抓取 GitHub AI 项目数据、PyPI 下载量、本地群聊信号，更新 12 个应用领域的供需分析，生成一份含「本周新增 / 趋势变化 / 本周判断更新」的 HTML 周报。 |
| **Where** | 本地 macOS 机器定时运行；输出 HTML 文件，可直接打开或部署为静态站点。 |
| **When** | 每周一凌晨自动执行，用户周一早上打开最新报告。 |
| **Why** | 现在是手动分析（一次性脚本），费时且数据老化。AI 领域变化极快，一份两周前的分析已经过时；需要持续追踪而非一次性报告。 |
| **How** | 1. 爬虫获取增量数据（GitHub + PyPI）→ 2. 存入 SQLite 时序表 → 3. 重新计算各领域评分 → 4. 与上周快照对比生成 diff → 5. LLM 生成 diff 摘要文案 → 6. 渲染 HTML 报告（含 diff section） |
| **How Much** | 开发成本：~3天；运营成本：GitHub Token（免费）+ LLM API（约 $0.1/次）；规模：单机运行，无服务器成本。 |
| **How Well** | 周报生成耗时 < 10 分钟；GitHub API 成功率 > 95%；HTML 可在 Safari/Chrome 直接打开无需服务器。 |

---

## 核心功能（MVP 范围）

### F1 — 数据爬虫
- GitHub Search API：按领域关键词搜索，获取本周新增项目（created 日期过滤）
- GitHub Repos API：获取已追踪项目的最新 star 数（top 3/领域）
- PyPI Stats API：`pypistats.org/api/packages/{name}/recent` 获取周下载量
- 本地群聊：读取 `~/.yoli/memory.db` 获取本周新增群聊消息

### F2 — 时序存储
- `snapshots` 表：每次运行的领域评分快照（week + domain + supply + demand + d1~d4）
- `project_stars` 表：追踪项目的每周 star 数（week + repo + stars）
- `pypi_weekly` 表：框架每周下载量时序

### F3 — 评分引擎
- 统一 4 维公式（同现有 HTML 报告）
- Track-A（群聊 ≥ 50 条）/ Track-B（群聊不足，用替代指标）
- 输出每领域的评分 breakdown

### F4 — Diff 生成
- 对比本周 vs 上周快照
- 输出：score 变化 > 3 的领域标注「↑↓」
- 新进入追踪的项目标注「🆕」
- LLM 生成每领域 1 句 diff 摘要（中文）

### F5 — HTML 周报
- 在现有报告基础上增加「本周更新」顶部 section
- 各领域卡片显示周环比变化
- ⓘ 点击浮出卡片显示评分依据（现有功能保留）

### F6 — 调度
- macOS launchd plist，每周一 06:00 触发
- 运行日志写入 `logs/`
- 失败时发系统通知（`osascript`）

---

## 不在 MVP 范围
- 邮件发送（v2 再做）
- Web 服务器 / 在线访问（v2 再做）
- 多人协作 / 权限控制
- 历史报告归档 UI（SQLite 中有数据，UI 后续加）
