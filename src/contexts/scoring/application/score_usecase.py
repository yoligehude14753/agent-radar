"""评分用例 — 统一4维公式，Track-A/B 双轨道，写入 domain_snapshots"""
from __future__ import annotations
import math
from dataclasses import dataclass
from src.shared.db import get_conn
from src.shared.config import TRACKED_REPOS

# ── 领域固定参数（不依赖实时数据的部分）──────────────────────────────
# market_level: 1-5 人工评级，附文字依据（见 docs/PRD.md）
DOMAIN_META: dict[str, dict] = {
    "coding": {
        "name": "编程开发 Agent", "sub": "AI IDE · 代码补全 · Code Review · DevOps 自动化",
        "count": 3541, "new26": 412,
        "commercial": 4, "market_level": 5, "pypi_pkg": "mcp",
        "top_repo": "anthropics/claude-code", "topProject": "Claude Code", "topStars": "22k+",
        "verdict": "exploding", "verdictLabel": "持续井喷",
        "market_note": "全球开发者工具市场$2000亿+",
        "prediction": "编程 Agent 是所有领域中增长最快、商业化最成熟的方向。Claude Code、Cursor 从 0 到 $10B 估值的路径已经验证，2026 年下半年将进入增量竞争阶段——差异化能力是关键，而非存在感本身。",
        "situation": "3541 个 GitHub 项目中约 15% 在 2025 年后创建，2026 上半年新增 412 个。Claude Code 月活已破百万，MCP 协议日安装量超 30 万次。GitHub Copilot 企业版 ARR 突破 $4.5 亿，验证付费意愿极强。",
        "devBehavior": "开发者主要在做三件事：① 为 Claude Code / Cursor 写 MCP 工具插件；② 搭建私有 Code Review 流水线（替代人工 review）；③ 把 IDE Agent 嵌入 CI/CD 实现 PR 自动修复。底层基础设施竞争已白热化，但垂直场景（安全审计、数据库查询生成）依然蓝海。",
        "community": "群聊高频词：「claude code 真好用」「cursor rule 怎么写」「mcp server 报错」「token 太贵了」「公司不让用怎么办」。痛点集中在：成本控制、企业安全合规、上下文 token 限制。",
        "opportunity": "企业内网部署版（安全合规） + 代码库专属 MCP 工具生成器 + Code Review 质量评估层。ToB SaaS 模式，客单价 $50-500/月/开发者，市场空间极大。",
    },
    "infra": {
        "name": "Agent 基础设施", "sub": "框架 · 协议 · 路由 · 编排 · 评测",
        "count": 234, "new26": 67,
        "commercial": 3, "market_level": 4, "pypi_pkg": "litellm",
        "top_repo": "BerriAI/litellm", "topProject": "LiteLLM", "topStars": "18k+",
        "verdict": "infrawar", "verdictLabel": "基础设施战",
        "market_note": "所有 Agent 都依赖，三个赢家已确立",
        "prediction": "基础设施层赢家正在形成寡头格局：LiteLLM（路由）、MCP（工具协议）、LangChain（编排）三足鼎立。新进入者窗口收窄，垂直场景专用基础设施（如 Agent 评测、Trace 监控）仍有机会。",
        "situation": "litellm 周下载量超 500 万次，anthropic SDK 月下载破 1 亿。MCP 协议从 Anthropic 内部工具演变为行业标准，2026 年支持 MCP 的产品超 500 个。LangChain 2.0 重构后性能提升 3x。",
        "devBehavior": "开发者在做：① 写 FastMCP 插件生态（工具即插件）；② 搭建 multi-agent 编排框架（替代 CrewAI 等重框架）；③ 构建 Agent 可观测性工具（Trace/Cost/Eval Dashboard）。",
        "community": "痛点：「agent 之间通信没有标准」「tool call 报错没法 debug」「litellm 又改 API 了」「评测哪个框架好用」。工程师对『重框架』普遍有疲感，更倾向轻量 SDK。",
        "opportunity": "Agent 评测平台（替代人工测试）+ 成本优化 Router（动态选模型降低 50% 费用）。已有初步商业化案例，B 轮窗口期。",
    },
    "browser": {
        "name": "浏览器/GUI Agent", "sub": "网页自动化 · RPA · 爬虫 · 内容采集",
        "count": 58, "new26": 23,
        "commercial": 0, "market_level": 4, "pypi_pkg": "browser-use",
        "top_repo": "browser-use/browser-use", "topProject": "browser-use", "topStars": "62k+",
        "verdict": "gap", "verdictLabel": "需求缺口",
        "big_funding": True,
        "market_note": "$17M 融资，RPA 替代市场 $30B+",
        "prediction": "browser-use 的爆发（单周 +8k stars）证明「让 AI 操作浏览器」的需求早已存在但一直没有好的开源方案。当前工程问题（验证码、反爬）是暂时门槛，不是行业天花板。未来 12 个月将出现面向垂直场景的专业化产品。",
        "situation": "browser-use 获 $17M A 轮，估值过 $1 亿。GitHub 项目数仅 58 个，但头部项目 stars 极高（62k+），说明用户聚焦在少数解决方案上，需求集中。小红书、抖音等平台的内容采集需求暴增。",
        "devBehavior": "开发者聚焦：① 反反爬技术研究（指纹、验证码绕过）；② 与 computer-use 结合的多模态控制；③ 低代码 RPA 录制+重放工具。",
        "community": "「playwright 被封了怎么办」「小红书 MCP 接口能用吗」「browser-use 太慢」「cost 太高能做到多便宜」。用户容忍度高但付费门槛也高。",
        "opportunity": "垂直爬虫 SaaS（电商/社媒数据订阅）+ 企业内网 RPA（替代 UiPath/Automation Anywhere）。国内市场对数据合规要求高，私有化部署是差异化。",
    },
    "rag": {
        "name": "RAG / 知识库", "sub": "企业知识库 · 文档问答 · 语义检索 · Wiki",
        "count": 677, "new26": 89,
        "commercial": 3, "market_level": 3, "pypi_pkg": "llama-index-core",
        "top_repo": "chatchat-space/Langchain-Chatchat", "topProject": "Chatchat", "topStars": "33k+",
        "verdict": "reshaping", "verdictLabel": "格局重塑",
        "market_note": "Dify $30M，企业知识库成熟市场",
        "prediction": "RAG 市场已进入成熟期，基础 RAG 已是商品化功能（Dify、FastGPT 都内置）。增量在于：Graph RAG（知识图谱 + 向量双路召回）和 Agentic RAG（自动判断是否检索）。纯 RAG 创业空间收窄，但细分垂直行业（法律、医疗）仍有机会。",
        "situation": "Dify 拿到 $30M B 轮，Langchain-Chatchat 33k stars，FastGPT 24k。2025 年 GraphRAG 相关项目增长 300%+，微软开源版本月下载超百万。",
        "devBehavior": "① 从 Naive RAG 升级到 GraphRAG + Reranker 双路召回；② 构建多租户知识库（一个平台服务多家企业）；③ 优化 chunk 策略和 embedding 模型选型。",
        "community": "「召回率不准怎么优化」「chunk 大小怎么调」「embedding 用哪个模型」「bge 还是 m3e」「多路召回实测效果」。纯技术讨论多，付费产品少。",
        "opportunity": "行业专属 RAG（法律合同、医疗记录）+ RAG 质量评估工具（自动化 recall@k 测试）。付费意愿强的垂直行业客单价高。",
    },
    "chatbot": {
        "name": "对话机器人 / 客服", "sub": "微信 Bot · 智能客服 · OpenWebUI · 企业助理",
        "count": 191, "new26": 34,
        "commercial": 3, "market_level": 3, "pypi_pkg": None,
        "top_repo": "zhayujie/chatgpt-on-wechat", "topProject": "chatgpt-on-wechat", "topStars": "34k+",
        "verdict": "reshaping", "verdictLabel": "格局重塑",
        "market_note": "微信生态刚需，但纯软件红海",
        "prediction": "微信 Bot 类工具已高度同质化，用户倾向于用一个通用平台。真正的增量在「角色扮演 / 情感陪伴」和「企业内部 AI 助理」两个方向。前者消费级市场爆发，后者 B 端付费成熟。",
        "situation": "chatgpt-on-wechat 34k stars，kirara-ai 3k。OpenWebUI 月活超 200 万，成为私有部署的事实标准。Character.AI 估值 $50 亿验证情感陪伴市场。",
        "devBehavior": "① 整合多模型路由（OpenAI + Claude + 本地模型）的统一接入层；② 为企业微信/钉钉定制 Bot；③ 角色扮演引擎开发（记忆+人设维持）。",
        "community": "「微信号被封了」「企业微信接口收费了」「怎么接 claude」「local model 效果差」「公司能不能用」。合规和成本是核心焦虑。",
        "opportunity": "企业内部 AI 助理平台（HR/法务/销售）+ 情感陪伴垂类（需要模型 fine-tune）。前者 B2B 模式稳健，后者 C 端增长快但合规风险高。",
    },
    "ai4science": {
        "name": "AI × 科研 / 学术", "sub": "论文辅助 · 实验自动化 · 药物发现 · ML 研究",
        "count": 1245, "new26": 201,
        "commercial": 2, "market_level": 3, "pypi_pkg": None,
        "top_repo": "binary-husky/gpt_academic", "topProject": "gpt_academic", "topStars": "67k+",
        "verdict": "gap", "verdictLabel": "低估蓝海",
        "market_note": "学术圈低估 10 倍，CRO 付费意愿强",
        "prediction": "AI for Science 在 GitHub 上项目数极多（1245），但商业化程度低，存在「有供给无商业」的结构性低估。gpt_academic 证明了学术工具用户基数庞大，但付费路径尚未打通。蛋白质结构、药物发现是率先商业化的突破口。",
        "situation": "gpt_academic 67k stars，DeerFlow（字节）2k，Elicit/Consensus 等海外付费学术工具 ARR 均超 $1000 万。AlphaFold 3 开源加速了生物信息基础设施建设。",
        "devBehavior": "① 文献综述自动化（PDF 解析 + 向量检索 + 摘要生成）；② 实验 log 分析 Agent；③ 论文图表生成 + LaTeX 格式化。大量工具仍处于「个人用爽了但没有产品化」阶段。",
        "community": "群聊覆盖不足，但在学术论坛/知乎/X 上讨论活跃。核心痛点：「PDF 解析效果差」「引用格式出错」「模型幻觉在论文里很危险」「实验室服务器没法连外网」。",
        "opportunity": "面向 CRO/Biotech 的实验数据分析 Agent（付费意愿强，数据私密性需求高）+ 高校科研助理 SaaS（订阅模式）。",
    },
    "personal": {
        "name": "个人 AI 助理", "sub": "日程 · 邮件 · 记忆 · 全能助手 · Second Brain",
        "count": 4, "new26": 2,
        "commercial": 3, "market_level": 4, "pypi_pkg": None,
        "top_repo": "HKUDS/nanobot", "topProject": "nanobot", "topStars": "11k+",
        "verdict": "nascent", "verdictLabel": "蓄势待发",
        "market_note": "均星 11k 全领域最高，需求确定",
        "prediction": "个人 AI 助理是需求最确定但开源供给最少的领域（仅 4 个项目，均星 11k 全领域最高）。需求缺口极大，关键障碍是「个人数据授权和隐私」。2026 下半年随着本地模型能力提升，将迎来爆发期。",
        "situation": "nanobot 11k stars，inbox-zero 聚焦邮件自动化 5k stars。NotebookLM 月活 2000 万验证个人知识管理需求。Apple Intelligence 2026 版将带来本地 Agent API，可能是爆发催化剂。",
        "devBehavior": "少数开发者在攻克：① 跨 App 数据整合（日历 + 邮件 + 笔记）；② 长期记忆系统（不丢失上下文）；③ 本地优先隐私架构。主流开发者在「等待模型能力提升」。",
        "community": "「有没有好用的个人助理」「zeroclaw 怎么样」「记忆太短了」「能帮我管理邮件吗」。用户有强烈意愿但找不到满意产品。",
        "opportunity": "本地运行的个人数据 Agent（隐私敏感用户）+ 邮件/日程 AI 助手（高价值 ToC 产品）。先做 niche 用户（程序员）再扩展。",
    },
    "finance": {
        "name": "金融 / 投资 Agent", "sub": "A 股分析 · 量化策略 · 投资研究 · 财报解读",
        "count": 42, "new26": 11,
        "commercial": 2, "market_level": 4, "pypi_pkg": None,
        "top_repo": "ZhuLinsen/daily_stock_analysis", "topProject": "daily_stock_analysis", "topStars": "4.5k+",
        "verdict": "china", "verdictLabel": "中国特供",
        "market_note": "2 亿中国散户，A 股市场唯一性",
        "prediction": "中国 A 股是全球最独特的 AI 金融应用场景：2 亿散户 + 政策驱动市场 + 市场不成熟。TradingAgents-CN 的出现标志着「海外量化框架本土化」趋势。未来 18 个月将出现年收入千万级的 A 股 AI 投研产品。",
        "situation": "42 个 GitHub 项目，daily_stock_analysis 4.5k stars，TradingAgents-CN 专注 A 股量化。Wind/Bloomberg 替代市场空间大，AI 投研 SaaS 已有 3-5 家拿到 A 轮。",
        "devBehavior": "① A 股因子挖掘 Agent；② 财报解读 + 舆情分析联动；③ 量化策略回测框架（国内数据源兼容）。数据源是核心壁垒。",
        "community": "「A 股数据哪里能拿到」「wind 太贵了」「东方财富 API 怎么用」「模型能预测涨跌吗」「风险控制怎么做」。数据获取是最大障碍。",
        "opportunity": "A 股散户 AI 投顾（月费 99-299 元，千万 MAU 目标市场）+ 量化私募 AI 工具（B 端，单客户 10 万+/年）。",
    },
    "social": {
        "name": "社媒运营 / 内容 Agent", "sub": "小红书 · 抖音 · 自动发帖 · 账号管理",
        "count": 14, "new26": 8,
        "commercial": 2, "market_level": 4, "pypi_pkg": None,
        "top_repo": "xpzouying/xiaohongshu-mcp", "topProject": "xiaohongshu-mcp", "topStars": "2k+",
        "verdict": "china", "verdictLabel": "中国特供",
        "market_note": "中国独有，百万商家用户",
        "prediction": "社媒运营 Agent 是 2026 年增长最快的细分之一。百万小红书商家 + 抖音 MCN 机构有强烈降本需求。MCP 协议使「AI 直接操作账号」变为可能，监管风险是唯一变量。",
        "situation": "仅 14 个 GitHub 项目但都是 2025 年后新项目，增长率最高。xhs-downloader 6k stars，xiaohongshu-mcp 是 MCP 协议在社媒运营的首批实践。",
        "devBehavior": "① 小红书/抖音内容自动生成 + 发布；② 竞品监控 + 选题推荐 Agent；③ 私信自动回复（客服功能）。大多数工具仍是脚本级而非产品级。",
        "community": "「小红书 API 有没有官方的」「账号被封了怎么办」「AI 写的内容能过审吗」「自动发帖有没有风险」。平台合规是最大顾虑。",
        "opportunity": "商家 AI 运营 SaaS（发帖 + 数据分析 + 客服一体化）+ MCN 机构批量账号管理工具。需要与平台方建立合作关系以规避封号风险。",
    },
    "creative": {
        "name": "创意 / 生成 Agent", "sub": "AI 绘画 · 视频生成 · 音乐 · ComfyUI 工作流",
        "count": 50, "new26": 6,
        "commercial": 1, "market_level": 2, "pypi_pkg": None,
        "top_repo": "comfyanonymous/ComfyUI", "topProject": "ComfyUI", "topStars": "74k+",
        "verdict": "zombie", "verdictLabel": "开源失速",
        "market_note": "开源已落后闭源，垂直 pipeline 机会",
        "prediction": "生成式 AI 创意工具的开源项目已在被 Midjourney / Sora / Kling 等闭源产品碾压。ComfyUI 因为工作流编排的独特价值仍存活，但新的纯生成工具很难靠开源建立竞争优势。机会在垂直应用层（广告素材 / 短剧 / 游戏资产）。",
        "situation": "ComfyUI 74k stars 但主要活跃在 2024 年前，2026 年新增项目仅 6 个。Sora 商业版 + Kling AI 月活均破千万，开源社区被虹吸。",
        "devBehavior": "① 基于 ComfyUI 构建垂直工作流（广告图生成）；② 整合多个生成 API 的统一调用层；③ 短剧/游戏素材批量生产工具。",
        "community": "「comfyui 节点报错」「stable diffusion 还有人用吗」「sora 效果比 wan 好太多」「要不要转去学 video」。开源社区有失落感。",
        "opportunity": "广告行业 AI 素材批量生产 SaaS（效率提升 10x）+ 游戏公司 AI 资产管线（B2B，替代外包）。关键是站在闭源模型肩膀上做应用层，不做底层生成模型。",
    },
    "multimodal": {
        "name": "语音 / 多模态 Agent", "sub": "TTS · 语音助手 · 实时对话 · 多模态理解",
        "count": 28, "new26": 12,
        "commercial": 2, "market_level": 3, "pypi_pkg": None,
        "top_repo": "canopylabs/orpheus-tts", "topProject": "Orpheus-TTS", "topStars": "9k+",
        "verdict": "forming", "verdictLabel": "成形中",
        "market_note": "AI 语音 YoY+34%，基础就绪待应用",
        "prediction": "语音 AI 基础能力（TTS/ASR/实时对话）在 2025-2026 已跨越可用门槛。Orpheus-TTS 的出现证明开源 TTS 可以媲美闭源。下一步增量是应用层：实时翻译耳机、语音 CRM、电话 AI 客服。",
        "situation": "Orpheus-TTS 9k stars，MiniCPM-o 多模态，Ultravox 实时语音。ElevenLabs ARR $1亿+，证明 TTS 付费市场成熟。国内讯飞、字节 TTS 商业版已成熟，开源追赶中。",
        "devBehavior": "① 实时语音对话系统（低延迟 < 200ms）；② 多语言 TTS 模型微调；③ 语音+视觉多模态理解（会议记录 + 截图分析）。",
        "community": "「有没有好用的中文 TTS」「实时语音延迟怎么优化」「电话机器人用什么」「语音克隆合不合法」。中文语音质量和延迟是核心诉求。",
        "opportunity": "电话 AI 客服（替换人工坐席，年省 60%+ 人力成本）+ 实时翻译耳机配套 App。前者 B 端付费强，后者需要硬件合作。",
    },
    "hardware": {
        "name": "硬件 / 边缘 Agent", "sub": "ESP32 · IoT · 本地部署 · 嵌入式 AI",
        "count": 19, "new26": 7,
        "commercial": 1, "market_level": 2, "pypi_pkg": None,
        "top_repo": "78/xiaozhi-esp32", "topProject": "xiaozhi-esp32", "topStars": "24k+",
        "verdict": "nascent", "verdictLabel": "早期探索",
        "market_note": "IoT 市场大但 AI 化率低，早期",
        "prediction": "硬件 AI 是长周期赛道，小智 ESP32 的 24k stars 证明「低成本 AI 硬件」有强大的 maker 社区吸引力。但从 maker 玩具到消费电子产品，距离遥远。2026 下半年 Qwen2.5-0.5B 等轻量模型的进步将加速边缘 AI 可行性。",
        "situation": "小智 ESP32 24k stars，是边缘 AI 领域唯一爆款开源项目。树莓派 AI Kit 发布，边缘 AI 芯片（NPU）价格下降 60%。但完整的边缘 Agent SDK 仍缺失。",
        "devBehavior": "① 在 ESP32/树莓派上运行 0.5-3B 本地模型；② 语音唤醒 + 本地意图识别；③ 工业 IoT 质检 Agent（视觉 + 决策一体化）。",
        "community": "「小模型能跑什么任务」「树莓派跑 qwen 效果怎么样」「边缘推理延迟多少」「NPU 怎么用」。技术爱好者主导，商业化早期。",
        "opportunity": "工业质检 AI（替代人工抽检，B2B 高毛利）+ AI 玩具/教育硬件（消费市场，量大但单价低）。工业方向更快盈利。",
    },
}

