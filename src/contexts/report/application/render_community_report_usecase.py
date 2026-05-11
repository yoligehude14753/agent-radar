"""
render_community_report_usecase.py
====================================
生成社区群聊报告。

数据来源：full_project_registry（唯一权威数据源）
  - 保证 AR 编号与 /all/ 页面完全一致
  - community_items 含压缩后的 QR 码 img_data_url

输出（均上传 GCS）：
  community.html        — HTML shell（17KB），fetch() 异步加载数据
  community_data.json   — REPOS 数据含 AR 编号 + QR 图（~50MB）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from src.shared.db import get_conn
from src.shared.config import OUTPUT_DIR

COMMUNITY_FINDER_DIR = Path(
    "/Users/yoligehude/Desktop/all/openall/projects/github-community-finder"
)
COMMUNITY_HTML  = OUTPUT_DIR / "community.html"
COMMUNITY_DATA  = OUTPUT_DIR / "community_data.json"
GCS_BASE = "https://storage.googleapis.com/yoli-agent-radar"

if str(COMMUNITY_FINDER_DIR) not in sys.path:
    sys.path.insert(0, str(COMMUNITY_FINDER_DIR))


# 平台展示配置
_PLATFORM_META = {
    "telegram": {"color": "#26A5E4", "icon": "✈️",  "label": "Telegram"},
    "discord":  {"color": "#5865F2", "icon": "💬",  "label": "Discord"},
    "wechat":   {"color": "#07C160", "icon": "💚",  "label": "微信"},
    "qq":       {"color": "#14B2E2", "icon": "🐧",  "label": "QQ"},
    "slack":    {"color": "#4A154B", "icon": "🟣",  "label": "Slack"},
    "feishu":   {"color": "#386AF0", "icon": "🪁",  "label": "飞书"},
    "matrix":   {"color": "#555",    "icon": "🔳",  "label": "Matrix"},
    "gitter":   {"color": "#ED1965", "icon": "💬",  "label": "Gitter"},
    "reddit":   {"color": "#FF4500", "icon": "🤖",  "label": "Reddit"},
    "facebook": {"color": "#1877F2", "icon": "📘",  "label": "Facebook"},
    "forum":    {"color": "#888888", "icon": "🏛️",  "label": "论坛"},
}
_JOINABLE = {"telegram","discord","wechat","qq","slack","feishu","matrix","gitter",
             "reddit","facebook","forum"}


def _compress_qr(img_data_url: str) -> str:
    """压缩 QR 码图片到 200px，降低 community_data.json 体积。"""
    try:
        import base64, io
        from PIL import Image
        header, b64 = img_data_url.split(",", 1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        img.thumbnail((200, 200), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=72, optimize=True)
        compressed = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{compressed}"
    except Exception:
        return img_data_url


def render_community_report(verbose: bool = True) -> Path:
    """从 full_project_registry 读取，生成 community.html + community_data.json。"""
    conn = get_conn()

    # 读取有社区信息的项目（与 /all/ 同一数据源，保证 AR 编号一致）
    rows = conn.execute("""
        SELECT ar_id, repo, name, stars, forks, language,
               description, summary_cn, community_items, gh_created
        FROM full_project_registry
        WHERE community_count > 0
        ORDER BY stars DESC
    """).fetchall()
    conn.close()

    if verbose:
        print(f"  [community] 从 DB 读取 {len(rows):,} 个有社区信息的项目")

    repos_data: list[dict] = []
    stats: dict[str, int] = {}
    total_items = 0

    for r in rows:
        items_raw = json.loads(r["community_items"] or "[]")
        if not isinstance(items_raw, list):
            items_raw = []

        # 提取可加入的社区条目
        platforms_seen: list[str] = []
        clean_items: list[dict] = []
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            plat = (item.get("platform") or "").lower()
            if plat not in _JOINABLE:
                continue
            if not item.get("is_valid", True):
                continue

            # 只取有实质内容的条目
            has_img = bool(item.get("img_data_url") or item.get("qr_data_url"))
            has_text = bool(item.get("value") or item.get("note"))
            if not has_img and not has_text:
                continue

            # 压缩 QR 图片
            img_url = item.get("img_data_url") or ""
            if img_url and img_url.startswith("data:image"):
                img_url = _compress_qr(img_url)

            clean_item = {
                "platform": plat,
                "delivery": item.get("delivery") or "",
                "url":  item.get("value") or "",
                "note": (item.get("note") or "")[:200],
                "members": item.get("member_count") or 0,
                "verified": bool(item.get("verified")),
                "img": img_url,
                "qr":  item.get("qr_data_url") or "",
            }
            # 去重
            dedup_key = f"{plat}:{clean_item['url']}"
            if dedup_key not in [f"{ci['platform']}:{ci['url']}" for ci in clean_items]:
                clean_items.append(clean_item)
                if plat not in platforms_seen:
                    platforms_seen.append(plat)
                    stats[plat] = stats.get(plat, 0) + 1

        if not clean_items:
            continue

        total_items += len(clean_items)
        repos_data.append({
            "ar_id":    r["ar_id"],           # AR-XXXXX，与 /all/ 完全一致
            "name":     r["repo"],
            "url":      f"https://github.com/{r['repo']}",
            "stars":    r["stars"],
            "lang":     r["language"] or "",
            "desc":     (r["summary_cn"] or r["description"] or "")[:300],
            "platforms": platforms_seen,
            "items":    clean_items,
        })

    total_repos = len(repos_data)
    if verbose:
        print(f"  [community] 有效社区项目：{total_repos:,}，群聊入口：{total_items:,}")

    # 统计 chips
    stats_sorted = sorted(stats.items(), key=lambda x: -x[1])
    stats_html = "".join(
        f'<span class="stat-chip" style="--c:{_PLATFORM_META.get(k,{}).get("color","#888")}">'
        f'{_PLATFORM_META.get(k,{}).get("icon","🔗")} <strong>{v}</strong>'
        f' {_PLATFORM_META.get(k,{}).get("label",k)}</span>'
        for k, v in stats_sorted
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 写数据文件
    COMMUNITY_DATA.write_text(
        json.dumps(repos_data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )

    # 写 HTML shell
    platform_meta_json = json.dumps(_PLATFORM_META, ensure_ascii=False)
    COMMUNITY_HTML.write_text(
        _build_html(total_repos, total_items, stats_html, platform_meta_json, GCS_BASE),
        encoding="utf-8"
    )

    if verbose:
        data_mb = COMMUNITY_DATA.stat().st_size / 1024 / 1024
        html_kb = COMMUNITY_HTML.stat().st_size / 1024
        print(f"  [community] community.html {html_kb:.0f} KB，community_data.json {data_mb:.1f} MB")

    return COMMUNITY_HTML


def _build_html(total_repos, total_items, stats_html, platform_meta_json, gcs_base):
    from datetime import date
    generated = date.today().strftime("%Y-%m-%d")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GitHub 开源社区雷达 · 群聊入口</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:14px}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}}
a{{color:#58a6ff;text-decoration:none}}a:hover{{text-decoration:underline}}
strong{{font-weight:600}}
.page{{max-width:1200px;margin:0 auto;padding:16px}}
.header{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px 24px;margin-bottom:16px}}
.header-title{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.header-title h1{{font-size:1.2rem;font-weight:700}}
.header-sub{{font-size:.8rem;color:#8b949e;margin-bottom:12px}}
.stat-chips{{display:flex;flex-wrap:wrap;gap:6px}}
.stat-chip{{background:color-mix(in srgb,var(--c,#888) 15%,transparent);
  border:1px solid color-mix(in srgb,var(--c,#888) 35%,transparent);
  color:var(--c,#888);border-radius:20px;padding:3px 12px;font-size:.78rem}}
.controls{{background:#161b22;border:1px solid #30363d;border-radius:12px;
  padding:14px 20px;margin-bottom:12px;display:flex;flex-direction:column;gap:10px}}
.ctrl-row{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.ctrl-label{{font-size:.8rem;color:#8b949e;white-space:nowrap;min-width:50px}}
.search-input{{flex:1;min-width:200px;background:#0d1117;border:1px solid #30363d;
  border-radius:8px;padding:7px 12px;color:#e6edf3;font-size:.85rem;outline:none}}
.search-input:focus{{border-color:#58a6ff}}
.search-input::placeholder{{color:#8b949e}}
.filter-chips{{display:flex;flex-wrap:wrap;gap:5px}}
.chip{{background:transparent;border:1px solid #30363d;border-radius:20px;
  padding:3px 12px;color:#8b949e;font-size:.78rem;cursor:pointer;transition:all .15s}}
.chip:hover{{border-color:#58a6ff;color:#58a6ff}}
.chip.active{{background:#58a6ff;border-color:#58a6ff;color:#fff;font-weight:600}}
.plat-chip.active{{background:color-mix(in srgb,var(--pc,#58a6ff) 20%,transparent);
  border-color:var(--pc,#58a6ff);color:var(--pc,#58a6ff)}}
.ctrl-select{{background:#0d1117;border:1px solid #30363d;border-radius:8px;
  padding:6px 10px;color:#e6edf3;font-size:.82rem;cursor:pointer}}
.result-bar{{display:flex;justify-content:space-between;align-items:center;
  padding:8px 4px;font-size:.82rem;color:#8b949e;margin-bottom:6px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;
  padding:16px 20px;margin-bottom:10px}}
.card:hover{{border-color:#444c56}}
.card-header{{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:6px}}
.ar-id{{font-size:.7rem;color:#8b949e;font-family:monospace;background:#21262d;
  border:1px solid #30363d;padding:1px 7px;border-radius:4px}}
.card-name{{font-size:1rem;font-weight:600;color:#58a6ff}}
.badge{{background:#21262d;border:1px solid #30363d;border-radius:4px;
  padding:2px 7px;font-size:.72rem;color:#8b949e}}
.card-desc{{font-size:.82rem;color:#8b949e;margin-bottom:10px;line-height:1.5}}
.items{{display:flex;flex-direction:column;gap:6px;margin-top:8px}}
.item{{display:flex;align-items:flex-start;gap:10px;background:#0d1117;
  border:1px solid #30363d;border-radius:8px;padding:10px 14px}}
.item-plat{{display:flex;align-items:center;gap:5px;font-size:.78rem;font-weight:600;
  min-width:88px;color:var(--pc,#8b949e)}}
.item-content{{flex:1;min-width:0}}
.item-link{{font-size:.82rem;word-break:break-all}}
.item-note{{font-size:.78rem;color:#8b949e;margin-top:3px}}
.item-meta{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:4px;font-size:.72rem}}
.qr-wrap{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.qr-img{{max-width:160px;max-height:160px;border-radius:6px;border:1px solid #30363d}}
.pagination{{display:flex;align-items:center;justify-content:center;gap:6px;
  padding:20px 0;flex-wrap:wrap}}
.pg-btn{{background:#161b22;border:1px solid #30363d;border-radius:6px;
  padding:5px 14px;color:#e6edf3;cursor:pointer;font-size:.82rem;transition:all .15s}}
.pg-btn:hover{{border-color:#58a6ff;color:#58a6ff}}
.pg-btn:disabled{{opacity:.4;cursor:default}}
.pg-info{{font-size:.82rem;color:#8b949e}}
.pg-jump{{width:56px;background:#0d1117;border:1px solid #30363d;border-radius:6px;
  padding:4px 8px;color:#e6edf3;font-size:.82rem;text-align:center}}
.empty{{text-align:center;padding:40px;color:#8b949e}}
.loading-wrap{{text-align:center;padding:60px;color:#8b949e}}
.loading-bar{{width:200px;height:4px;background:#30363d;border-radius:2px;margin:12px auto;overflow:hidden}}
.loading-bar-inner{{height:100%;background:#58a6ff;animation:la 1.4s ease-in-out infinite}}
@keyframes la{{0%{{width:0%;transform:translateX(0)}}50%{{width:60%}}100%{{width:0%;transform:translateX(220px)}}}}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div class="header-title">
      <span style="font-size:1.4rem">🛰️</span>
      <h1>GitHub 开源社区雷达 <small style="font-size:.7em;color:#8b949e;font-weight:400">群聊入口专版</small></h1>
    </div>
    <div class="header-sub">
      仅收录可加入的群聊（Telegram / Discord / 微信 / QQ / Slack / 飞书 / Matrix / Gitter）
      &nbsp;·&nbsp; 更新：{generated}
      &nbsp;·&nbsp; <strong>{total_repos:,}</strong> 个项目，共 <strong>{total_items:,}</strong> 个入口
      &nbsp;·&nbsp; 编号与
      <a href="https://yoliyoli.uk/agent-radar/all/">全量库（AR-XXXXX）</a>完全对齐
    </div>
    <div class="stat-chips">{stats_html}</div>
  </div>

  <div class="controls">
    <div class="ctrl-row">
      <span class="ctrl-label">🔍 搜索</span>
      <input class="search-input" id="search" type="text"
        placeholder="AR 编号 / 仓库名 / 描述关键词…" oninput="onFilter()">
    </div>
    <div class="ctrl-row">
      <span class="ctrl-label">📡 平台</span>
      <div class="filter-chips" id="plat-chips">
        <button class="chip active" data-plat="" onclick="setPlatform(this)">全部</button>
      </div>
    </div>
    <div class="ctrl-row">
      <span class="ctrl-label">⭐ Stars</span>
      <div class="filter-chips">
        <button class="chip active" data-star="" onclick="setStar(this)">不限</button>
        <button class="chip" data-star="100" onclick="setStar(this)">100-999</button>
        <button class="chip" data-star="1000" onclick="setStar(this)">1k-4.9k</button>
        <button class="chip" data-star="5000" onclick="setStar(this)">5k-19.9k</button>
        <button class="chip" data-star="20000" onclick="setStar(this)">20k+</button>
      </div>
      <span class="ctrl-label" style="margin-left:12px">排序</span>
      <select class="ctrl-select" id="sort-sel" onchange="onFilter()">
        <option value="stars">⭐ 星数最多</option>
        <option value="items">入口数最多</option>
      </select>
    </div>
  </div>

  <div class="result-bar">
    <div>共 <strong id="result-count">-</strong> 个项目</div>
    <div id="page-info-top" style="color:#8b949e;font-size:.78rem"></div>
  </div>
  <div id="cards-container">
    <div class="loading-wrap">正在加载…<div class="loading-bar"><div class="loading-bar-inner"></div></div></div>
  </div>
  <div class="pagination">
    <button class="pg-btn" id="pg-prev" onclick="goPage(currentPage-1)">← 上一页</button>
    <span class="pg-info" id="pg-info"></span>
    <input class="pg-jump" id="pg-jump" type="number" min="1" placeholder="页码"
      onkeydown="if(event.key==='Enter')goPage(+this.value-1)">
    <button class="pg-btn" id="pg-next" onclick="goPage(currentPage+1)">下一页 →</button>
  </div>
</div>

<script>
const PLATFORM_META = {platform_meta_json};
const PAGE_SIZE = 50;
let REPOS = [], filtered = [], currentPage = 0, activePlat = '', activeStar = '';

(async function load() {{
  try {{
    const r = await fetch('{gcs_base}/community_data.json');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    REPOS = await r.json();
    initPlatChips();
    onFilter();
  }} catch(e) {{
    document.getElementById('cards-container').innerHTML =
      `<div class="empty">❌ 加载失败：${{e.message}}</div>`;
  }}
}})();

function initPlatChips() {{
  const plats = {{}};
  REPOS.forEach(r => (r.platforms||[]).forEach(p => plats[p]=(plats[p]||0)+1));
  const c = document.getElementById('plat-chips');
  ['telegram','discord','wechat','qq','slack','feishu','matrix','gitter','reddit','facebook','forum']
    .filter(p => plats[p]).forEach(p => {{
      const m = PLATFORM_META[p]||{{icon:'🔗',label:p,color:'#888'}};
      const b = document.createElement('button');
      b.className='chip plat-chip'; b.dataset.plat=p;
      b.style.setProperty('--pc',m.color);
      b.innerHTML=`${{m.icon}} ${{m.label}} <span style="opacity:.6">(${{plats[p]}})</span>`;
      b.onclick=()=>setPlatform(b); c.appendChild(b);
    }});
}}

function onFilter() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const sort = document.getElementById('sort-sel').value;
  const smin = activeStar ? +activeStar : 0;
  const smax = activeStar ? ({{'100':999,'1000':4999,'5000':19999,'20000':Infinity}})[activeStar]??Infinity : Infinity;
  filtered = REPOS.filter(r => {{
    if (activePlat && !(r.platforms||[]).includes(activePlat)) return false;
    if (r.stars<smin||r.stars>smax) return false;
    if (q && !(r.ar_id||'').toLowerCase().includes(q)
           && !r.name.toLowerCase().includes(q)
           && !(r.desc||'').toLowerCase().includes(q)) return false;
    return true;
  }});
  if (sort==='stars') filtered.sort((a,b)=>b.stars-a.stars);
  else filtered.sort((a,b)=>b.items.length-a.items.length);
  currentPage=0; renderPage();
}}

function setPlatform(btn) {{
  document.querySelectorAll('.plat-chip,.chip[data-plat]').forEach(c=>c.classList.remove('active'));
  btn.classList.add('active'); activePlat=btn.dataset.plat||''; onFilter();
}}
function setStar(btn) {{
  document.querySelectorAll('[data-star]').forEach(c=>c.classList.remove('active'));
  btn.classList.add('active'); activeStar=btn.dataset.star||''; onFilter();
}}
function goPage(p) {{
  const t=Math.ceil(filtered.length/PAGE_SIZE);
  if(p<0||p>=t) return;
  currentPage=p; renderPage(); window.scrollTo({{top:0,behavior:'smooth'}});
}}

function renderPage() {{
  const total=filtered.length, tpg=Math.max(1,Math.ceil(total/PAGE_SIZE));
  const start=currentPage*PAGE_SIZE, sl=filtered.slice(start,start+PAGE_SIZE);
  document.getElementById('result-count').textContent=total.toLocaleString();
  document.getElementById('pg-info').textContent=`第 ${{currentPage+1}}/${{tpg}} 页`;
  document.getElementById('page-info-top').textContent=
    total>0?`第 ${{start+1}}-${{Math.min(start+PAGE_SIZE,total)}} 条`:'';
  document.getElementById('pg-prev').disabled=currentPage===0;
  document.getElementById('pg-next').disabled=currentPage>=tpg-1;
  const c=document.getElementById('cards-container');
  c.innerHTML=total===0?'<div class="empty">😶 无匹配项目</div>':sl.map(renderCard).join('');
}}

function renderCard(r) {{
  const stars=r.stars>=1000?(r.stars/1000).toFixed(1)+'k':String(r.stars);
  const plats=(r.platforms||[]).map(p=>{{
    const m=PLATFORM_META[p]||{{icon:'🔗',label:p,color:'#888'}};
    return `<span class="badge" style="color:${{m.color}}">${{m.icon}} ${{m.label}}</span>`;
  }}).join('');
  const dispItems=activePlat?(r.items||[]).filter(i=>i.platform===activePlat):(r.items||[]);
  const allUrl=`https://yoliyoli.uk/agent-radar/all/`;
  return `<div class="card">
    <div class="card-header">
      <a class="ar-id" href="${{allUrl}}" title="在全量库中查看 ${{r.ar_id}}">${{r.ar_id}}</a>
      <a class="card-name" href="${{esc(r.url)}}" target="_blank" rel="noopener">${{esc(r.name)}}</a>
      <span class="badge">⭐ ${{stars}}</span>
      ${{r.lang?`<span class="badge">${{esc(r.lang)}}</span>`:''}}
      ${{plats}}
    </div>
    ${{r.desc?`<div class="card-desc">${{esc(r.desc)}}</div>`:''}}
    <div class="items">${{dispItems.map(renderItem).join('')}}</div>
  </div>`;
}}

function renderItem(i) {{
  const m=PLATFORM_META[i.platform]||{{icon:'🔗',label:i.platform,color:'#888'}};
  let content='';
  if(i.img) {{
    content=`<div class="qr-wrap">
      <img class="qr-img" src="${{i.img}}" alt="QR" loading="lazy">
      ${{i.note?`<div style="font-size:.7rem;color:#8b949e;max-width:160px;text-align:center">${{esc(i.note)}}</div>`:''}}
    </div>`;
  }} else if(i.qr) {{
    content=`<div class="qr-wrap"><img class="qr-img" src="${{i.qr}}" alt="QR" loading="lazy"></div>`;
  }} else if(i.url) {{
    content=`<div class="item-link"><a href="${{esc(i.url)}}" target="_blank" rel="noopener">${{esc(shortUrl(i.url))}}</a></div>
    ${{i.note?`<div class="item-note">${{esc(i.note)}}</div>`:''}}`;
  }} else if(i.note) {{
    content=`<div class="item-note">${{esc(i.note)}}</div>`;
  }}
  const meta=[];
  if(i.members) meta.push(`👥 ${{i.members}} 人`);
  if(i.verified) meta.push('✅ 已验证');
  return `<div class="item">
    <div class="item-plat" style="--pc:${{m.color}}">${{m.icon}} ${{m.label}}</div>
    <div class="item-content">${{content}}${{meta.length?`<div class="item-meta">${{meta.join(' · ')}}</div>`:''}}</div>
  </div>`;
}}

function esc(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
function shortUrl(u){{
  try{{const x=new URL(u);let s=x.hostname.replace(/^www\./,'')+x.pathname;return s.length>60?s.slice(0,57)+'…':s;}}
  catch{{return(u||'').slice(0,60);}}
}}
</script>
</body>
</html>"""
