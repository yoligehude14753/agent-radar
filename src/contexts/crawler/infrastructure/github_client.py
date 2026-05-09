"""GitHub API 客户端 — 获取 repo star 数 + 新项目搜索"""
from __future__ import annotations
import time
import requests
from src.shared.config import GITHUB_HEADERS


_BASE = "https://api.github.com"


def get_repo_stars(repo: str) -> int | None:
    """获取单个 repo 当前 star 数，失败返回 None"""
    try:
        r = requests.get(f"{_BASE}/repos/{repo}", headers=GITHUB_HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get("stargazers_count")
        return None
    except Exception:
        return None


def search_new_repos(keywords: list[str], since_date: str, max_results: int = 20) -> list[dict]:
    """
    用关键词搜索最近创建的项目（since_date 格式：'2026-05-01'）
    返回 [{"full_name", "stars", "description", "created_at"}]
    """
    # 拼接关键词 OR 查询，限制速率（Search API 30 req/min）
    q = " OR ".join(f'"{kw}"' for kw in keywords[:3])  # 最多 3 个词避免查询太宽
    q += f" created:>{since_date}"
    params = {"q": q, "sort": "stars", "order": "desc", "per_page": max_results}
    try:
        time.sleep(2)  # 主动限速，避免触发 rate limit
        r = requests.get(f"{_BASE}/search/repositories", headers=GITHUB_HEADERS,
                         params=params, timeout=15)
        if r.status_code == 200:
            items = r.json().get("items", [])
            return [
                {
                    "full_name":   it["full_name"],
                    "stars":       it["stargazers_count"],
                    "description": it.get("description") or "",
                    "created_at":  it["created_at"][:10],
                }
                for it in items
            ]
        return []
    except Exception:
        return []
