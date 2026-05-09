"""全局配置 — 路径与 API 设置"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).resolve().parents[2]
DATA_DIR  = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR   = BASE_DIR / "logs"
TMPL_DIR  = BASE_DIR / "templates"

DB_PATH       = DATA_DIR / "agent_radar.db"
SOURCE_DB     = Path(os.getenv("WECHAT_DB", "~/.yoli/memory.db")).expanduser()
REPORT_PATH   = OUTPUT_DIR / "report_latest.html"

GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

# 每领域追踪的 top 项目（repo full name）
TRACKED_REPOS: dict[str, list[str]] = {
    "coding":     ["anthropics/claude-code", "daytonaio/daytona", "getcursor/cursor"],
    "infra":      ["BerriAI/litellm", "modelcontextprotocol/python-sdk", "punkpeye/awesome-mcp-servers"],
    "browser":    ["browser-use/browser-use", "vercel-labs/agent-browser", "JoeanAmier/XHS-Downloader"],
    "rag":        ["chatchat-space/Langchain-Chatchat", "langchain-ai/langchain", "run-llama/llama_index"],
    "chatbot":    ["zhayujie/chatgpt-on-wechat", "lss233/kirara-ai", "78/xiaozhi-esp32"],
    "ai4science": ["binary-husky/gpt_academic", "bytedance/deer-flow", "shibing624/MedicalGPT"],
    "personal":   ["HKUDS/nanobot", "elie222/inbox-zero"],
    "finance":    ["ZhuLinsen/daily_stock_analysis", "hsliuping/TradingAgents-CN"],
    "social":     ["xpzouying/xiaohongshu-mcp", "cs-lazy-tools/ChatGPT-On-CS"],
    "creative":   ["comfyanonymous/ComfyUI"],
    "multimodal": ["OpenBMB/MiniCPM-o", "canopylabs/orpheus-tts", "fixie-ai/ultravox"],
    "hardware":   ["78/xiaozhi-esp32"],
}

# 每领域代表性 PyPI 包（用于衡量该领域的生产采用率）
DOMAIN_PYPI: dict[str, list[dict]] = {
    # 编程开发：Agent 工具协议、代码 Agent 框架、可观测
    "coding": [
        {"pkg": "mcp",           "label": "MCP 协议 SDK"},
        {"pkg": "fastmcp",       "label": "FastMCP server"},
        {"pkg": "pydantic-ai",   "label": "Pydantic AI Agent"},
        {"pkg": "openai-agents", "label": "OpenAI Agents SDK"},
        {"pkg": "instructor",    "label": "Instructor 结构化输出"},
        {"pkg": "aider-chat",    "label": "Aider AI 结对编程"},
        {"pkg": "agentops",      "label": "AgentOps 可观测性"},
    ],
    # 基础设施：Agent 框架、路由、编排、监控
    "infra": [
        {"pkg": "litellm",       "label": "LiteLLM 多模型路由"},
        {"pkg": "crewai",        "label": "CrewAI 多 Agent 编排"},
        {"pkg": "langgraph",     "label": "LangGraph 状态图"},
        {"pkg": "langchain-core","label": "LangChain Core"},
        {"pkg": "autogen",       "label": "AutoGen 微软框架"},
        {"pkg": "mem0ai",        "label": "Mem0 Agent 记忆层"},
        {"pkg": "instructor",    "label": "Instructor 结构化"},
        {"pkg": "agentops",      "label": "AgentOps 监控"},
    ],
    # 浏览器/爬虫：仅浏览器自动化、抓取专属工具
    "browser": [
        {"pkg": "browser-use",   "label": "browser-use（$17M A轮）"},
        {"pkg": "playwright",    "label": "Playwright 浏览器自动化"},
        {"pkg": "selenium",      "label": "Selenium 经典 RPA"},
        {"pkg": "scrapy",        "label": "Scrapy 爬虫框架"},
        {"pkg": "pyppeteer",     "label": "Pyppeteer Chrome 控制"},
        {"pkg": "curl-cffi",     "label": "curl-cffi 反指纹检测"},
        {"pkg": "beautifulsoup4","label": "BeautifulSoup HTML 解析"},
        {"pkg": "parsel",        "label": "Parsel XPath/CSS 选择器"},
        {"pkg": "unstructured",  "label": "Unstructured 网页结构化"},
    ],
    # RAG/知识库：向量库、检索、文档解析
    "rag": [
        {"pkg": "llama-index-core",      "label": "LlamaIndex 检索框架"},
        {"pkg": "langchain-core",        "label": "LangChain Core"},
        {"pkg": "chromadb",              "label": "ChromaDB 向量库"},
        {"pkg": "qdrant-client",         "label": "Qdrant 向量数据库"},
        {"pkg": "faiss-cpu",             "label": "FAISS 相似度检索"},
        {"pkg": "sentence-transformers", "label": "Sentence-BERT Embedding"},
        {"pkg": "tiktoken",              "label": "tiktoken Token 计数"},
        {"pkg": "unstructured",          "label": "Unstructured 文档解析"},
        {"pkg": "pymupdf",               "label": "PyMuPDF PDF 解析"},
    ],
    # 对话机器人：Bot SDK、对话平台
    "chatbot": [
        {"pkg": "python-telegram-bot","label": "Telegram Bot SDK"},
        {"pkg": "discord.py",         "label": "Discord Bot"},
        {"pkg": "slack-sdk",          "label": "Slack Bot SDK"},
        {"pkg": "mem0ai",             "label": "Mem0 对话记忆"},
        {"pkg": "gradio",             "label": "Gradio 对话 UI"},
        {"pkg": "streamlit",          "label": "Streamlit WebUI"},
        {"pkg": "nonebot2",           "label": "NoneBot2 国产 Bot 框架"},
    ],
    # AI×科研：生信、化学、药物、论文检索（无通用数据/绘图库）
    "ai4science": [
        {"pkg": "biopython",     "label": "BioPython 生物信息学"},
        {"pkg": "deepchem",      "label": "DeepChem 药物发现"},
        {"pkg": "rdkit",         "label": "RDKit 化学信息学"},
        {"pkg": "scikit-learn",  "label": "scikit-learn ML 实验基础"},
        {"pkg": "arxiv",         "label": "arxiv 论文检索 API"},
        {"pkg": "pymatgen",      "label": "pymatgen 材料科学"},
        {"pkg": "mdanalysis",    "label": "MDAnalysis 分子动力学"},
        {"pkg": "openmm",        "label": "OpenMM 蛋白质模拟"},
    ],
    # 个人助理：日历/邮件/任务管理专属 SDK
    "personal": [
        {"pkg": "mem0ai",                  "label": "Mem0 个人记忆"},
        {"pkg": "google-api-python-client","label": "Google Calendar/Gmail"},
        {"pkg": "notion-client",           "label": "Notion API"},
        {"pkg": "todoist-api-python",      "label": "Todoist 任务管理"},
        {"pkg": "icalendar",               "label": "iCalendar 日程解析"},
        {"pkg": "schedule",                "label": "schedule 定时任务"},
        {"pkg": "caldav",                  "label": "CalDAV 日历协议"},
        {"pkg": "exchangelib",             "label": "exchangelib Outlook/Exchange"},
    ],
    # 金融：行情数据、回测、量化专属库
    "finance": [
        {"pkg": "akshare",         "label": "AKShare A股免费数据"},
        {"pkg": "yfinance",        "label": "yfinance 国际行情"},
        {"pkg": "backtrader",      "label": "Backtrader 策略回测"},
        {"pkg": "pandas-ta",       "label": "pandas-ta 技术指标"},
        {"pkg": "tushare",         "label": "Tushare A股（付费）"},
        {"pkg": "zipline-reloaded","label": "Zipline 回测引擎"},
        {"pkg": "pyfolio-reloaded","label": "Pyfolio 组合归因"},
        {"pkg": "quantlib",        "label": "QuantLib 衍生品定价"},
        {"pkg": "ccxt",            "label": "CCXT 加密货币交易"},
    ],
    # 社媒运营：内容采集/自动化（无通用 HTTP/图片库）
    "social": [
        {"pkg": "playwright",    "label": "Playwright 账号自动化"},
        {"pkg": "selenium",      "label": "Selenium 操作浏览器"},
        {"pkg": "scrapy",        "label": "Scrapy 内容抓取"},
        {"pkg": "jieba",         "label": "jieba 中文分词/关键词"},
        {"pkg": "weibo-scraper", "label": "微博数据抓取"},
        {"pkg": "instaloader",   "label": "instaloader Instagram 采集"},
        {"pkg": "twscrape",      "label": "twscrape Twitter/X 采集"},
        {"pkg": "schedule",      "label": "schedule 定时发布"},
    ],
    # 创意/生成：扩散模型、图像生成专属库（无通用 torch）
    "creative": [
        {"pkg": "diffusers",      "label": "Diffusers 扩散模型核心"},
        {"pkg": "accelerate",     "label": "Accelerate 分布式训练"},
        {"pkg": "controlnet-aux", "label": "ControlNet 条件控制"},
        {"pkg": "compel",         "label": "Compel Prompt 权重"},
        {"pkg": "insightface",    "label": "InsightFace 人脸识别/换脸"},
        {"pkg": "moviepy",        "label": "MoviePy 视频剪辑"},
        {"pkg": "opencv-python",  "label": "OpenCV 图像处理"},
    ],
    # 语音/多模态：ASR/TTS/音频专属库
    "multimodal": [
        {"pkg": "openai-whisper", "label": "Whisper 语音识别"},
        {"pkg": "faster-whisper", "label": "faster-whisper 加速 ASR"},
        {"pkg": "TTS",            "label": "Coqui TTS 语音合成"},
        {"pkg": "pyaudio",        "label": "PyAudio 实时音频流"},
        {"pkg": "soundfile",      "label": "SoundFile 音频读写"},
        {"pkg": "speechbrain",    "label": "SpeechBrain 语音工具包"},
        {"pkg": "pydub",          "label": "pydub 音频格式转换"},
        {"pkg": "kokoro",         "label": "Kokoro TTS 中文语音"},
    ],
    # 硬件/边缘：固件、串口、边缘推理专属库
    "hardware": [
        {"pkg": "esptool",        "label": "esptool ESP 固件烧录"},
        {"pkg": "pyserial",       "label": "pyserial 串口通信"},
        {"pkg": "onnxruntime",    "label": "ONNX Runtime 边缘推理"},
        {"pkg": "tflite-runtime", "label": "TFLite 嵌入式推理"},
        {"pkg": "vosk",           "label": "Vosk 离线语音识别"},
        {"pkg": "opencv-python",  "label": "OpenCV 边缘视觉"},
        {"pkg": "paho-mqtt",      "label": "paho-mqtt IoT 消息"},
        {"pkg": "gpiozero",       "label": "gpiozero 树莓派 GPIO"},
    ],
}

# 兼容旧字段（爬虫仍需遍历）
PYPI_PACKAGES = list({
    entry["pkg"]
    for entries in DOMAIN_PYPI.values()
    for entry in entries
})

# repos.json 领域分类关键词（匹配 topics + description + name）
DOMAIN_REPO_KWS: dict[str, list[str]] = {
    "coding":     ["mcp", "code agent", "coding agent", "aider", "cursor", "copilot", "devtools",
                   "code review", "github copilot", "opencode", "devin", "swe-agent", "sweagent",
                   "code generation", "code completion", "ide agent", "terminal agent"],
    "infra":      ["agent framework", "multi-agent", "multiagent", "langchain", "crewai", "autogen",
                   "langgraph", "litellm", "llm router", "llm gateway", "agent orchestrat",
                   "tool calling", "function calling", "pydantic-ai", "llm framework", "llm wrapper"],
    "browser":    ["browser agent", "browser use", "web agent", "web automation", "rpa", "scraper",
                   "crawler", "playwright", "selenium", "puppeteer", "web scraping", "spider",
                   "爬虫", "computer use", "gui agent", "desktop automation"],
    "rag":        ["rag", "retrieval augmented", "knowledge base", "vector database", "embedding",
                   "document qa", "pdf chat", "knowledge graph", "semantic search", "知识库",
                   "chatchat", "fastgpt", "dify", "langchain rag", "pandawiki"],
    "chatbot":    ["chatbot", "wechat bot", "discord bot", "telegram bot", "customer service",
                   "微信机器人", "客服", "on-wechat", "openwebui", "chat ui", "llm chat",
                   "conversational", "nonebot", "kirara"],
    "ai4science": ["ai for science", "drug discovery", "protein", "molecular", "bioinformatics",
                   "chemistry", "materials science", "scientific", "research agent", "paper",
                   "academic", "lab automation", "medical ai", "clinical", "gpt academic"],
    "personal":   ["personal assistant", "personal agent", "life os", "second brain", "productivity",
                   "email agent", "calendar", "task manager", "inbox", "nanobot", "memo", "jarvis"],
    "finance":    ["stock", "trading", "quant", "quantitative", "financial", "投资", "股票",
                   "a股", "hedge fund", "backtest", "algorithmic trading", "fintech", "market data",
                   "portfolio", "TradingAgents", "akshare"],
    "social":     ["xiaohongshu", "小红书", "douyin", "tiktok", "weibo", "social media",
                   "content creation", "influencer", "social automation", "运营", "自媒体", "xhs"],
    "creative":   ["image generation", "text to image", "stable diffusion", "comfyui", "diffusion",
                   "video generation", "music generation", "ai art", "midjourney", "flux",
                   "controlnet", "lora", "dreambooth", "ai video", "sora"],
    "multimodal": ["speech", "voice", "tts", "asr", "whisper", "text to speech", "speech to text",
                   "audio", "multimodal", "vision language", "real-time voice", "语音", "ultravox",
                   "orpheus", "kokoro", "realtime api"],
    "hardware":   ["esp32", "raspberry pi", "arduino", "iot", "embedded", "edge ai", "firmware",
                   "micropython", "robot", "hardware agent", "边缘", "嵌入式", "xiaozhi",
                   "local llm", "on-device"],
}

# 群聊关键词（与现有分析保持一致）
WECHAT_DOMAIN_KWS: dict[str, list[str]] = {
    "coding":     ["claude code", "cursor", "copilot", "opencode", "codex", "coding agent", "ide", "代码", "编程"],
    "browser":    ["browser", "爬虫", "spider", "小红书", "selenium", "playwright", "rpa", "自动化浏览"],
    "rag":        ["知识库", "rag", "向量", "检索", "pandawiki", "文档", "embedding", "chatchat"],
    "creative":   ["comfyui", "stable diffusion", "短剧", "ai绘画", "视频生成", "音乐生成"],
    "chatbot":    ["微信机器人", "chatbot", "客服", "on-wechat", "openwebui", "对话"],
    "personal":   ["个人助理", "zeroclaw", "nanobot", "lobster", "任务代理"],
    "finance":    ["股票", "a股", "量化", "期货", "交易", "理财", "金融"],
    "ai4science": ["蛋白质", "药物", "bioinformatics", "科研", "论文", "pubmed", "医学", "ml实验"],
    "social":     ["小红书运营", "xianyu", "闲鱼", "内容创作", "营销", "抖音"],
    "infra":      ["langchain", "crewai", "mcp", "autogen", "框架", "多agent", "subagent"],
    "multimodal": ["语音", "tts", "多模态", "ultravox", "miniCPM", "音频"],
    "hardware":   ["esp32", "嵌入式", "iot", "硬件", "边缘", "本地部署", "xiaozhi"],
}
