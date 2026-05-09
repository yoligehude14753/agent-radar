"""
render_full_projects_usecase.py
================================
生成全量项目库页面和配套数据文件。

文件分层（避免单文件过大）：
  full_projects.html       — 页面框架（<50KB）
  full_projects_data.json  — 精简主数据，42k 条，~6-8MB（不含 summary/QR）
  full_projects_detail.json— 社区文字 + summary，仅 24k 有社区信息的条目，~7MB，首次点击懒加载
  community.html           — 完整群聊报告（github_radar.report.render 生成，含 QR 码），在 /community/ 路由
"""
from __future__ import annotations

import json
from pathlib import Path

from src.shared.db import get_conn
from src.shared.config import OUTPUT_DIR

FULL_PROJECTS_HTML   = OUTPUT_DIR / "full_projects.html"
FULL_PROJECTS_DATA   = OUTPUT_DIR / "full_projects_data.json"
FULL_PROJECTS_DETAIL = OUTPUT_DIR / "full_projects_detail.json"


def render_full_projects(verbose: bool = True) -> Path:
    conn = get_conn()

    total       = conn.execute("SELECT COUNT(*) FROM full_project_registry").fetchone()[0]
    wechat_cnt  = conn.execute("SELECT COUNT(*) FROM full_project_registry WHERE has_wechat=1").fetchone()[0]
    discord_cnt = conn.execute("SELECT COUNT(*) FROM full_project_registry WHERE has_discord=1").fetchone()[0]
    any_comm    = conn.execute("SELECT COUNT(*) FROM full_project_registry WHERE community_count>0").fetchone()[0]

    rows = conn.execute("""
        SELECT ar_id, repo, stars, language,
               description, domain_tags,
               has_wechat, has_discord, has_qq, has_telegram, has_slack,
               community_count, gh_created,
               summary_cn, community_items
        FROM full_project_registry
        ORDER BY stars DESC
    """).fetchall()
    conn.close()

    # ── 主数据：精简，每条只有基础字段 ──────────────────────────────────────
    records: list[list] = []
    # ── 详情数据：懒加载，含 summary + 社区文字（无 QR 图片 base64）────────
    detail: dict[str, dict] = {}

    for r in rows:
        comm_flags = (
            (1 if r["has_wechat"]   else 0) |
            (2 if r["has_discord"]  else 0) |
            (4 if r["has_qq"]       else 0) |
            (8 if r["has_telegram"] else 0) |
            (16 if r["has_slack"]   else 0)
        )
        desc    = (r["description"] or "")[:200]
        yr      = (r["gh_created"] or "")[:4]
        domains = json.loads(r["domain_tags"] or "[]")

        records.append([
            r["ar_id"],           # 0 "AR-00001"
            r["repo"],            # 1 "owner/name"
            r["stars"],           # 2
            r["language"] or "",  # 3
            desc,                 # 4
            domains,              # 5
            comm_flags,           # 6
            yr,                   # 7
        ])

        # 详情：有 summary 或社区信息才纳入
        summary_cn = (r["summary_cn"] or "")[:400]
        comm_items_raw = json.loads(r["community_items"] or "[]")

        # 过滤：仅保留文字字段（去掉 img_data_url / qr_data_url 这类 base64）
        comm_items_text = []
        has_qr_image = False
        for item in comm_items_raw:
            if not isinstance(item, dict):
                continue
            if item.get("img_data_url") or item.get("qr_data_url"):
                has_qr_image = True
            entry = {k: v for k, v in item.items()
                     if k in ("platform","delivery","note","value",
                               "member_count","verified","is_valid")}
            if entry.get("note") or entry.get("value"):
                comm_items_text.append(entry)

        if summary_cn or comm_items_text or has_qr_image:
            detail[r["repo"]] = {
                "summary": summary_cn,
                "items":   comm_items_text,
                "has_qr":  has_qr_image,  # 告知前端是否在 community.html 里有 QR
            }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(FULL_PROJECTS_DATA, "w", encoding="utf-8") as f:
        json.dump({
            "total": total, "wechat_cnt": wechat_cnt,
            "discord_cnt": discord_cnt, "any_comm": any_comm,
            "records": records,
        }, f, ensure_ascii=False, separators=(",", ":"))

    with open(FULL_PROJECTS_DETAIL, "w", encoding="utf-8") as f:
        json.dump(detail, f, ensure_ascii=False, separators=(",", ":"))

    if verbose:
        data_mb   = FULL_PROJECTS_DATA.stat().st_size / 1024 / 1024
        detail_mb = FULL_PROJECTS_DETAIL.stat().st_size / 1024 / 1024
        print(f"  [render_full] 主数据：{data_mb:.1f} MB，{total:,} 条")
        print(f"  [render_full] 详情数据：{detail_mb:.1f} MB，{len(detail):,} 条有社区信息")

    html = _build_html(total, wechat_cnt, discord_cnt, any_comm)
    with open(FULL_PROJECTS_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    if verbose:
        print(f"  [render_full] 已生成 {FULL_PROJECTS_HTML}")

    return FULL_PROJECTS_HTML


def _build_html(total: int, wechat_cnt: int, discord_cnt: int, any_comm: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Radar · 全量项目库</title>
<style>
:root {{
  --bg:#0d1117; --surface:#161b22; --border:#30363d;
  --text:#e6edf3; --muted:#8b949e; --accent:#58a6ff;
  --green:#3fb950; --orange:#d29922; --red:#f85149;
  --wechat:#07c160; --discord:#5865f2; --qq:#12b7f5;
  --telegram:#2ca5e0; --slack:#e01e5a;
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:var(--bg);color:var(--text);font-family:var(--font);}}

.nav{{background:var(--surface);border-bottom:1px solid var(--border);
  padding:12px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;
  position:sticky;top:0;z-index:100;}}
.nav-title{{font-weight:700;font-size:1.1rem;color:var(--accent);}}
.nav-back{{color:var(--muted);text-decoration:none;font-size:.85rem;}}
.nav-back:hover{{color:var(--accent);}}
.nav-community-link{{
  margin-left:auto;padding:5px 14px;border-radius:20px;
  background:rgba(7,193,96,.1);border:1px solid rgba(7,193,96,.3);
  color:var(--wechat);font-size:.8rem;text-decoration:none;font-weight:600;
}}
.nav-community-link:hover{{background:rgba(7,193,96,.2);}}
.nav-stats{{display:flex;gap:12px;flex-wrap:wrap;}}
.stat-chip{{background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.2);
  border-radius:20px;padding:4px 12px;font-size:.78rem;color:var(--accent);}}

.toolbar{{padding:14px 24px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;
  background:var(--surface);border-bottom:1px solid var(--border);}}
.search-box{{flex:1;min-width:200px;background:var(--bg);border:1px solid var(--border);
  border-radius:8px;padding:8px 12px;color:var(--text);font-size:.9rem;outline:none;}}
.search-box:focus{{border-color:var(--accent);}}
.search-box::placeholder{{color:var(--muted);}}

.filter-group{{display:flex;gap:5px;flex-wrap:wrap;align-items:center;}}
.filter-label{{font-size:.75rem;color:var(--muted);white-space:nowrap;}}
.fbtn{{padding:4px 11px;border-radius:20px;border:1px solid var(--border);
  background:transparent;color:var(--muted);font-size:.76rem;cursor:pointer;
  transition:all .15s;white-space:nowrap;}}
.fbtn:hover{{border-color:var(--accent);color:var(--accent);}}
.fbtn.active{{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600;}}
.fbtn[data-comm="1"].active{{background:var(--wechat);border-color:var(--wechat);}}
.fbtn[data-comm="2"].active{{background:var(--discord);border-color:var(--discord);}}
.fbtn[data-comm="4"].active{{background:var(--qq);border-color:var(--qq);}}
.fbtn[data-comm="8"].active{{background:var(--telegram);border-color:var(--telegram);}}
.sort-sel{{background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:6px 10px;color:var(--text);font-size:.82rem;cursor:pointer;}}
.result-count{{font-size:.8rem;color:var(--muted);margin-left:auto;}}

.list-wrap{{padding:0 24px 40px;}}
.list-header{{
  display:grid;grid-template-columns:90px 1fr 90px 80px 180px 120px;
  gap:8px;padding:10px 12px;font-size:.72rem;color:var(--muted);
  border-bottom:1px solid var(--border);text-transform:uppercase;
  letter-spacing:.05em;margin-top:10px;
  position:sticky;top:0;background:var(--bg);z-index:90;
}}
.row{{
  display:grid;grid-template-columns:90px 1fr 90px 80px 180px 120px;
  gap:8px;padding:9px 12px;
  border-bottom:1px solid rgba(48,54,61,.6);
  align-items:start;cursor:pointer;font-size:.83rem;
}}
.row:hover{{background:var(--surface);}}
.col-id{{color:var(--muted);font-size:.73rem;font-family:monospace;}}
.col-repo{{display:flex;flex-direction:column;gap:3px;overflow:hidden;}}
.repo-link{{color:var(--accent);text-decoration:none;font-weight:500;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.repo-link:hover{{text-decoration:underline;}}
.expand-hint{{color:var(--muted);font-size:.68rem;margin-left:4px;}}
.repo-desc{{color:var(--muted);font-size:.73rem;line-height:1.4;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}}
.col-stars{{color:var(--orange);text-align:right;font-variant-numeric:tabular-nums;}}
.col-lang{{color:var(--green);font-size:.73rem;}}
.col-domains{{display:flex;flex-wrap:wrap;gap:3px;}}
.dtag{{background:rgba(88,166,255,.1);color:var(--accent);border-radius:4px;
  padding:1px 6px;font-size:.68rem;border:1px solid rgba(88,166,255,.2);}}
.col-comm{{display:flex;gap:3px;flex-wrap:wrap;}}
.cbadge{{border-radius:4px;padding:2px 6px;font-size:.66rem;font-weight:600;}}
.cb-wechat{{background:rgba(7,193,96,.15);color:var(--wechat);border:1px solid rgba(7,193,96,.3);}}
.cb-discord{{background:rgba(88,101,242,.15);color:var(--discord);border:1px solid rgba(88,101,242,.3);}}
.cb-qq{{background:rgba(18,183,245,.15);color:var(--qq);border:1px solid rgba(18,183,245,.3);}}
.cb-telegram{{background:rgba(44,165,224,.15);color:var(--telegram);border:1px solid rgba(44,165,224,.3);}}
.cb-slack{{background:rgba(224,30,90,.15);color:var(--slack);border:1px solid rgba(224,30,90,.3);}}

.row-detail{{
  display:none;background:rgba(88,166,255,.03);
  border-left:3px solid var(--accent);border-radius:0 0 6px 6px;
  padding:12px 16px;margin:-1px 0 4px;
}}
.row-detail.open{{display:block;}}
.detail-loading{{color:var(--muted);font-size:.8rem;}}
.detail-summary{{color:var(--text);font-size:.82rem;line-height:1.65;margin-bottom:10px;}}
.detail-comm-list{{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;}}
.dci{{background:var(--surface);border:1px solid var(--border);
  border-radius:8px;padding:10px 14px;font-size:.78rem;max-width:340px;}}
.dci-plat{{font-weight:700;margin-bottom:4px;}}
.dci-note{{color:var(--muted);line-height:1.5;}}
.dci-link{{color:var(--accent);word-break:break-all;}}
.dci-meta{{color:var(--green);font-size:.7rem;margin-top:4px;}}
.community-link-btn{{
  display:inline-block;margin-top:10px;padding:5px 14px;
  border-radius:20px;background:rgba(7,193,96,.1);
  border:1px solid rgba(7,193,96,.3);color:var(--wechat);
  text-decoration:none;font-size:.78rem;font-weight:600;
}}
.community-link-btn:hover{{background:rgba(7,193,96,.2);}}

.pagination{{display:flex;align-items:center;justify-content:center;
  gap:7px;padding:20px 0;flex-wrap:wrap;}}
.pbtn{{padding:5px 13px;border-radius:6px;border:1px solid var(--border);
  background:var(--surface);color:var(--text);cursor:pointer;font-size:.8rem;transition:all .15s;}}
.pbtn:hover{{border-color:var(--accent);color:var(--accent);}}
.pbtn.active{{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600;}}
.pbtn:disabled{{opacity:.4;cursor:default;}}
.pinfo{{font-size:.8rem;color:var(--muted);}}

.loading{{text-align:center;padding:60px;color:var(--muted);}}
.loading-bar{{width:200px;height:4px;background:var(--border);border-radius:2px;
  margin:12px auto 0;overflow:hidden;}}
.loading-bar-inner{{height:100%;background:var(--accent);border-radius:2px;
  animation:la 1.4s ease-in-out infinite;}}
@keyframes la{{0%{{width:0%;transform:translateX(0);}}50%{{width:60%;}}100%{{width:0%;transform:translateX(250px);}}}}

@media(max-width:800px){{
  .list-header,.row{{grid-template-columns:70px 1fr 70px 60px;}}
  .col-domains,.col-comm{{display:none;}}
}}
</style>
</head>
<body>

<nav class="nav">
  <a class="nav-back" href="/agent-radar/">← 周报</a>
  <span class="nav-title">🔭 Agent Radar · 全量项目库</span>
  <div class="nav-stats">
    <span class="stat-chip">共 {total:,} 个项目</span>
    <span class="stat-chip" style="color:var(--wechat);border-color:rgba(7,193,96,.3);background:rgba(7,193,96,.06)">💬 微信群 {wechat_cnt:,}</span>
    <span class="stat-chip" style="color:var(--discord);border-color:rgba(88,101,242,.3);background:rgba(88,101,242,.06)">Discord {discord_cnt:,}</span>
    <span class="stat-chip" style="color:var(--muted);border-color:var(--border);background:transparent">有社区 {any_comm:,}</span>
  </div>
  <a class="nav-community-link" href="https://storage.googleapis.com/yoli-agent-radar/community.html" target="_blank">💬 完整群聊报告（含二维码）→</a>
</nav>

<div class="toolbar">
  <input class="search-box" id="searchInput" type="text" placeholder="搜索仓库名 / 描述..." autocomplete="off">
  <div class="filter-group">
    <span class="filter-label">社区：</span>
    <button class="fbtn" data-comm="1">💬 微信</button>
    <button class="fbtn" data-comm="2">Discord</button>
    <button class="fbtn" data-comm="4">QQ</button>
    <button class="fbtn" data-comm="8">Telegram</button>
    <button class="fbtn" data-comm="31">任意社区</button>
  </div>
  <div class="filter-group">
    <span class="filter-label">领域：</span>
    <button class="fbtn" data-domain="">全部</button>
    <button class="fbtn" data-domain="coding">编程辅助</button>
    <button class="fbtn" data-domain="infra">基础设施</button>
    <button class="fbtn" data-domain="rag">RAG</button>
    <button class="fbtn" data-domain="chatbot">对话机器人</button>
    <button class="fbtn" data-domain="creative">创意生成</button>
    <button class="fbtn" data-domain="data">数据分析</button>
    <button class="fbtn" data-domain="browser">浏览器/爬虫</button>
    <button class="fbtn" data-domain="finance">金融量化</button>
    <button class="fbtn" data-domain="ai4science">AI4Science</button>
    <button class="fbtn" data-domain="security">安全</button>
    <button class="fbtn" data-domain="hardware">硬件/机器人</button>
    <button class="fbtn" data-domain="education">教育</button>
    <button class="fbtn" data-domain="healthcare">医疗</button>
    <button class="fbtn" data-domain="game">游戏</button>
  </div>
  <select class="sort-sel" id="sortSel">
    <option value="stars">按 Stars 排序</option>
    <option value="comm">按社区数排序</option>
    <option value="ar">按编号排序</option>
  </select>
  <span class="result-count" id="resultCount"></span>
</div>

<div class="list-wrap">
  <div class="list-header">
    <div>编号</div><div>项目</div>
    <div style="text-align:right">Stars</div>
    <div>语言</div><div>领域</div><div>社区</div>
  </div>
  <div class="loading" id="loadingEl">
    正在加载项目数据...
    <div class="loading-bar"><div class="loading-bar-inner"></div></div>
  </div>
  <div id="rowList"></div>
  <div class="pagination" id="paginEl" style="display:none"></div>
</div>

<script>
const PAGE_SIZE = 100;
const COMM_NAMES   = ['微信','Discord','QQ','Telegram','Slack'];
const COMM_CLS     = ['cb-wechat','cb-discord','cb-qq','cb-telegram','cb-slack'];
const DOMAIN_LABELS = {{
  coding:'编程',infra:'基础设施',rag:'RAG',chatbot:'对话',creative:'创意',
  data:'数据',browser:'浏览器',finance:'金融',ai4science:'科研',
  security:'安全',hardware:'硬件',education:'教育',healthcare:'医疗',
  game:'游戏',personal:'个人',social:'社交',multimodal:'多模态',
  legal:'法务',hr:'招聘',ecommerce:'电商'
}};
const PLAT_ICONS = {{wechat:'💬',discord:'🎮',qq:'🐧',telegram:'✈️',slack:'💼',twitter:'🐦',github:'🐙',website:'🌐'}};

let allData=[], filtered=[], activeComm=0, activeDomain='', searchQ='', sortMode='stars', curPage=0;

// 详情懒加载缓存
let detailData=null, detailLoading=false, detailCBs=[];
function loadDetail(cb) {{
  if (detailData){{ cb(detailData); return; }}
  detailCBs.push(cb);
  if (detailLoading) return;
  detailLoading=true;
  fetch('full_projects_detail.json')
    .then(r=>r.json())
    .then(d=>{{ detailData=d; detailCBs.forEach(fn=>fn(d)); detailCBs=[]; }})
    .catch(()=>{{ detailData={{}}; detailCBs.forEach(fn=>fn({{}})); detailCBs=[]; }});
}}

// 加载主数据
fetch('full_projects_data.json')
  .then(r=>{{if(!r.ok) throw new Error('HTTP '+r.status); return r.json();}})
  .then(payload=>{{
    allData=payload.records||[];
    document.getElementById('loadingEl').style.display='none';
    document.getElementById('paginEl').style.display='';
    applyFilter();
  }})
  .catch(err=>{{
    document.getElementById('loadingEl').innerHTML=`<div style="color:var(--red)">加载失败：${{err}}</div>`;
  }});

function popcount(n){{let c=0;while(n){{c+=n&1;n>>=1;}}return c;}}

function applyFilter(){{
  const q=searchQ.toLowerCase();
  filtered=allData.filter(r=>{{
    if(activeComm&&!(r[6]&activeComm)) return false;
    if(activeDomain&&!(r[5]||[]).includes(activeDomain)) return false;
    if(q&&!r[1].toLowerCase().includes(q)&&!(r[4]||'').toLowerCase().includes(q)) return false;
    return true;
  }});
  if(sortMode==='stars') filtered.sort((a,b)=>b[2]-a[2]);
  else if(sortMode==='comm') filtered.sort((a,b)=>popcount(b[6])-popcount(a[6]));
  else filtered.sort((a,b)=>a[0].localeCompare(b[0]));
  curPage=0;
  document.getElementById('resultCount').textContent=
    filtered.length===allData.length
      ? `共 ${{allData.length.toLocaleString()}} 条`
      : `筛选 ${{filtered.length.toLocaleString()}} / ${{allData.length.toLocaleString()}}`;
  renderPage();
}}

function renderPage(){{
  const totalPg=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE));
  curPage=Math.max(0,Math.min(curPage,totalPg-1));
  const chunk=filtered.slice(curPage*PAGE_SIZE,(curPage+1)*PAGE_SIZE);
  document.getElementById('rowList').innerHTML=chunk.map(buildRow).join('');
  renderPagination(totalPg);
  window.scrollTo(0,0);
}}

function buildRow(r){{
  const [ar_id,repo,stars,lang,desc,domains,comm_flags,yr]=r;
  const starsStr=stars>=1000?(stars/1000).toFixed(1)+'k':String(stars);
  let commH='';
  for(let b=0;b<5;b++) if(comm_flags&(1<<b)) commH+=`<span class="cbadge ${{COMM_CLS[b]}}">${{COMM_NAMES[b]}}</span>`;
  const domH=(domains||[]).slice(0,3).map(d=>`<span class="dtag">${{DOMAIN_LABELS[d]||d}}</span>`).join('');
  const ghUrl=`https://github.com/${{repo}}`;
  const shortRepo=repo.length>38?repo.slice(0,36)+'…':repo;
  return `<div class="row" onclick="toggleDetail('${{ar_id}}','${{repo.replace(/'/g,"\\\\'")}}')">
    <div class="col-id">${{ar_id}}</div>
    <div class="col-repo">
      <a class="repo-link" href="${{ghUrl}}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${{escHtml(shortRepo)}}</a><span class="expand-hint">▸</span>
      <div class="repo-desc">${{escHtml((desc||'').slice(0,150))}}</div>
    </div>
    <div class="col-stars">⭐ ${{starsStr}}</div>
    <div class="col-lang">${{escHtml(lang)}}</div>
    <div class="col-domains">${{domH}}</div>
    <div class="col-comm">${{commH}}</div>
  </div>
  <div class="row-detail" id="d-${{ar_id}}"><div class="detail-loading">加载中...</div></div>`;
}}

function toggleDetail(arId, repo){{
  const el=document.getElementById('d-'+arId);
  if(!el) return;
  if(el.classList.contains('open')){{ el.classList.remove('open'); return; }}
  el.classList.add('open');
  if(el.dataset.loaded) return;
  el.dataset.loaded='1';
  loadDetail(data=>{{
    const d=data[repo];
    if(!d){{ el.innerHTML='<div style="color:var(--muted);font-size:.8rem">暂无社区信息</div>'; return; }}
    let html='';
    if(d.summary) html+=`<div class="detail-summary">${{escHtml(d.summary)}}</div>`;
    let commPart='';
    for(const item of (d.items||[])){{
      const icon=PLAT_ICONS[item.platform]||'📌';
      const pname=(item.platform||'').charAt(0).toUpperCase()+(item.platform||'').slice(1);
      let content='';
      if(item.value&&item.delivery==='link'){{
        content=`<div class="dci-link"><a href="${{escHtml(item.value)}}" target="_blank" rel="noopener">${{escHtml((item.value||'').slice(0,80))}}</a></div>`;
      }} else if(item.note){{
        content=`<div class="dci-note">${{escHtml(item.note)}}</div>`;
      }}
      if(!content) continue;
      const meta=[];
      if(item.member_count) meta.push(`👥 ${{item.member_count}} 人`);
      if(item.verified) meta.push('✅ 已验证');
      commPart+=`<div class="dci">
        <div class="dci-plat">${{icon}} ${{pname}}</div>
        ${{content}}
        ${{meta.length?`<div class="dci-meta">${{meta.join(' · ')}}</div>`:''}}
      </div>`;
    }}
    if(commPart) html+=`<div class="detail-comm-list">${{commPart}}</div>`;
    if(d.has_qr){{
      const qrUrl=encodeURIComponent(repo);
      html+=`<a class="community-link-btn" href="https://storage.googleapis.com/yoli-agent-radar/community.html" target="_blank">📷 查看完整二维码 →</a>`;
    }}
    el.innerHTML=html||'<div style="color:var(--muted);font-size:.8rem">暂无内容</div>';
  }});
}}

function renderPagination(totalPg){{
  const el=document.getElementById('paginEl');
  if(totalPg<=1){{el.innerHTML='';return;}}
  const pages=buildPageNums(curPage,totalPg);
  let h=`<button class="pbtn" onclick="goPage(${{curPage-1}})" ${{curPage===0?'disabled':''}}>‹</button>`;
  for(const p of pages){{
    if(p==='...') h+=`<span class="pinfo">…</span>`;
    else h+=`<button class="pbtn ${{p===curPage?'active':''}}" onclick="goPage(${{p}})">${{p+1}}</button>`;
  }}
  h+=`<button class="pbtn" onclick="goPage(${{curPage+1}})" ${{curPage===totalPg-1?'disabled':''}}>›</button>`;
  h+=`<span class="pinfo">第 ${{curPage+1}}/${{totalPg}} 页</span>`;
  el.innerHTML=h;
}}
function buildPageNums(cur,total){{
  if(total<=9)return Array.from({{length:total}},(_,i)=>i);
  const p=[0];
  if(cur>3) p.push('...');
  for(let i=Math.max(1,cur-2);i<=Math.min(total-2,cur+2);i++) p.push(i);
  if(cur<total-4) p.push('...');
  p.push(total-1);
  return p;
}}
function goPage(p){{
  const total=Math.ceil(filtered.length/PAGE_SIZE);
  curPage=Math.max(0,Math.min(p,total-1));
  renderPage();
}}
function escHtml(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}

// ── 事件 ──────────────────────────────────────────────────────────────────
document.getElementById('searchInput').addEventListener('input',e=>{{searchQ=e.target.value;applyFilter();}});
document.getElementById('sortSel').addEventListener('change',e=>{{sortMode=e.target.value;applyFilter();}});

document.querySelectorAll('[data-comm]').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    const v=parseInt(btn.dataset.comm);
    if(activeComm===v){{activeComm=0;document.querySelectorAll('[data-comm]').forEach(b=>b.classList.remove('active'));}}
    else{{document.querySelectorAll('[data-comm]').forEach(b=>b.classList.remove('active'));activeComm=v;btn.classList.add('active');}}
    applyFilter();
  }});
}});
document.querySelectorAll('[data-domain]').forEach(btn=>{{
  btn.addEventListener('click',()=>{{
    const v=btn.dataset.domain;
    document.querySelectorAll('[data-domain]').forEach(b=>b.classList.remove('active'));
    if(activeDomain===v&&v!==''){{activeDomain='';document.querySelector('[data-domain=""]').classList.add('active');}}
    else{{activeDomain=v;btn.classList.add('active');}}
    applyFilter();
  }});
}});
document.querySelector('[data-domain=""]').classList.add('active');
</script>
</body>
</html>"""
