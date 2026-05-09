"""
full_import_usecase.py
======================
将 github-community-finder 爬取的全量 repos.json（~4.2万条）导入
full_project_registry 表，并用 results.jsonl 富化社区标签。

运行时机：
  - 首次：完整导入全部仓库
  - 每周：增量追加新仓库 + 更新现有仓库 star 数

用法（在 main.py 中调用）：
  from src.contexts.crawler.application.full_import_usecase import run_full_import
  run_full_import(verbose=True)
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from src.shared.db import get_conn
from src.shared.config import BASE_DIR

# ─── 数据源路径 ──────────────────────────────────────────────────────────────

COMMUNITY_FINDER_DIR = Path(
    "/Users/yoligehude/Desktop/all/openall/projects/github-community-finder"
)
REPOS_JSON    = COMMUNITY_FINDER_DIR / "report_full.html.cache" / "repos.json"
RESULTS_JSONL = COMMUNITY_FINDER_DIR / "report_full.html.cache" / "results.jsonl"

# ─── 领域关键词（用于自动打标签） ──────────────────────────────────────────

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "coding":      ["code", "coding", "cursor", "copilot", "ide", "dev", "compiler",
                    "autocomplete", "devin", "swe", "software engineer", "claude-code"],
    "infra":       ["llm", "inference", "deploy", "serving", "mcp", "gateway", "api",
                    "proxy", "litellm", "vllm", "ollama", "triton", "openai-compatible"],
    "browser":     ["browser", "web scraper", "crawl", "playwright", "selenium",
                    "web automation", "spider", "scraping"],
    "rag":         ["rag", "retrieval", "vector", "embedding", "knowledge base",
                    "langchain", "llama_index", "chroma", "faiss", "weaviate"],
    "chatbot":     ["chatbot", "wechat bot", "telegram bot", "discord bot",
                    "customer service", "客服", "对话", "conversational"],
    "ai4science":  ["medical", "biomedical", "chemistry", "protein", "drug",
                    "climate", "genomics", "biology", "physics", "科研", "学术"],
    "personal":    ["personal", "productivity", "todo", "notes", "email",
                    "calendar", "assistant", "life", "schedule"],
    "finance":     ["trading", "stock", "quant", "financial", "invest",
                    "backtest", "alpha", "portfolio", "crypto", "market"],
    "social":      ["social", "twitter", "reddit", "weibo", "content creator",
                    "influencer", "community", "forum"],
    "creative":    ["image", "video", "audio", "music", "art", "design",
                    "stable diffusion", "midjourney", "generate", "creative"],
    "multimodal":  ["multimodal", "vision", "ocr", "speech", "tts", "asr",
                    "audio", "voice", "image understanding"],
    "hardware":    ["robot", "drone", "iot", "embedded", "esp32", "raspberry",
                    "hardware", "device", "sensor", "physical"],
    "data":        ["data pipeline", "etl", "analytics", "dashboard", "bi",
                    "visualization", "notebook", "sql", "database"],
    "security":    ["security", "pentest", "vulnerability", "malware",
                    "cybersecurity", "exploit", "audit"],
    "education":   ["education", "tutorial", "learn", "course", "teach",
                    "student", "homework", "quiz"],
    "game":        ["game", "gaming", "unity", "unreal", "npc", "rpg",
                    "simulation"],
    "healthcare":  ["health", "hospital", "clinical", "patient", "diagnosis",
                    "therapy", "mental health"],
    "legal":       ["legal", "law", "contract", "compliance", "regulation"],
    "hr":          ["hr", "recruit", "resume", "job", "talent", "hiring"],
    "ecommerce":   ["ecommerce", "shop", "product", "price", "merchant", "review"],
}


def _classify_domains(repo_name: str, desc: str, topics: list[str]) -> list[str]:
    """基于仓库名、描述、topics 匹配领域标签，返回 list[domain_id]。"""
    text = " ".join([
        repo_name.lower(),
        (desc or "").lower(),
        " ".join(t.lower() for t in topics),
    ])
    matched: list[str] = []
    for domain_id, kws in DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in kws):
            matched.append(domain_id)
    return matched


def _parse_community_flags(items_raw) -> dict:
    """从 items 字段解析社区平台标志。"""
    items = items_raw if isinstance(items_raw, list) else []
    if not items and isinstance(items_raw, str):
        try:
            items = json.loads(items_raw)
        except Exception:
            items = []

    flags = {
        "has_wechat": 0,
        "has_discord": 0,
        "has_qq": 0,
        "has_telegram": 0,
        "has_slack": 0,
    }
    count = 0
    seen_platforms: set[str] = set()
    for item in (items or []):
        if not isinstance(item, dict):
            continue
        platform = (item.get("platform") or "").lower()
        seen_platforms.add(platform)
        if platform == "wechat":
            flags["has_wechat"] = 1
        elif platform == "discord":
            flags["has_discord"] = 1
        elif platform == "qq":
            flags["has_qq"] = 1
        elif platform == "telegram":
            flags["has_telegram"] = 1
        elif platform == "slack":
            flags["has_slack"] = 1
    count = sum(1 for v in flags.values() if v)
    return {**flags, "community_count": count}


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def run_full_import(verbose: bool = True) -> int:
    """
    全量导入（幂等）。
    - 若 repo 已存在：更新 stars / community 数据
    - 若 repo 不存在：插入并分配新 AR-XXXXX 编号
    返回本次新增数量。
    """
    if verbose:
        print("  [full_import] 加载 repos.json ...")
    with open(REPOS_JSON, encoding="utf-8") as f:
        repos_raw: list[dict] = json.load(f)

    if verbose:
        print(f"  [full_import] repos.json 共 {len(repos_raw):,} 条")
        print("  [full_import] 加载 results.jsonl 社区数据 ...")

    # 构建社区数据索引: full_name → {flags, summary_cn}
    community_index: dict[str, dict] = {}
    try:
        with open(RESULTS_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                fn = d.get("full_name") or d.get("name", "")
                if not fn:
                    continue
                flags = _parse_community_flags(d.get("items") or d.get("communities"))
                community_index[fn] = {
                    **flags,
                    "summary_cn": (d.get("summary_cn") or "")[:500],
                }
    except FileNotFoundError:
        if verbose:
            print("  [full_import] ⚠ results.jsonl 不存在，跳过社区数据")

    if verbose:
        print(f"  [full_import] 社区索引 {len(community_index):,} 条")

    conn = get_conn()
    _ensure_table(conn)

    # 获取当前最大编号
    row = conn.execute("SELECT MAX(CAST(SUBSTR(ar_id,4) AS INTEGER)) FROM full_project_registry").fetchone()
    next_num = (row[0] or 0) + 1

    # 获取已存在的 repo 集合
    existing = set(
        r[0] for r in conn.execute("SELECT repo FROM full_project_registry").fetchall()
    )

    new_count = 0
    updated_count = 0
    batch: list[tuple] = []

    for repo in repos_raw:
        full_name: str = repo.get("full_name") or repo.get("name") or ""
        if not full_name or "/" not in full_name:
            continue

        stars   = int(repo.get("stargazers_count") or repo.get("stars") or 0)
        forks   = int(repo.get("forks_count") or repo.get("forks") or 0)
        desc    = (repo.get("description") or "")[:400]
        lang    = repo.get("language") or ""
        topics  = repo.get("topics") or []
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except Exception:
                topics = []
        homepage  = repo.get("homepage") or ""
        gh_created = repo.get("created_at") or ""
        name_only = full_name.split("/")[-1]

        domain_tags = _classify_domains(full_name, desc, topics)
        comm = community_index.get(full_name, {})
        summary_cn = comm.get("summary_cn", "")

        if full_name not in existing:
            ar_id = f"AR-{next_num:05d}"
            next_num += 1
            new_count += 1
            batch.append((
                ar_id, full_name, name_only, stars, forks, desc, lang,
                json.dumps(topics, ensure_ascii=False),
                homepage, gh_created,
                json.dumps(domain_tags, ensure_ascii=False),
                comm.get("has_wechat", 0),
                comm.get("has_discord", 0),
                comm.get("has_qq", 0),
                comm.get("has_telegram", 0),
                comm.get("has_slack", 0),
                comm.get("community_count", 0),
                summary_cn,
                "2026-W19",
            ))
        else:
            # 更新现有条目
            updated_count += 1
            comm_part = ""
            params = [
                stars, forks, desc, lang,
                json.dumps(topics, ensure_ascii=False),
                json.dumps(domain_tags, ensure_ascii=False),
                comm.get("has_wechat", 0),
                comm.get("has_discord", 0),
                comm.get("has_qq", 0),
                comm.get("has_telegram", 0),
                comm.get("has_slack", 0),
                comm.get("community_count", 0),
                summary_cn or None,
                full_name,
            ]
            conn.execute("""
                UPDATE full_project_registry
                SET stars=?, forks=?, description=?, language=?,
                    topics=?, domain_tags=?,
                    has_wechat=?, has_discord=?, has_qq=?,
                    has_telegram=?, has_slack=?, community_count=?,
                    summary_cn=COALESCE(NULLIF(?,''), summary_cn),
                    updated_at=datetime('now')
                WHERE repo=?
            """, params)

        # 批量写入
        if len(batch) >= 500:
            _batch_insert(conn, batch)
            batch = []
            if verbose:
                print(f"  [full_import] 已导入 {new_count:,} 条新项目...", end="\r")

    if batch:
        _batch_insert(conn, batch)

    conn.commit()
    conn.close()

    if verbose:
        print(f"\n  [full_import] 完成：新增 {new_count:,} 条，更新 {updated_count:,} 条")
    return new_count


def _ensure_table(conn: sqlite3.Connection) -> None:
    """确保 full_project_registry 表存在（兼容 init_db 已建表的情况）。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS full_project_registry (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ar_id           TEXT NOT NULL UNIQUE,
            repo            TEXT NOT NULL UNIQUE,
            name            TEXT,
            stars           INTEGER DEFAULT 0,
            forks           INTEGER DEFAULT 0,
            description     TEXT,
            language        TEXT,
            topics          TEXT DEFAULT '[]',
            homepage        TEXT,
            gh_created      TEXT,
            domain_tags     TEXT DEFAULT '[]',
            has_wechat      INTEGER DEFAULT 0,
            has_discord     INTEGER DEFAULT 0,
            has_qq          INTEGER DEFAULT 0,
            has_telegram    INTEGER DEFAULT 0,
            has_slack       INTEGER DEFAULT 0,
            community_count INTEGER DEFAULT 0,
            summary_cn      TEXT,
            first_seen      TEXT,
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fpr_stars ON full_project_registry(stars DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fpr_domain ON full_project_registry(domain_tags)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fpr_wechat ON full_project_registry(has_wechat)")
    conn.commit()


def _batch_insert(conn: sqlite3.Connection, batch: list[tuple]) -> None:
    conn.executemany("""
        INSERT OR IGNORE INTO full_project_registry
        (ar_id, repo, name, stars, forks, description, language,
         topics, homepage, gh_created, domain_tags,
         has_wechat, has_discord, has_qq, has_telegram, has_slack,
         community_count, summary_cn, first_seen)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, batch)
    conn.commit()
