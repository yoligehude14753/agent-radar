#!/usr/bin/env bash
# setup_vm.sh
# 在 yoli-server-2（或任意 Linux VM）上一键完成环境配置 + 每周自动更新
# 用法：curl -sSL <raw_url>/scripts/setup_vm.sh | bash
#   或：git clone ... && bash agent-radar/scripts/setup_vm.sh

set -euo pipefail

HOME_DIR="$HOME"
WORK_DIR="$HOME_DIR/agent-radar-worker"
AGENT_RADAR_DIR="$WORK_DIR/agent-radar"
COMMUNITY_FINDER_DIR="$WORK_DIR/github-community-finder"
GCS_BUCKET="yoli-agent-radar"
LOG_FILE="$HOME_DIR/agent-radar-cron.log"

echo "========================================"
echo " Agent Radar VM 自动更新配置脚本"
echo "========================================"

# ── 1. 安装系统依赖 ────────────────────────────────────────────────────────────
echo ""
echo "▶ [1/6] 安装系统依赖..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git curl wget \
  libjpeg-dev libpng-dev 2>/dev/null || true

# 安装 gcloud（如果没有）
if ! command -v gcloud &>/dev/null; then
  echo "  安装 gcloud CLI..."
  curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts
  export PATH="$HOME/google-cloud-sdk/bin:$PATH"
fi
# 安装 Docker（如果没有）
if ! command -v docker &>/dev/null; then
  echo "  安装 Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" || true
fi

echo "  系统依赖安装完成"

# ── 2. 克隆仓库 ────────────────────────────────────────────────────────────────
echo ""
echo "▶ [2/6] 克隆仓库..."
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

if [ ! -d "$AGENT_RADAR_DIR/.git" ]; then
  git clone https://github.com/yoligehude14753/agent-radar.git "$AGENT_RADAR_DIR"
else
  echo "  agent-radar 已存在，更新..."
  cd "$AGENT_RADAR_DIR" && git pull --ff-only && cd "$WORK_DIR"
fi

if [ ! -d "$COMMUNITY_FINDER_DIR/.git" ]; then
  # 私有仓库用 SSH 或 PAT
  if [ -f "$HOME/.github_token" ]; then
    TOKEN=$(cat "$HOME/.github_token")
    git clone "https://$TOKEN@github.com/yoligehude14753/github-community-finder.git" "$COMMUNITY_FINDER_DIR" 2>/dev/null || \
    git clone https://github.com/yoligehude14753/github-community-finder.git "$COMMUNITY_FINDER_DIR" 2>/dev/null || \
    echo "  ⚠ github-community-finder 克隆失败，请手动克隆到 $COMMUNITY_FINDER_DIR"
  else
    echo "  ⚠ 未找到 GitHub token，请手动克隆 github-community-finder 到 $COMMUNITY_FINDER_DIR"
    echo "    git clone https://YOUR_TOKEN@github.com/... $COMMUNITY_FINDER_DIR"
  fi
fi

# ── 3. 配置 Python 虚拟环境 ────────────────────────────────────────────────────
echo ""
echo "▶ [3/6] 配置 Python 虚拟环境..."
python3 -m venv "$WORK_DIR/venv"
source "$WORK_DIR/venv/bin/activate"
pip install --upgrade pip -q

# 安装 agent-radar 依赖
pip install -r "$AGENT_RADAR_DIR/requirements.txt" -q

# 安装 github-community-finder 依赖（如果存在）
if [ -f "$COMMUNITY_FINDER_DIR/requirements.txt" ]; then
  pip install -r "$COMMUNITY_FINDER_DIR/requirements.txt" -q
fi

deactivate
echo "  Python 环境配置完成"

# ── 4. 从 GCS 下载初始数据缓存 ────────────────────────────────────────────────
echo ""
echo "▶ [4/6] 从 GCS 下载数据缓存..."
CACHE_DIR="$COMMUNITY_FINDER_DIR/report_full.html.cache"
mkdir -p "$CACHE_DIR"

# 需要 gcloud auth 或 service account
if gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q "@"; then
  echo "  已有 gcloud 认证"
else
  echo "  ⚠ 未找到 gcloud 认证，请运行："
  echo "    gcloud auth login"
  echo "  或配置 Service Account"
fi

gsutil -m cp "gs://$GCS_BUCKET/cache/results.jsonl" "$CACHE_DIR/results.jsonl" 2>/dev/null && \
  echo "  results.jsonl 下载完成（$(du -sh "$CACHE_DIR/results.jsonl" | cut -f1)）" || \
  echo "  ⚠ results.jsonl 下载失败，请检查 gcloud 权限"

gsutil -m cp "gs://$GCS_BUCKET/cache/repos.json" "$CACHE_DIR/repos.json" 2>/dev/null && \
  echo "  repos.json 下载完成（$(du -sh "$CACHE_DIR/repos.json" | cut -f1)）" || \
  echo "  ⚠ repos.json 下载失败，请检查 gcloud 权限"

