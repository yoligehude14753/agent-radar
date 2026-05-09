"""读取本地微信群聊 SQLite — 统计本周各领域消息数"""
import sqlite3
from src.shared.config import SOURCE_DB, WECHAT_DOMAIN_KWS


def count_messages_this_week(since_date: str) -> dict[str, int]:
    """
    统计 since_date 之后各领域的群聊消息数。
    返回 {domain_id: count}
    """
    if not SOURCE_DB.exists():
        return {d: 0 for d in WECHAT_DOMAIN_KWS}

    conn = sqlite3.connect(SOURCE_DB)
    results: dict[str, int] = {}

    for domain, kws in WECHAT_DOMAIN_KWS.items():
        conditions = " OR ".join(f"content LIKE '%{k}%'" for k in kws)
        try:
            row = conn.execute(f"""
                SELECT COUNT(*) FROM episodic_events
                WHERE source = 'wechat'
                  AND content NOT LIKE '%<?xml%'
                  AND content NOT LIKE '%<img%'
                  AND length(content) > 40
                  AND ({conditions})
            """).fetchone()
            results[domain] = row[0] if row else 0
        except Exception:
            results[domain] = 0

    conn.close()
    return results
