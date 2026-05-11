"""
render_community_report_usecase.py
====================================
生成社区群聊报告，修复原 render() 因 50MB 内联 JSON 导致浏览器 0 条的 bug。

架构：
  community_data.json   — REPOS 数据（含压缩 QR 图片）上传 GCS
  community.html        — HTML shell，fetch() 异步加载 community_data.json，上传 GCS

两个文件均超过 Cloud Run 32MB 上限，必须通过 GCS 公共存储桶服务：
  https://storage.googleapis.com/yoli-agent-radar/community.html
  https://storage.googleapis.com/yoli-agent-radar/community_data.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from src.shared.config import OUTPUT_DIR

COMMUNITY_FINDER_DIR = Path(
    "/Users/yoligehude/Desktop/all/openall/projects/github-community-finder"
)
RESULTS_JSONL    = COMMUNITY_FINDER_DIR / "report_full.html.cache" / "results.jsonl"
COMMUNITY_HTML   = OUTPUT_DIR / "community.html"
COMMUNITY_DATA   = OUTPUT_DIR / "community_data.json"

GCS_BASE = "https://storage.googleapis.com/yoli-agent-radar"

if str(COMMUNITY_FINDER_DIR) not in sys.path:
    sys.path.insert(0, str(COMMUNITY_FINDER_DIR))


def render_community_report(verbose: bool = True) -> Path:
    """
    生成 community.html + community_data.json（异步加载架构）。
    返回 community.html 路径。
    """
    from github_radar.models import result_from_dict
    from github_radar.report import (
        _extract_joinable_items, _repo_to_json,
        _build_stats_data, _PLATFORM_META,
    )

    if verbose:
        print("  [community] 加载 results.jsonl ...")

    results = []
    try:
        with open(RESULTS_JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    r = result_from_dict(d)
                    results.append(r)
                except Exception:
                    continue
    except FileNotFoundError:
        if verbose:
            print(f"  [community] ⚠ 找不到 {RESULTS_JSONL}，跳过")
        return COMMUNITY_HTML

    if verbose:
        print(f"  [community] 共 {len(results):,} 条，提取社区数据 ...")

    # ── 构建 repos_data（与 report.render() 内部一致）────────────────────────
    repos_data: list[dict] = []
    for repo in results:
        items = _extract_joinable_items(repo)
        if not items:
            continue
        repos_data.append(_repo_to_json(repo, items))
    repos_data.sort(key=lambda r: -r["stars"])

    stats = _build_stats_data(repos_data)
    stats_sorted = sorted(stats.items(), key=lambda x: -x[1])

    total_repos  = len(repos_data)
    total_items  = sum(len(r["items"]) for r in repos_data)

    if verbose:
        print(f"  [community] {total_repos:,} 个有群聊项目，{total_items:,} 个入口")

    # ── 写外部数据文件 ────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data_json_str = json.dumps(repos_data, ensure_ascii=False, separators=(",", ":"))
    COMMUNITY_DATA.write_text(data_json_str, encoding="utf-8")

    platform_meta_json = json.dumps(
        {k: {"color": v["color"], "icon": v["icon"], "label": v["label"]}
         for k, v in _PLATFORM_META.items()},
        ensure_ascii=False
    )

    # 统计 chips HTML
    stats_chips = []
    for k, v in stats_sorted:
        m = _PLATFORM_META.get(k, {"color": "#888", "icon": "🔗", "label": k})
        stats_chips.append(
            f'<span class="stat-chip" style="--c:{m["color"]}">'
            f'{m["icon"]} <strong>{v}</strong> {m["label"]}</span>'
        )
    stats_html = "".join(stats_chips)

    # ── 生成 HTML shell（fetch 异步加载）─────────────────────────────────────
    html = _build_html_shell(
        total_repos=total_repos,
        total_items=total_items,
        stats_html=stats_html,
        platform_meta_json=platform_meta_json,
        gcs_base=GCS_BASE,
    )
    COMMUNITY_HTML.write_text(html, encoding="utf-8")

    if verbose:
        data_mb = COMMUNITY_DATA.stat().st_size / 1024 / 1024
        html_kb = COMMUNITY_HTML.stat().st_size / 1024
        print(f"  [community] community.html {html_kb:.0f} KB，community_data.json {data_mb:.1f} MB")
        print(f"  [community] 访问：{GCS_BASE}/community.html")

    return COMMUNITY_HTML


def _build_html_shell(
    total_repos: int,
    total_items: int,
    stats_html: str,
    platform_meta_json: str,
    gcs_base: str,
) -> str:
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
a{{color:#58a6ff;text-decoration:none}}
a:hover{{text-decoration:underline}}
strong{{font-weight:600}}
.page{{max-width:1200px;margin:0 auto;padding:16px}}
.header{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:20px 24px;margin-bottom:16px}}
.header-title{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.header-title h1{{font-size:1.25rem;font-weight:700}}
.header-sub{{font-size:.8rem;color:#8b949e;margin-bottom:12px}}
.stat-chips{{display:flex;flex-wrap:wrap;gap:6px}}
.stat-chip{{background:color-mix(in srgb,var(--c,#888) 15%,transparent);
  border:1px solid color-mix(in srgb,var(--c,#888) 35%,transparent);
  color:var(--c,#888);border-radius:20px;padding:3px 12px;font-size:.78rem;cursor:pointer;transition:all .15s}}
.stat-chip:hover,.stat-chip.active{{background:color-mix(in srgb,var(--c,#888) 30%,transparent);font-weight:600}}
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
  padding:16px 20px;margin-bottom:10px;transition:border-color .15s}}
.card:hover{{border-color:#444c56}}
.card-title{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px}}
.card-name{{font-size:1rem;font-weight:600;color:#58a6ff}}
.badge{{background:#21262d;border:1px solid #30363d;border-radius:4px;
  padding:2px 7px;font-size:.72rem;color:#8b949e}}
.card-desc{{font-size:.82rem;color:#8b949e;margin-bottom:10px;line-height:1.5}}
.items{{display:flex;flex-direction:column;gap:6px;margin-top:10px}}
.item{{display:flex;align-items:flex-start;gap:10px;background:#0d1117;
  border:1px solid #30363d;border-radius:8px;padding:10px 14px}}
.item-plat{{display:flex;align-items:center;gap:5px;font-size:.78rem;font-weight:600;
  min-width:90px;color:var(--pc,#8b949e)}}
.item-content{{flex:1;min-width:0}}
.item-value{{font-size:.82rem;word-break:break-all}}
.item-note{{font-size:.78rem;color:#8b949e;margin-top:3px}}
.item-meta{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:4px;font-size:.72rem}}
.wechat-qr-wrap{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.wechat-qr{{max-width:160px;max-height:160px;border-radius:6px;border:1px solid #30363d}}
.pagination{{display:flex;align-items:center;justify-content:center;gap:6px;
  padding:20px 0;flex-wrap:wrap}}
.pg-btn{{background:#161b22;border:1px solid #30363d;border-radius:6px;
  padding:5px 14px;color:#e6edf3;cursor:pointer;font-size:.82rem;transition:all .15s}}
.pg-btn:hover{{border-color:#58a6ff;color:#58a6ff}}
.pg-btn:disabled{{opacity:.4;cursor:default}}
.pg-info{{font-size:.82rem;color:#8b949e}}
.pg-jump{{width:56px;background:#0d1117;border:1px solid #30363d;border-radius:6px;
  padding:4px 8px;color:#e6edf3;font-size:.82rem;text-align:center}}
.empty{{text-align:center;padding:40px;color:#8b949e;font-size:.9rem}}
.loading-wrap{{text-align:center;padding:60px;color:#8b949e}}
.loading-bar{{width:200px;height:4px;background:#30363d;border-radius:2px;
  margin:12px auto;overflow:hidden}}
.loading-bar-inner{{height:100%;background:#58a6ff;border-radius:2px;
  animation:la 1.4s ease-in-out infinite}}
@keyframes la{{0%{{width:0%;transform:translateX(0)}}50%{{width:60%}}100%{{width:0%;transform:translateX(220px)}}}}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div class="header-title">
      <span style="font-size:1.5rem">🛰️</span>
      <h1>GitHub 开源社区雷达 <small style="font-size:.7em;color:#8b949e;font-weight:400">群聊入口专版</small></h1>
    </div>
    <div class="header-sub">
      仅收录可加入的群聊（Telegram / Discord / 微信 / QQ / Slack / 飞书 / Matrix / Gitter）
      &nbsp;·&nbsp; 生成：{{}}&nbsp;·&nbsp;
      <strong>{total_repos:,}</strong> 个项目，共 <strong>{total_items:,}</strong> 个入口
      &nbsp;·&nbsp; <a href="/agent-radar/all/" style="color:#8b949e">← 全量项目库</a>
    </div>
    <div class="stat-chips" id="stat-chips">
      {stats_html}
    </div>
  </div>

  <div class="controls">
    <div class="ctrl-row">
      <span class="ctrl-label">🔍 搜索</span>
      <input class="search-input" id="search" type="text"
        placeholder="项目名 / 描述关键词…" oninput="onFilter()">
    </div>
    <div class="ctrl-row">
      <span class="ctrl-label">📡 平台</span>
      <div class="filter-chips" id="plat-chips">
        <button class="chip active" data-plat="" onclick="setPlatform(this)">全部</button>
      </div>
    </div>
    <div class="ctrl-row">
      <span class="ctrl-label">⭐ Stars</span>
      <div class="filter-chips" id="star-chips">
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
    <div class="loading-wrap">
      正在加载社区数据，请稍候…
      <div class="loading-bar"><div class="loading-bar-inner"></div></div>
    </div>
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
// 平台元信息
const PLATFORM_META = {platform_meta_json};
const PAGE_SIZE = 50;

// 状态
let REPOS = [];
let filtered = [];
let currentPage = 0;
let activePlat = '';
let activeStar = '';

// ── 异步加载数据 ──────────────────────────────────────────────────────────────
(async function loadData() {{
  try {{
    const resp = await fetch('community_data.json');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    REPOS = await resp.json();
    // 初始化平台 chips
    initPlatChips();
    // 设置生成时间
    const sub = document.querySelector('.header-sub');
    if (sub) sub.innerHTML = sub.innerHTML.replace('{{}}', new Date().toLocaleDateString('zh-CN'));
    onFilter();
  }} catch(e) {{
    document.getElementById('cards-container').innerHTML =
      `<div class="empty">❌ 加载失败：${{e.message}}<br><small>请刷新页面重试</small></div>`;
  }}
}})();

function initPlatChips() {{
  const plats = {{}};
  REPOS.forEach(r => (r.platforms||[]).forEach(p => plats[p] = (plats[p]||0)+1));
  const container = document.getElementById('plat-chips');
  const order = ['telegram','discord','wechat','qq','slack','feishu','matrix','gitter','reddit','facebook','forum'];
  const sorted = Object.entries(plats).sort((a,b) => {{
    const oa = order.indexOf(a[0]), ob = order.indexOf(b[0]);
    return (oa<0?99:oa) - (ob<0?99:ob);
  }});
  sorted.forEach(([plat, cnt]) => {{
    const m = PLATFORM_META[plat] || {{icon:'🔗', label:plat, color:'#888'}};
    const btn = document.createElement('button');
    btn.className = 'chip plat-chip';
    btn.dataset.plat = plat;
    btn.style.setProperty('--pc', m.color);
    btn.innerHTML = `${{m.icon}} ${{m.label}} <span style="opacity:.6">(${{cnt}})</span>`;
    btn.onclick = function() {{ setPlatform(this); }};
    container.appendChild(btn);
  }});
}}

// ── 筛选逻辑 ──────────────────────────────────────────────────────────────────
function onFilter() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const sort = document.getElementById('sort-sel').value;
  const starMin = activeStar ? +activeStar : 0;
  const starMax = activeStar ? ({{
    '100':999,'1000':4999,'5000':19999,'20000':Infinity
  }})[activeStar] ?? Infinity : Infinity;

  filtered = REPOS.filter(r => {{
    if (activePlat && !(r.platforms||[]).includes(activePlat)) return false;
    if (r.stars < starMin || r.stars > starMax) return false;
    if (q && !r.name.toLowerCase().includes(q) && !(r.desc||'').toLowerCase().includes(q)) return false;
    return true;
  }});
  if (sort === 'stars') filtered.sort((a,b) => b.stars - a.stars);
  else if (sort === 'items') filtered.sort((a,b) => b.items.length - a.items.length);
  currentPage = 0;
  renderPage();
}}

function setPlatform(btn) {{
  document.querySelectorAll('#plat-chips .chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  activePlat = btn.dataset.plat;
  onFilter();
}}
function setStar(btn) {{
  document.querySelectorAll('#star-chips .chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  activeStar = btn.dataset.star || '';
  onFilter();
}}
function goPage(p) {{
  const total = Math.ceil(filtered.length / PAGE_SIZE);
  if (p < 0 || p >= total) return;
  currentPage = p;
  renderPage();
  window.scrollTo({{top:0,behavior:'smooth'}});
}}

// ── 渲染 ─────────────────────────────────────────────────────────────────────
function renderPage() {{
  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = currentPage * PAGE_SIZE;
  const slice = filtered.slice(start, start + PAGE_SIZE);
  document.getElementById('result-count').textContent = total.toLocaleString();
  document.getElementById('pg-info').textContent = `第 ${{currentPage+1}} / ${{totalPages}} 页`;
  document.getElementById('page-info-top').textContent =
    total > 0 ? `第 ${{start+1}}-${{Math.min(start+PAGE_SIZE,total)}} 条` : '';
  document.getElementById('pg-prev').disabled = currentPage === 0;
  document.getElementById('pg-next').disabled = currentPage >= totalPages-1;
  const container = document.getElementById('cards-container');
  if (total === 0) {{
    container.innerHTML = '<div class="empty">😶 没有匹配的项目，换个关键词试试？</div>';
    return;
  }}
  container.innerHTML = slice.map(renderCard).join('');
}}

function renderCard(r) {{
  const m = PLATFORM_META;
  const plats = (r.platforms||[]).map(p => {{
    const pm = m[p]||{{icon:'🔗',label:p,color:'#888'}};
    return `<span class="badge" style="color:${{pm.color}}">${{pm.icon}} ${{pm.label}}</span>`;
  }}).join('');
  const displayItems = activePlat
    ? (r.items||[]).filter(i => i.platform === activePlat)
    : (r.items||[]);
  const itemsHtml = displayItems.map(renderItem).join('');
  const stars = r.stars >= 1000 ? (r.stars/1000).toFixed(1)+'k' : String(r.stars);
  return `<div class="card">
    <div class="card-title">
      <a class="card-name" href="https://github.com/${{esc(r.name)}}" target="_blank" rel="noopener">${{esc(r.name)}}</a>
      <span class="badge">⭐ ${{stars}}</span>
      ${{r.lang ? `<span class="badge">${{esc(r.lang)}}</span>` : ''}}
      ${{plats}}
    </div>
    ${{r.desc ? `<div class="card-desc">${{esc(r.desc)}}</div>` : ''}}
    ${{r.summary ? `<div class="card-desc" style="color:#e6edf3">${{esc(r.summary)}}</div>` : ''}}
    <div class="items">${{itemsHtml}}</div>
  </div>`;
}}

function renderItem(item) {{
  const m = PLATFORM_META[item.platform]||{{icon:'🔗',label:item.platform,color:'#888'}};
  let content = '';
  if (item.img) {{
    content = `<div class="wechat-qr-wrap">
      <img class="wechat-qr" src="${{item.img}}" alt="QR Code" loading="lazy">
      ${{item.note ? `<div style="font-size:.72rem;color:#8b949e;max-width:160px;text-align:center">${{esc(item.note)}}</div>` : ''}}
    </div>`;
  }} else if (item.qr) {{
    content = `<div class="wechat-qr-wrap">
      <img class="wechat-qr" src="${{item.qr}}" alt="QR Code" loading="lazy">
    </div>`;
  }} else if (item.url) {{
    content = `<div class="item-value"><a href="${{esc(item.url)}}" target="_blank" rel="noopener">${{esc(shortUrl(item.url))}}</a></div>
    ${{item.note ? `<div class="item-note">${{esc(item.note)}}</div>` : ''}}`;
  }} else if (item.note) {{
    content = `<div class="item-note">${{esc(item.note)}}</div>`;
  }}
  const meta = [];
  if (item.members) meta.push(`👥 ${{item.members}} 人`);
  if (item.verified) meta.push('✅ 已验证');
  return `<div class="item">
    <div class="item-plat" style="--pc:${{m.color}}">${{m.icon}} ${{m.label}}</div>
    <div class="item-content">
      ${{content}}
      ${{meta.length ? `<div class="item-meta">${{meta.join(' · ')}}</div>` : ''}}
    </div>
  </div>`;
}}

function esc(s) {{ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function shortUrl(url) {{
  try {{
    const u = new URL(url);
    let s = u.hostname.replace(/^www\./,'') + u.pathname;
    return s.length > 60 ? s.slice(0,57) + '…' : s;
  }} catch {{ return (url||'').slice(0,60); }}
}}
</script>
</body>
</html>"""
