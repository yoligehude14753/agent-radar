"""
render_full_projects_usecase.py
================================
从 full_project_registry 导出精简 JSON 数据，
并生成 full_projects.html（前端虚拟滚动）。
"""
from __future__ import annotations

import json
import gzip
import shutil
from pathlib import Path

from src.shared.db import get_conn
from src.shared.config import OUTPUT_DIR, TMPL_DIR


FULL_PROJECTS_HTML  = OUTPUT_DIR / "full_projects.html"
FULL_PROJECTS_DATA  = OUTPUT_DIR / "full_projects_data.json"


def render_full_projects(verbose: bool = True) -> Path:
    """生成 full_projects.html 和配套 data JSON。"""
    conn = get_conn()

    # 统计数字
    total       = conn.execute("SELECT COUNT(*) FROM full_project_registry").fetchone()[0]
    wechat_cnt  = conn.execute("SELECT COUNT(*) FROM full_project_registry WHERE has_wechat=1").fetchone()[0]
    discord_cnt = conn.execute("SELECT COUNT(*) FROM full_project_registry WHERE has_discord=1").fetchone()[0]
    any_comm    = conn.execute("SELECT COUNT(*) FROM full_project_registry WHERE community_count>0").fetchone()[0]

    # 拉全量数据
    rows = conn.execute("""
        SELECT ar_id, repo, name, stars, forks, language,
               description, domain_tags,
               has_wechat, has_discord, has_qq, has_telegram, has_slack,
               community_count, gh_created, summary_cn, community_items
        FROM full_project_registry
        ORDER BY stars DESC
    """).fetchall()
    conn.close()

    # comm_flags: bit0=wechat, bit1=discord, bit2=qq, bit3=telegram, bit4=slack
    records: list[list] = []
    for r in rows:
        comm_flags = (
            (1 if r["has_wechat"]   else 0) |
            (2 if r["has_discord"]  else 0) |
            (4 if r["has_qq"]       else 0) |
            (8 if r["has_telegram"] else 0) |
            (16 if r["has_slack"]   else 0)
        )
        desc    = (r["description"] or "")[:200]
        summary = (r["summary_cn"] or "")[:300]
        yr      = (r["gh_created"] or "")[:4]
        domains = json.loads(r["domain_tags"] or "[]")
        # 社区详情（文字部分，无 base64 图片）
        comm_items = json.loads(r["community_items"] or "[]")
        # 只保留有 value 或 note 的有效条目
        comm_items_clean = [
            {k: v for k, v in item.items() if k in ("platform","delivery","note","value","member_count","verified")}
            for item in comm_items
            if isinstance(item, dict) and (item.get("note") or item.get("value"))
        ]
        records.append([
            r["ar_id"],            # 0  "AR-00001"
            r["repo"],             # 1  "owner/name"
            r["stars"],            # 2  12345
            r["language"] or "",   # 3  "Python"
            desc,                  # 4  description (en)
            domains,               # 5  ["coding","infra"]
            comm_flags,            # 6  bitmask
            yr,                    # 7  "2023"
            summary,               # 8  summary_cn
            comm_items_clean,      # 9  [{platform,delivery,note,value,...}]
        ])

    # 写 JSON 数据文件
    data_payload = {
        "total":       total,
        "wechat_cnt":  wechat_cnt,
        "discord_cnt": discord_cnt,
        "any_comm":    any_comm,
        "records":     records,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(FULL_PROJECTS_DATA, "w", encoding="utf-8") as f:
        json.dump(data_payload, f, ensure_ascii=False, separators=(",", ":"))

    if verbose:
        size_mb = FULL_PROJECTS_DATA.stat().st_size / 1024 / 1024
        print(f"  [render_full] data JSON: {size_mb:.1f} MB, {total:,} 条")

    # 渲染 HTML（模板内联 JS，从相对路径加载 data JSON）
    html = _build_html(total, wechat_cnt, discord_cnt, any_comm)
    with open(FULL_PROJECTS_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    if verbose:
        print(f"  [render_full] 已生成 {FULL_PROJECTS_HTML}")

    return FULL_PROJECTS_HTML


# ─── HTML 生成 ─────────────────────────────────────────────────────────────

def _build_html(total: int, wechat_cnt: int, discord_cnt: int, any_comm: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Radar · 全量项目库</title>
<style>
:root {{
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --purple: #bc8cff; --orange: #d29922;
  --red: #f85149; --pink: #ff7b72;
  --wechat-color: #07c160;
  --discord-color: #5865f2;
  --qq-color: #12b7f5;
  --telegram-color: #2ca5e0;
  --slack-color: #e01e5a;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: var(--font); }}

/* ── 顶部导航 ── */
.nav {{ background: var(--surface); border-bottom: 1px solid var(--border);
  padding: 12px 24px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; position: sticky; top: 0; z-index: 100; }}
.nav-title {{ font-weight: 700; font-size: 1.1rem; color: var(--accent); }}
.nav-back {{ color: var(--muted); text-decoration: none; font-size: 0.85rem; transition: color .15s; }}
.nav-back:hover {{ color: var(--accent); }}
.nav-stats {{ margin-left: auto; display: flex; gap: 16px; }}
.stat-chip {{ background: rgba(88,166,255,.08); border: 1px solid rgba(88,166,255,.2);
  border-radius: 20px; padding: 4px 12px; font-size: 0.78rem; color: var(--accent); }}

/* ── 搜索 + 筛选栏 ── */
.toolbar {{ padding: 16px 24px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center;
  background: var(--surface); border-bottom: 1px solid var(--border); }}
.search-box {{ flex: 1; min-width: 200px; background: var(--bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 12px; color: var(--text); font-size: 0.9rem; outline: none; }}
.search-box:focus {{ border-color: var(--accent); }}
.search-box::placeholder {{ color: var(--muted); }}

.filter-group {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
.filter-label {{ font-size: 0.78rem; color: var(--muted); }}
.filter-btn {{ padding: 5px 12px; border-radius: 20px; border: 1px solid var(--border);
  background: transparent; color: var(--muted); font-size: 0.78rem; cursor: pointer; transition: all .15s; white-space: nowrap; }}
.filter-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
.filter-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }}

.filter-comm-wechat.active  {{ background: var(--wechat-color); border-color: var(--wechat-color); }}
.filter-comm-discord.active {{ background: var(--discord-color); border-color: var(--discord-color); }}
.filter-comm-qq.active      {{ background: var(--qq-color);      border-color: var(--qq-color); }}
.filter-comm-telegram.active {{ background: var(--telegram-color); border-color: var(--telegram-color); }}

.sort-select {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 6px 10px; color: var(--text); font-size: 0.82rem; cursor: pointer; }}
.result-count {{ font-size: 0.82rem; color: var(--muted); margin-left: auto; }}

/* ── 列表容器 ── */
.list-wrap {{
  padding: 0 24px 40px;
}}

.list-header {{
  display: grid;
  grid-template-columns: 90px 1fr 90px 80px 180px 120px;
  gap: 8px;
  padding: 10px 12px;
  font-size: 0.75rem;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 10px;
  position: sticky;
  top: 0;
  background: var(--bg);
  z-index: 90;
}}

#rowList {{ }}

/* 展开详情 */
.row {{ cursor: pointer; }}
.row-detail {{
  display: none;
  grid-column: 1 / -1;
  background: rgba(88,166,255,.04);
  border-left: 3px solid var(--accent);
  border-radius: 0 0 6px 6px;
  padding: 14px 16px;
  margin: -1px 0 4px;
}}
.row-detail.open {{ display: block; }}
.detail-summary {{
  color: var(--text); font-size: 0.82rem; line-height: 1.6; margin-bottom: 10px;
}}
.detail-comm-list {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.detail-comm-item {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 12px;
  font-size: 0.78rem; max-width: 340px;
}}
.detail-comm-platform {{
  font-weight: 700; margin-bottom: 4px;
  display: flex; align-items: center; gap: 6px;
}}
.detail-comm-note {{ color: var(--muted); line-height: 1.5; }}
.detail-comm-link {{ color: var(--accent); word-break: break-all; }}
.detail-comm-meta {{ color: var(--muted); font-size: 0.72rem; margin-top: 4px; }}

/* 分页 */
.pagination {{
  display: flex; align-items: center; justify-content: center;
  gap: 8px; padding: 20px 0; flex-wrap: wrap;
}}
.page-btn {{
  padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); cursor: pointer;
  font-size: 0.82rem; transition: all .15s;
}}
.page-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
.page-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }}
.page-btn:disabled {{ opacity: .4; cursor: default; }}
.page-info {{ font-size: 0.82rem; color: var(--muted); }}

/* 行 */
.row {{
  display: grid;
  grid-template-columns: 90px 1fr 90px 80px 180px 120px;
  gap: 8px;
  padding: 9px 12px;
  border-bottom: 1px solid rgba(48,54,61,.6);
  align-items: start;
  transition: background .1s;
  font-size: 0.83rem;
}}
.row:hover {{ background: var(--surface); }}
.col-id {{ color: var(--muted); font-size: 0.75rem; font-family: monospace; }}
.col-repo {{ display: flex; flex-direction: column; gap: 3px; overflow: hidden; }}
.repo-link {{ color: var(--accent); text-decoration: none; font-weight: 500;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.repo-link:hover {{ text-decoration: underline; }}
.repo-desc {{ color: var(--muted); font-size: 0.75rem; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; }}
.col-stars {{ color: var(--orange); text-align: right; font-variant-numeric: tabular-nums; }}
.col-lang {{ color: var(--green); font-size: 0.75rem; }}
.col-domains {{ display: flex; flex-wrap: wrap; gap: 3px; }}
.domain-tag {{ background: rgba(88,166,255,.1); color: var(--accent);
  border-radius: 4px; padding: 1px 6px; font-size: 0.7rem; border: 1px solid rgba(88,166,255,.2); }}
.col-comm {{ display: flex; gap: 4px; flex-wrap: wrap; }}
.comm-badge {{ border-radius: 4px; padding: 2px 6px; font-size: 0.68rem; font-weight: 600; }}
.comm-wechat  {{ background: rgba(7,193,96,.15);  color: var(--wechat-color); border: 1px solid rgba(7,193,96,.3); }}
.comm-discord {{ background: rgba(88,101,242,.15); color: var(--discord-color); border: 1px solid rgba(88,101,242,.3); }}
.comm-qq      {{ background: rgba(18,183,245,.15); color: var(--qq-color); border: 1px solid rgba(18,183,245,.3); }}
.comm-telegram {{ background: rgba(44,165,224,.15); color: var(--telegram-color); border: 1px solid rgba(44,165,224,.3); }}
.comm-slack   {{ background: rgba(224,30,90,.15);  color: var(--slack-color); border: 1px solid rgba(224,30,90,.3); }}

/* 加载状态 */
.loading {{ text-align: center; padding: 60px; color: var(--muted); }}
.loading-bar {{ width: 200px; height: 4px; background: var(--border); border-radius: 2px;
  margin: 12px auto 0; overflow: hidden; }}
.loading-bar-inner {{ height: 100%; background: var(--accent); border-radius: 2px;
  animation: loading-anim 1.4s ease-in-out infinite; }}
@keyframes loading-anim {{
  0% {{ width: 0%; transform: translateX(0); }}
  50% {{ width: 60%; }}
  100% {{ width: 0%; transform: translateX(250px); }}
}}

/* 响应式 */
@media (max-width: 800px) {{
  .list-header, .row {{
    grid-template-columns: 70px 1fr 70px 60px;
  }}
  .col-domains, .col-comm {{ display: none; }}
}}
</style>
</head>
<body>

<nav class="nav">
  <a class="nav-back" href="/agent-radar/">← 周报</a>
  <span class="nav-title">🔭 Agent Radar · 全量项目库</span>
  <div class="nav-stats">
    <span class="stat-chip" id="stat-total">共 {total:,} 个项目</span>
    <span class="stat-chip" style="color:var(--wechat-color);border-color:rgba(7,193,96,.3);background:rgba(7,193,96,.06)">💬 微信群 {wechat_cnt:,}</span>
    <span class="stat-chip" style="color:var(--discord-color);border-color:rgba(88,101,242,.3);background:rgba(88,101,242,.06)">Discord {discord_cnt:,}</span>
    <span class="stat-chip" style="color:var(--muted);border-color:var(--border);background:transparent">有社区 {any_comm:,}</span>
  </div>
</nav>

<div class="toolbar">
  <input class="search-box" id="searchInput" type="text" placeholder="搜索仓库名 / 描述..." autocomplete="off">

  <div class="filter-group">
    <span class="filter-label">社区：</span>
    <button class="filter-btn filter-comm-wechat" data-comm="1">💬 微信</button>
    <button class="filter-btn filter-comm-discord" data-comm="2">Discord</button>
    <button class="filter-btn filter-comm-qq" data-comm="4">QQ</button>
    <button class="filter-btn filter-comm-telegram" data-comm="8">Telegram</button>
    <button class="filter-btn" data-comm="31">任意社区</button>
  </div>

  <div class="filter-group">
    <span class="filter-label">领域：</span>
    <button class="filter-btn" data-domain="">全部</button>
    <button class="filter-btn" data-domain="coding">编程辅助</button>
    <button class="filter-btn" data-domain="infra">基础设施</button>
    <button class="filter-btn" data-domain="rag">RAG</button>
    <button class="filter-btn" data-domain="chatbot">对话机器人</button>
    <button class="filter-btn" data-domain="creative">创意生成</button>
    <button class="filter-btn" data-domain="data">数据分析</button>
    <button class="filter-btn" data-domain="browser">浏览器/爬虫</button>
    <button class="filter-btn" data-domain="finance">金融量化</button>
    <button class="filter-btn" data-domain="ai4science">AI4Science</button>
    <button class="filter-btn" data-domain="security">安全</button>
    <button class="filter-btn" data-domain="hardware">硬件/机器人</button>
    <button class="filter-btn" data-domain="education">教育</button>
    <button class="filter-btn" data-domain="healthcare">医疗</button>
    <button class="filter-btn" data-domain="game">游戏</button>
  </div>

  <select class="sort-select" id="sortSelect">
    <option value="stars">按 Stars 排序</option>
    <option value="comm">按社区数排序</option>
    <option value="ar">按编号排序</option>
  </select>

  <span class="result-count" id="resultCount"></span>
</div>

<div class="list-wrap">
  <div class="list-header">
    <div>编号</div>
    <div>项目</div>
    <div style="text-align:right">Stars</div>
    <div>语言</div>
    <div>领域</div>
    <div>社区</div>
  </div>
  <div class="loading" id="loadingEl">
    正在加载项目数据...
    <div class="loading-bar"><div class="loading-bar-inner"></div></div>
  </div>
  <div id="rowList"></div>
  <div class="pagination" id="paginationEl" style="display:none"></div>
</div>

<script>
const PAGE_SIZE = 100;

const COMM_NAMES   = ['微信','Discord','QQ','Telegram','Slack'];
const COMM_CLASSES = ['comm-wechat','comm-discord','comm-qq','comm-telegram','comm-slack'];
const DOMAIN_LABELS = {{
  coding:'编程',infra:'基础设施',rag:'RAG',chatbot:'对话',creative:'创意',
  data:'数据',browser:'浏览器',finance:'金融',ai4science:'科研',
  security:'安全',hardware:'硬件',education:'教育',healthcare:'医疗',
  game:'游戏',personal:'个人',social:'社交',multimodal:'多模态',
  legal:'法务',hr:'招聘',ecommerce:'电商'
}};

let allData   = [];
let filtered  = [];
let activeComm   = 0;
let activeDomain = '';
let searchQ   = '';
let sortMode  = 'stars';
let curPage   = 0;   // 0-indexed

// ─── 加载 ────────────────────────────────────────────────────────────────────
fetch('full_projects_data.json')
  .then(r => {{
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }})
  .then(payload => {{
    allData = payload.records || [];
    document.getElementById('loadingEl').style.display = 'none';
    document.getElementById('paginationEl').style.display = '';
    applyFilter();
  }})
  .catch(err => {{
    const el = document.getElementById('loadingEl');
    el.innerHTML = `<div style="color:var(--red)">加载失败（${{err}}）</div>
      <div style="margin-top:8px;font-size:.8rem;color:var(--muted)">
      尝试直接访问：<a href="full_projects_data.json" style="color:var(--accent)">full_projects_data.json</a></div>`;
  }});

// ─── 筛选 + 排序 ──────────────────────────────────────────────────────────────
function applyFilter() {{
  const q = searchQ.toLowerCase();
  filtered = allData.filter(r => {{
    if (activeComm && !(r[6] & activeComm)) return false;
    if (activeDomain && !(r[5] || []).includes(activeDomain)) return false;
    if (q && !r[1].toLowerCase().includes(q) && !(r[4]||'').toLowerCase().includes(q)) return false;
    return true;
  }});
  if (sortMode === 'stars') filtered.sort((a,b) => b[2]-a[2]);
  else if (sortMode === 'comm') filtered.sort((a,b) => popcount(b[6])-popcount(a[6]));
  else filtered.sort((a,b) => a[0].localeCompare(b[0]));

  curPage = 0;
  document.getElementById('resultCount').textContent =
    filtered.length === allData.length
      ? `共 ${{allData.length.toLocaleString()}} 条`
      : `筛选结果 ${{filtered.length.toLocaleString()}} / ${{allData.length.toLocaleString()}}`;
  renderPage();
}}

function popcount(n) {{ let c=0; while(n){{c+=n&1;n>>=1;}} return c; }}

// ─── 渲染当页 ────────────────────────────────────────────────────────────────
function renderPage() {{
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  curPage = Math.max(0, Math.min(curPage, totalPages-1));

  const start = curPage * PAGE_SIZE;
  const end   = Math.min(start + PAGE_SIZE, filtered.length);
  const chunk = filtered.slice(start, end);

  document.getElementById('rowList').innerHTML = chunk.map(buildRow).join('');
  renderPagination(totalPages);
  window.scrollTo(0, 0);
}}

const PLATFORM_ICONS = {{
  wechat:'💬', discord:'🎮', qq:'🐧', telegram:'✈️', slack:'💼',
  twitter:'🐦', github:'🐙', website:'🌐',
}};

function buildRow(r, idx) {{
  const [ar_id, repo, stars, lang, desc, domains, comm_flags, yr, summary, commItems] = r;
  const starsStr = stars >= 1000 ? (stars/1000).toFixed(1)+'k' : String(stars);
  let commHTML = '';
  for (let b = 0; b < 5; b++) {{
    if (comm_flags & (1<<b))
      commHTML += `<span class="comm-badge ${{COMM_CLASSES[b]}}">${{COMM_NAMES[b]}}</span>`;
  }}
  const domainTags = (domains||[]).slice(0,3)
    .map(d=>`<span class="domain-tag">${{DOMAIN_LABELS[d]||d}}</span>`).join('');
  const ghUrl = `https://github.com/${{repo}}`;
  const shortRepo = repo.length > 38 ? repo.slice(0,36)+'…' : repo;
  const hasDetail = summary || (commItems && commItems.length > 0);
  const expandHint = hasDetail ? ` <span style="color:var(--muted);font-size:.7rem">▸ 详情</span>` : '';

  // 详情面板
  let detailHTML = '';
  if (hasDetail) {{
    let summaryPart = summary
      ? `<div class="detail-summary">${{escHtml(summary)}}</div>` : '';
    let commPart = '';
    for (const item of (commItems||[])) {{
      const icon = PLATFORM_ICONS[item.platform] || '📌';
      const name = item.platform.charAt(0).toUpperCase() + item.platform.slice(1);
      let content = '';
      if (item.value && item.delivery === 'link') {{
        content = `<div class="detail-comm-link"><a href="${{escHtml(item.value)}}" target="_blank" rel="noopener">${{escHtml(item.value.slice(0,60))}}</a></div>`;
      }} else if (item.note) {{
        content = `<div class="detail-comm-note">${{escHtml(item.note)}}</div>`;
      }}
      const meta = [];
      if (item.member_count) meta.push(`👥 ${{item.member_count}} 人`);
      if (item.verified) meta.push('✅ 已验证');
      const metaHTML = meta.length ? `<div class="detail-comm-meta">${{meta.join(' · ')}}</div>` : '';
      commPart += `<div class="detail-comm-item">
        <div class="detail-comm-platform">${{icon}} ${{name}}</div>
        ${{content}}${{metaHTML}}
      </div>`;
    }}
    const commListHTML = commPart ? `<div class="detail-comm-list">${{commPart}}</div>` : '';
    detailHTML = `<div class="row-detail" id="detail-${{ar_id}}">${{summaryPart}}${{commListHTML}}</div>`;
  }}

  return `<div class="row" onclick="toggleDetail('${{ar_id}}',${{hasDetail?1:0}})">
    <div class="col-id">${{ar_id}}</div>
    <div class="col-repo">
      <a class="repo-link" href="${{ghUrl}}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${{escHtml(shortRepo)}}</a>${{expandHint}}
      <div class="repo-desc">${{escHtml((desc||'').slice(0,150))}}</div>
    </div>
    <div class="col-stars">⭐ ${{starsStr}}</div>
    <div class="col-lang">${{escHtml(lang)}}</div>
    <div class="col-domains">${{domainTags}}</div>
    <div class="col-comm">${{commHTML}}</div>
  </div>${{detailHTML}}`;
}}

function toggleDetail(arId, hasDetail) {{
  if (!hasDetail) return;
  const el = document.getElementById('detail-' + arId);
  if (!el) return;
  el.classList.toggle('open');
}}

function renderPagination(totalPages) {{
  const el = document.getElementById('paginationEl');
  if (totalPages <= 1) {{ el.innerHTML=''; return; }}
  const pages = buildPageNumbers(curPage, totalPages);
  let html = `<button class="page-btn" onclick="goPage(${{curPage-1}})" ${{curPage===0?'disabled':''}}>‹ 上一页</button>`;
  for (const p of pages) {{
    if (p === '...') html += `<span class="page-info">…</span>`;
    else html += `<button class="page-btn ${{p===curPage?'active':''}}" onclick="goPage(${{p}})">${{p+1}}</button>`;
  }}
  html += `<button class="page-btn" onclick="goPage(${{curPage+1}})" ${{curPage===totalPages-1?'disabled':''}}>下一页 ›</button>`;
  html += `<span class="page-info">第 ${{curPage+1}} / ${{totalPages}} 页（每页 ${{PAGE_SIZE}} 条）</span>`;
  el.innerHTML = html;
}}

function buildPageNumbers(cur, total) {{
  const pages = [];
  if (total <= 9) {{ for (let i=0;i<total;i++) pages.push(i); return pages; }}
  pages.push(0);
  if (cur > 3) pages.push('...');
  for (let i=Math.max(1,cur-2); i<=Math.min(total-2,cur+2); i++) pages.push(i);
  if (cur < total-4) pages.push('...');
  pages.push(total-1);
  return pages;
}}

function goPage(p) {{
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  curPage = Math.max(0, Math.min(p, totalPages-1));
  renderPage();
}}

function escHtml(s) {{
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

// ─── 事件绑定 ────────────────────────────────────────────────────────────────
document.getElementById('searchInput').addEventListener('input', e => {{
  searchQ = e.target.value; applyFilter();
}});
document.getElementById('sortSelect').addEventListener('change', e => {{
  sortMode = e.target.value; applyFilter();
}});

document.querySelectorAll('[data-comm]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const v = parseInt(btn.dataset.comm);
    if (activeComm === v) {{
      activeComm = 0;
      document.querySelectorAll('[data-comm]').forEach(b=>b.classList.remove('active'));
    }} else {{
      document.querySelectorAll('[data-comm]').forEach(b=>b.classList.remove('active'));
      activeComm = v; btn.classList.add('active');
    }}
    applyFilter();
  }});
}});

document.querySelectorAll('[data-domain]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const v = btn.dataset.domain;
    document.querySelectorAll('[data-domain]').forEach(b=>b.classList.remove('active'));
    if (activeDomain === v && v !== '') {{
      activeDomain = '';
      document.querySelector('[data-domain=""]').classList.add('active');
    }} else {{
      activeDomain = v; btn.classList.add('active');
    }}
    applyFilter();
  }});
}});
document.querySelector('[data-domain=""]').classList.add('active');
</script>
</body>
</html>"""