_MAX_WECHAT = 600
_MAX_PYPI   = 108_750_766  # litellm 满分基准
_MAX_STARS  = 135_653      # obra/superpowers 满分基准


@dataclass
class DomainScore:
    domain_id: str
    supply: int
    demand: int
    d1: int; d1_track: str
    d2: int
    d3: int
    d4: int


def _calc_supply(count: int) -> int:
    """log₁₀ 归一化到 [0,100]，参考区间 [4, 3541]"""
    if count <= 1:
        return 0
    return round((math.log10(count) - math.log10(4)) / (math.log10(3541) - math.log10(4)) * 100)


def _calc_d1(wechat: int) -> tuple[int, str]:
    """Track-A: 群聊≥50条用原始值；Track-B: 返回 -1 信号，由调用方用替代指标"""
    if wechat >= 50:
        return round(min(wechat / _MAX_WECHAT, 1) * 25), "A"
    return -1, "B"  # 调用方用替代指标


def _d1_fallback(domain_id: str, conn) -> int:
    """Track-B 替代指标：用头部项目 stars 速度代理"""
    top_repo = DOMAIN_META[domain_id].get("top_repo", "")
    if not top_repo:
        return 0
    row = conn.execute(
        "SELECT delta FROM project_stars WHERE repo=? ORDER BY week DESC LIMIT 1",
        (top_repo,)
    ).fetchone()
    if row and row["delta"] > 0:
        # 增速归一化：每月 1万 star 为基准 → 10分
        monthly_est = row["delta"] * 4  # 周→月
        return round(min(monthly_est / 10000, 1) * 15)
    # 没有增速数据，用静态 stars
    row2 = conn.execute(
        "SELECT stars FROM project_stars WHERE repo=? ORDER BY week DESC LIMIT 1",
        (top_repo,)
    ).fetchone()
    if row2:
        return round(min(row2["stars"] / _MAX_STARS, 1) * 15)
    return 0


