"""
full_import_usecase.py
======================
将 github-community-finder 的产出（repos.json + results.jsonl）导入
full_project_registry 表。

设计原则：
  - 不重新发明轮子：用 github_radar.models.result_from_dict 反序列化
  - 保留完整 community 数据：img_data_url（QR 码）、summary_cn、items
  - repos.json 提供 42k 基础数据；results.jsonl 富化其中 24k
  - 每次运行：新仓库插入，旧仓库更新 stars / community

运行时机：
  - 首次：完整导入
  - 每周：find_communities.py 更新 results.jsonl 后调用本函数做增量导入
"""
from __future__ import annotations

import json
import sys
import sqlite3
from pathlib import Path

from src.shared.db import get_conn

# ─── 数据源路径（github-community-finder 输出目录）────────────────────────────
COMMUNITY_FINDER_DIR = Path(
    "/Users/yoligehude/Desktop/all/openall/projects/github-community-finder"
)
REPOS_JSON    = COMMUNITY_FINDER_DIR / "report_full.html.cache" / "repos.json"
RESULTS_JSONL = COMMUNITY_FINDER_DIR / "report_full.html.cache" / "results.jsonl"

# 将 github-community-finder 加入 sys.path 以使用其 models
if str(COMMUNITY_FINDER_DIR) not in sys.path:
    sys.path.insert(0, str(COMMUNITY_FINDER_DIR))

# ─── 领域关键词（自动打标签）────────────────────────────────────────────────

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
    "game":        ["game", "gaming", "unity", "unreal", "npc", "rpg"],
    "healthcare":  ["health", "hospital", "clinical", "patient", "diagnosis",
                    "therapy", "mental health"],
    "legal":       ["legal", "law", "contract", "compliance", "regulation"],
    "hr":          ["hr", "recruit", "resume", "job", "talent", "hiring"],
    "ecommerce":   ["ecommerce", "shop", "product", "price", "merchant", "review"],
}


def _classify_domains(repo_name: str, desc: str, topics: list[str]) -> list[str]:
    text = " ".join([repo_name.lower(), (desc or "").lower(),
                     " ".join(t.lower() for t in topics)])
    return [d for d, kws in DOMAIN_KEYWORDS.items() if any(k in text for k in kws)]


# ─── 从 results.jsonl 构建社区索引（正确使用 result_from_dict）──────────────