# ── 5. 写入环境变量文件 ────────────────────────────────────────────────────────
echo ""
echo "▶ [5/6] 配置环境变量..."
ENV_FILE="$WORK_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'ENVEOF'
# Agent Radar 周更新所需环境变量
# 请填写以下值后保存
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
COMMUNITY_MODEL=gpt-4.1-nano
GCS_BUCKET=yoli-agent-radar
GCP_PROJECT=glass-sequence-494808-s7
GCP_REGION=asia-east1
DOCKER_IMAGE=asia-east1-docker.pkg.dev/glass-sequence-494808-s7/agent-radar/report
ENVEOF
  echo "  ⚠ 请编辑 $ENV_FILE 填写 API Token："
  echo "    nano $ENV_FILE"
else
  echo "  .env 已存在，跳过"
fi

# ── 6. 写入 weekly_update 脚本并配置 cron ─────────────────────────────────────
echo ""
echo "▶ [6/6] 配置每周自动更新..."

CRON_SCRIPT="$WORK_DIR/run_weekly.sh"
cat > "$CRON_SCRIPT" <<CRONEOF
#!/usr/bin/env bash
# 自动生成的周更新脚本，请勿手动编辑此文件（修改 setup_vm.sh）
set -euo pipefail

WORK_DIR="$WORK_DIR"
AGENT_RADAR_DIR="$AGENT_RADAR_DIR"
COMMUNITY_FINDER_DIR="$COMMUNITY_FINDER_DIR"
CACHE_DIR="$CACHE_DIR"
LOG_FILE="$LOG_FILE"

# 加载环境变量
set -a; source "$WORK_DIR/.env"; set +a

# 激活 Python 虚拟环境
source "$WORK_DIR/venv/bin/activate"

echo "" >> "\$LOG_FILE"
echo "====== \$(date '+%Y-%m-%d %H:%M') 周更新开始 ======" >> "\$LOG_FILE"

# 拉最新代码
cd "\$AGENT_RADAR_DIR" && git pull --ff-only >> "\$LOG_FILE" 2>&1

# 差量扫描（最近 7 天新项目）
echo "▶ 差量扫描..." >> "\$LOG_FILE"
cd "\$COMMUNITY_FINDER_DIR"
python3 find_communities.py \\
  --mode scan --days-back 7 --min-stars 50 \\
  --out report_weekly_delta.html \\
  --concurrency 5 >> "\$LOG_FILE" 2>&1

# 运行 agent-radar 主流程
echo "▶ 渲染报告..." >> "\$LOG_FILE"
cd "\$AGENT_RADAR_DIR"
python3 src/main.py --skip-crawl >> "\$LOG_FILE" 2>&1

# 上传到 GCS
echo "▶ 上传 GCS..." >> "\$LOG_FILE"
gsutil -m -h "Content-Type:text/html;charset=UTF-8" \\
  -h "Cache-Control:public,max-age=3600" \\
  cp output/community.html "gs://\$GCS_BUCKET/community.html" >> "\$LOG_FILE" 2>&1
gsutil acl ch -u AllUsers:R "gs://\$GCS_BUCKET/community.html" >> "\$LOG_FILE" 2>&1

gsutil -m -h "Content-Type:application/json" \\
  -h "Cache-Control:public,max-age=3600" \\
  cp output/community_data.json "gs://\$GCS_BUCKET/community_data.json" >> "\$LOG_FILE" 2>&1
gsutil acl ch -u AllUsers:R "gs://\$GCS_BUCKET/community_data.json" >> "\$LOG_FILE" 2>&1

# 更新 GCS 缓存供 CI 使用
gsutil -m cp "\$CACHE_DIR/results.jsonl" "gs://\$GCS_BUCKET/cache/results.jsonl" >> "\$LOG_FILE" 2>&1

# 构建并部署
echo "▶ 部署..." >> "\$LOG_FILE"
cd "\$AGENT_RADAR_DIR"
WEEK=\$(python3 -c "import datetime; print(datetime.date.today().strftime('%Y-W%V'))")
docker buildx build --platform linux/amd64 \\
  -t "\$DOCKER_IMAGE:latest" -t "\$DOCKER_IMAGE:\$WEEK" --push . >> "\$LOG_FILE" 2>&1
gcloud run services update agent-radar \\
  --image "\$DOCKER_IMAGE:latest" \\
  --region "\$GCP_REGION" --project "\$GCP_PROJECT" >> "\$LOG_FILE" 2>&1

echo "✅ 完成" >> "\$LOG_FILE"
CRONEOF
chmod +x "$CRON_SCRIPT"

# 配置 cron（每周日 23:00，在 CI 周一 01:00 之前）
CRON_LINE="0 23 * * 0 $CRON_SCRIPT >> $LOG_FILE 2>&1"
(crontab -l 2>/dev/null | grep -v "run_weekly\|agent-radar"; echo "$CRON_LINE") | crontab -

echo "  ✅ cron 已配置（每周日 23:00 自动运行）"
crontab -l | grep agent-radar

echo ""
echo "========================================"
echo " 配置完成！"
echo "========================================"
echo ""
echo "下一步（必须完成）："
echo "  1. 编辑环境变量：nano $ENV_FILE"
echo "  2. 配置 gcloud 认证：gcloud auth login"
echo "     或服务账号：gcloud auth activate-service-account --key-file=SA_KEY.json"
echo "  3. 手动测试一次：bash $CRON_SCRIPT"
echo ""
echo "日志：tail -f $LOG_FILE"
echo "周报：https://yoliyoli.uk/agent-radar/"
echo "群聊：https://storage.googleapis.com/yoli-agent-radar/community.html"
