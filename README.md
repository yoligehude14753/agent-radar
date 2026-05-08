# agent-radar

> 创建日期：2026-05-08

## 简介

（在此描述项目目标和核心价值，参考 docs/PRD.md）

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt  # Python
# 或
npm install                       # Node.js

# 启动
python src/main.py  # 修改为实际命令
```

## 中台依赖

```python
# 已全局安装，直接导入：
from yoli_llm import call_llm_with_fallback
from yoli_agent.tools import web_search, bash
from yoli_db import Base, get_async_session
```

## 文档

- [PRD 需求文档](docs/PRD.md)
- [架构设计](docs/ARCHITECTURE.md)
- [测试检查清单](docs/CHECKLIST.md)