def _build_community_index(verbose: bool = False) -> dict[str, dict]:
    """
    读取 results.jsonl，用 result_from_dict 反序列化，
    构建 full_name → community_info 索引。
    保留完整 items（含 img_data_url QR 码）和 summary_cn。
    """
    try:
        from github_radar.models import result_from_dict
        use_model = True
    except ImportError:
        if verbose:
            print("  [full_import] ⚠ github_radar 不可导入，用 JSON 兜底解析")
        use_model = False

    index: dict[str, dict] = {}
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

                # 用 result_from_dict 正确反序列化，保留所有字段
                if use_model:
                    try:
                        r = result_from_dict(d)
                        items = [
                            {
                                "platform":     item.platform,
                                "delivery":     item.delivery,
                                "value":        item.value or "",
                                "is_valid":     item.is_valid,
                                "note":         item.note or "",
                                "member_count": item.member_count,
                                "verified":     item.verified,
                                "img_data_url": item.img_data_url or "",  # QR 码 base64
                                "qr_data_url":  item.qr_data_url or "",
                            }
                            for item in (r.items or [])
                        ]
                        summary_cn = r.summary_cn or ""
                        stars = r.stars
                    except Exception:
                        items = d.get("items") or []
                        summary_cn = d.get("summary_cn") or ""
                        stars = d.get("stars") or 0
                else:
                    items = d.get("items") or []
                    if isinstance(items, str):
                        try:
                            items = json.loads(items)
                        except Exception:
                            items = []
                    summary_cn = d.get("summary_cn") or ""
                    stars = d.get("stars") or 0

                # 提取平台标志位
                platforms = {(item.get("platform") or "").lower() for item in items
                             if isinstance(item, dict)}
                index[fn] = {
                    "summary_cn":      summary_cn[:500],
                    "items":           items,
                    "has_wechat":      int("wechat" in platforms),
                    "has_discord":     int("discord" in platforms),
                    "has_qq":          int("qq" in platforms),
                    "has_telegram":    int("telegram" in platforms),
                    "has_slack":       int("slack" in platforms),
                    "community_count": len(platforms & {"wechat","discord","qq","telegram","slack"}),
                }
    except FileNotFoundError:
        if verbose:
            print(f"  [full_import] ⚠ 找不到 {RESULTS_JSONL}")

    return index


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def run_full_import(verbose: bool = True) -> int:
    """
    全量导入（幂等）。
    - 新仓库：从 repos.json 插入，用 results.jsonl 富化
    - 已存在：更新 stars / summary / community 数据
    返回本次新增数量。
    """
    if verbose:
        print("  [full_import] 加载 repos.json ...")
    with open(REPOS_JSON, encoding="utf-8") as f:
        repos_raw: list[dict] = json.load(f)
    if verbose:
        print(f"  [full_import] repos.json 共 {len(repos_raw):,} 条")
        print("  [full_import] 构建社区索引（用 result_from_dict）...")

    community_index = _build_community_index(verbose=verbose)
    if verbose:
        print(f"  [full_import] 社区索引 {len(community_index):,} 条")

    conn = get_conn()
    _ensure_table(conn)

    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(ar_id,4) AS INTEGER)) FROM full_project_registry"
    ).fetchone()
    next_num = (row[0] or 0) + 1

    existing = set(
        r[0] for r in conn.execute("SELECT repo FROM full_project_registry").fetchall()
    )

    new_count = updated_count = 0
    batch: list[tuple] = []

    for repo in repos_raw:
        full_name: str = repo.get("full_name") or repo.get("name") or ""
        if not full_name or "/" not in full_name:
            continue

        stars   = int(repo.get("stargazers_count") or repo.get("stars") or 0)
        forks   = int(repo.get("forks_count") or repo.get("forks") or 0)
        desc    = (repo.get("description") or "")[:400]
        lang    = repo.get("language") or ""
        topics_raw = repo.get("topics") or []
        if isinstance(topics_raw, str):
            try:
                topics_raw = json.loads(topics_raw)
            except Exception:
                topics_raw = []
        homepage   = repo.get("homepage") or ""
        gh_created = repo.get("created_at") or ""
        name_only  = full_name.split("/")[-1]

        domain_tags = _classify_domains(full_name, desc, topics_raw)
        comm = community_index.get(full_name, {})
        summary_cn  = comm.get("summary_cn", "")
        items_json  = json.dumps(comm.get("items", []), ensure_ascii=False)

        if full_name not in existing:
            ar_id = f"AR-{next_num:05d}"
            next_num += 1
            new_count += 1
            batch.append((
                ar_id, full_name, name_only, stars, forks, desc, lang,
                json.dumps(topics_raw, ensure_ascii=False),
                homepage, gh_created,
                json.dumps(domain_tags, ensure_ascii=False),
                comm.get("has_wechat", 0),
                comm.get("has_discord", 0),
                comm.get("has_qq", 0),
                comm.get("has_telegram", 0),
                comm.get("has_slack", 0),
                comm.get("community_count", 0),
                items_json,
                summary_cn,
                "2026-W19",
            ))
        else:
            updated_count += 1
            conn.execute("""
                UPDATE full_project_registry
                SET stars=?, forks=?, description=?, language=?,
                    topics=?, domain_tags=?,
                    has_wechat=?, has_discord=?, has_qq=?,
                    has_telegram=?, has_slack=?, community_count=?,
                    community_items=?,
                    summary_cn=COALESCE(NULLIF(?,''), summary_cn),
                    updated_at=datetime('now')
                WHERE repo=?
            """, [
                stars, forks, desc, lang,
                json.dumps(topics_raw, ensure_ascii=False),
                json.dumps(domain_tags, ensure_ascii=False),
                comm.get("has_wechat", 0),
                comm.get("has_discord", 0),
                comm.get("has_qq", 0),
                comm.get("has_telegram", 0),
                comm.get("has_slack", 0),
                comm.get("community_count", 0),
                items_json,
                summary_cn or None,
                full_name,
            ])

        if len(batch) >= 500:
            _batch_insert(conn, batch)
            batch = []
            if verbose:
                print(f"  [full_import] 已导入 {new_count:,} 条...", end="\r")

    if batch:
        _batch_insert(conn, batch)

    conn.commit()
    conn.close()

    if verbose:
        print(f"\n  [full_import] 完成：新增 {new_count:,} 条，更新 {updated_count:,} 条")
    return new_count


def _ensure_table(conn: sqlite3.Connection) -> None:
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
            community_items TEXT DEFAULT '[]',  -- 完整 items JSON，含 img_data_url QR 码
            summary_cn      TEXT,
            first_seen      TEXT,
            updated_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    # 兼容旧表：补列
    for col, defn in [
        ("community_items", "TEXT DEFAULT '[]'"),
    ]:
        try:
            conn.execute(f"ALTER TABLE full_project_registry ADD COLUMN {col} {defn}")
        except Exception:
            pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fpr_stars  ON full_project_registry(stars DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fpr_domain ON full_project_registry(domain_tags)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fpr_wechat ON full_project_registry(has_wechat)")
    conn.commit()


def _batch_insert(conn: sqlite3.Connection, batch: list[tuple]) -> None:
    conn.executemany("""
        INSERT OR IGNORE INTO full_project_registry
        (ar_id, repo, name, stars, forks, description, language,
         topics, homepage, gh_created, domain_tags,
         has_wechat, has_discord, has_qq, has_telegram, has_slack,
         community_count, community_items, summary_cn, first_seen)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, batch)
    conn.commit()
