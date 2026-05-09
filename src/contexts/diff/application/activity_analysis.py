"""
用 LLM 分析 GitHub 周活动：
  - 本周主要进展（commits 视角）
  - 用户反馈热点（issues 视角）
  - 开发重心（PRs 视角）
  - 综合判断（一句话）
"""
from __future__ import annotations
import json
import os
import requests


def _call_llm(prompt: str) -> str:
    """调用 OpenAI 兼容接口（支持自定义 base URL）"""
    from dotenv import load_dotenv
    from pathlib import Path
    # parents: activity_analysis.py → diff/application → diff → contexts → src → agent-radar
    load_dotenv(Path(__file__).resolve().parents[4] / ".env")

    api_key  = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    if not api_key:
        return ""

    return _call_openai(prompt, api_key, base_url)


def _call_openai(prompt: str, api_key: str, base_url: str = "https://api.openai.com/v1") -> str:
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 600, "temperature": 0.3},
            timeout=30,
        )
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


def _call_anthropic(prompt: str) -> str:
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json={"model": "claude-haiku-20240307",
                  "max_tokens": 600,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        return r.json()["content"][0]["text"].strip()
    except Exception:
        return ""


def _build_prompt(repo: str, issue_titles: list[str],
                  pr_titles: list[str], commit_msgs: list[str]) -> str:
    def fmt(lst, label):
        if not lst:
            return f"{label}：无"
        return f"{label}（{len(lst)} 条）：\n" + "\n".join(f"  - {t}" for t in lst[:20])

    return f"""你是一名开源技术分析师。以下是 GitHub 项目 **{repo}** 本周（过去7天）的活动数据。

{fmt(issue_titles, 'Issues')}

{fmt(pr_titles, 'Pull Requests')}

{fmt(commit_msgs, 'Commits')}

请用中文输出以下分析，格式严格为 JSON（不要 markdown 包裹）：
{{
  "progress":  "本周主要进展（1-2句，从commits视角，说明做了什么）",
  "user_pain": "用户反馈热点（1-2句，从issues视角，归纳用户在反映什么问题或需求）",
  "dev_focus": "开发重心（1句，从PRs视角，说明开发者在重点推进什么）",
  "verdict":   "综合判断（1句话，项目本周整体状态，是活跃推进/用户问题多/平稳维护/等）"
}}

如果某类数据为空，对应字段填"数据不足"。只输出 JSON，不要其他内容。"""


def analyze_repo_activity(
    repo: str,
    issue_titles: list[str],
    pr_titles: list[str],
    commit_msgs: list[str],
) -> dict:
    """
    返回结构：
    {
      "progress":  str,
      "user_pain": str,
      "dev_focus": str,
      "verdict":   str,
    }
    任何失败返回空字符串字段。
    """
    empty = {"progress": "", "user_pain": "", "dev_focus": "", "verdict": ""}

    # 三类都为空则跳过
    if not (issue_titles or pr_titles or commit_msgs):
        return empty

    prompt = _build_prompt(repo, issue_titles, pr_titles, commit_msgs)
    raw = _call_llm(prompt)
    if not raw:
        return empty

    try:
        # 清理可能的多余字符
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        data  = json.loads(raw[start:end])
        return {k: data.get(k, "") for k in empty}
    except Exception:
        return empty