def _calc_d2(domain_id: str, pypi_weekly: int | None, top_stars: int) -> int:
    """PyPI 有数据走对数归一化；否则用头部 Stars 代理（上限 20）"""
    meta = DOMAIN_META[domain_id]
    if meta.get("pypi_pkg") and pypi_weekly:
        return round(min(math.log10(max(pypi_weekly, 1)) / math.log10(_MAX_PYPI), 1) * 25)
    # Stars 代理（非 PyPI，降权上限 20）
    return round(min(top_stars / _MAX_STARS, 1) * 20)


def _calc_d3(commercial: int, big_funding: bool) -> int:
    if big_funding:
        return 25
    return round(min(commercial / 5, 1) * 25)


def _calc_d4(market_level: int) -> int:
    return market_level * 5


def compute_scores(week: str, wechat_counts: dict[str, int]) -> list[DomainScore]:
    conn = get_conn()
    scores: list[DomainScore] = []

    for domain_id, meta in DOMAIN_META.items():
        wechat = wechat_counts.get(domain_id, 0)

        # 供给
        supply = _calc_supply(meta["count"])

        # D1
        d1_raw, track = _calc_d1(wechat)
        if track == "B":
            d1 = _d1_fallback(domain_id, conn)
        else:
            d1 = d1_raw

        # 获取头部项目当前 stars
        top_repo = meta.get("top_repo", "")
        row = conn.execute(
            "SELECT stars FROM project_stars WHERE repo=? ORDER BY week DESC LIMIT 1",
            (top_repo,)
        ).fetchone()
        top_stars = row["stars"] if row else 0

        # 获取 PyPI 下载量
        pypi_weekly = None
        if meta.get("pypi_pkg"):
            r = conn.execute(
                "SELECT downloads FROM pypi_weekly WHERE package=? ORDER BY week DESC LIMIT 1",
                (meta["pypi_pkg"],)
            ).fetchone()
            if r:
                pypi_weekly = r["downloads"]

        d2 = _calc_d2(domain_id, pypi_weekly, top_stars)
        d3 = _calc_d3(meta["commercial"], meta.get("big_funding", False))
        d4 = _calc_d4(meta["market_level"])
        demand = d1 + d2 + d3 + d4

        score = DomainScore(
            domain_id=domain_id, supply=supply, demand=demand,
            d1=d1, d1_track=track, d2=d2, d3=d3, d4=d4
        )
        scores.append(score)

        conn.execute("""
            INSERT INTO domain_snapshots
                (week, domain_id, supply, demand, d1, d1_track, d2, d3, d4)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(week, domain_id) DO UPDATE SET
                supply=excluded.supply, demand=excluded.demand,
                d1=excluded.d1, d1_track=excluded.d1_track,
                d2=excluded.d2, d3=excluded.d3, d4=excluded.d4
        """, (week, domain_id, supply, demand, d1, track, d2, d3, d4))

    conn.commit()
    conn.close()
    return scores
