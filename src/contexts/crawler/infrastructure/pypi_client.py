"""PyPI Stats API 客户端"""
from __future__ import annotations
import requests


def get_weekly_downloads(package: str) -> int | None:
    """从 pypistats.org 获取过去一周下载量"""
    try:
        r = requests.get(
            f"https://pypistats.org/api/packages/{package}/recent",
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get("data", {}).get("last_week")
        return None
    except Exception:
        return None
