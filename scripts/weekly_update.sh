#!/usr/bin/env bash
# weekly_update.sh
# 本地每周数据更新脚本（在有 GitHub Token 和完整缓存的机器上运行）
#
# 步骤：
#   1. find_communities.py 差量扫描（最近 7 天新项目）→ 更新 results.jsonl
#   2. agent-radar main.py（重新导入 + 评分 + 渲染）
#   3. 上传 community.html / community_data.json / 缓存文件到 GCS
#   4. 重新部署 Cloud Run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_RADAR_DIR="$(dirname "$SCRIPT_DIR")"
COMMUNITY_FINDER_DIR="/Users/yoligehude/Desktop/all/openall/projects/github-community-finder"
GCS_BUCKET="yoli-agent-radar"
REGION="asia-east1"
PROJECT_ID="glass-sequence-494808-s7"
IMAGE="asia-east1-docker.pkg.dev/${PROJECT_ID}/agent-radar/report"

echo "====== Agent Radar 周更新 $(date '+%Y-%m-%d %H:%M') ======"

# ── 1. 差量扫描（在本机有 GitHub Token 和缓存的情况下）──────────────────────
echo ""
echo "▶ [1/5] 差量扫描 github-community-finder（最近 7 天）..."
cd "$COMMUNITY_FINDER_DIR"
python3 find_communities.py \
  --mode scan \
  --days-back 7 \
  --min-stars 50 \
  --out report_weekly_delta.html \
  --concurrency 8
echo "  差量扫描完成"

# ── 2. 运行 agent-radar 主流程 ────────────────────────────────────────────────
echo ""
echo "▶ [2/5] 运行 agent-radar（评分 + 渲染）..."
cd "$AGENT_RADAR_DIR"
python3 src/main.py --skip-crawl   # 爬取已在上一步完成
echo "  渲染完成"

# ── 3. 上传到 GCS ──────────────────────────────────────────────────────────────
echo ""
echo "▶ [3/5] 上传到 GCS..."

gsutil -m \
  -h "Content-Type:text/html;charset=UTF-8" \
  -h "Cache-Control:public,max-age=3600" \
  cp output/community.html "gs://${GCS_BUCKET}/community.html"
gsutil acl ch -u AllUsers:R "gs://${GCS_BUCKET}/community.html"

gsutil -m \
  -h "Content-Type:application/json" \
  -h "Cache-Control:public,max-age=3600" \
  cp output/community_data.json "gs://${GCS_BUCKET}/community_data.json"
gsutil acl ch -u AllUsers:R "gs://${GCS_BUCKET}/community_data.json"

# 更新 CI 用缓存
gsutil -m cp \
  "${COMMUNITY_FINDER_DIR}/report_full.html.cache/results.jsonl" \
  "gs://${GCS_BUCKET}/cache/results.jsonl"
gsutil -m cp \
  "${COMMUNITY_FINDER_DIR}/report_full.html.cache/repos.json" \
  "gs://${GCS_BUCKET}/cache/repos.json"

echo "  GCS 上传完成"

# ── 4. 构建 Docker 镜像并部署 ─────────────────────────────────────────────────
echo ""
echo "▶ [4/5] 构建 Docker 镜像..."
cd "$AGENT_RADAR_DIR"
WEEK=$(python3 -c "import datetime; print(datetime.date.today().strftime('%Y-W%V'))")
docker buildx build --platform linux/amd64 \
  -t "${IMAGE}:latest" \
  -t "${IMAGE}:${WEEK}" \
  --push .
echo "  镜像推送完成"

echo ""
echo "▶ [5/5] 部署到 Cloud Run..."
gcloud run services update agent-radar \
  --image "${IMAGE}:latest" \
  --region "$REGION" \
  --project "$PROJECT_ID"
echo "  部署完成"

echo ""
echo "✅ 周更新完成！"
echo "   周报：https://yoliyoli.uk/agent-radar/"
echo "   全量库：https://yoliyoli.uk/agent-radar/all/"
echo "   群聊报告（含 QR）：https://storage.googleapis.com/${GCS_BUCKET}/community.html"
