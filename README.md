# News_xiaohongshu_mcp

一个双服务项目：

- `News_xiaohongshu`：热点抓取 + 草稿生成 + 审核 + 发布编排（FastAPI）
- `xiaohongshu-mcp-python`：小红书浏览器自动化 MCP 服务（FastAPI + Playwright）

该仓库用于实现“新闻到小红书发布”的半自动流程。

## 1. 整体架构

```text
[News_xiaohongshu 主服务 :5108]
   ├─ 热点抓取（Anspire/Bocha/Tavily/Mock）
   ├─ 草稿生成与状态流转（pending_review -> approved -> published/failed）
   ├─ 封面生成（Mock 或 OpenAI-Compatible 图像模型）
   └─ 通过 MCP 调用发布工具
            |
            v
[xiaohongshu-mcp-python :18060]
   ├─ MCP 协议 /mcp
   ├─ Playwright 驱动浏览器
   └─ 小红书登录、发帖、互动工具
```

## 2. 目录结构

```text
News_xiaohongshu_mcp/
├─ News_xiaohongshu/          # 主服务（管理页 + 业务 API）
└─ xiaohongshu-mcp-python/    # MCP 自动化服务
```

## 3. 环境要求

- Python `3.10+`（建议 3.11/3.12）
- pip
- Chromium 浏览器内核（通过 Playwright 安装）
- 数据库：
  - 生产建议 MySQL
  - 本地调试可用 SQLite（通过 `DATABASE_URL` 或 `DB_DIALECT=sqlite`）

## 4. 快速启动（推荐顺序）

## 4.1 启动 MCP 服务（先启动）

```bash
cd News_xiaohongshu_mcp/xiaohongshu-mcp-python
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

安装依赖：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

配置：

```bash
copy .env.example .env
```

启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 18060
```

验证：

- `http://127.0.0.1:18060/health`

## 4.2 启动主服务

```bash
cd News_xiaohongshu_mcp/News_xiaohongshu
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

配置：

```bash
copy .env.example .env
```

建议最少配置：

- 数据库（MySQL 或 SQLite）
- `SEARCH_TOOL_TYPE` 与对应 API Key（至少一个搜索供应商）
- `XHS_MCP_BASE_URL=http://127.0.0.1:18060`

启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 5108 --reload
```

验证：

- `http://127.0.0.1:5108/health`
- 管理页：`http://127.0.0.1:5108/admin`
- OpenAPI：`http://127.0.0.1:5108/docs`

## 5. 关键环境变量

## 5.1 主服务 `News_xiaohongshu/.env`

服务基础：

- `APP_HOST` / `APP_PORT`
- `LOG_LEVEL`

数据库：

- `DATABASE_URL`（优先）
- 或 `DB_DIALECT/DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`

搜索：

- `SEARCH_TOOL_TYPE=AnspireAPI|BochaAPI|TavilyAPI|MockAPI`
- `ANSPIRE_API_KEY`
- `BOCHA_WEB_SEARCH_API_KEY`
- `TAVILY_API_KEY`

封面生成：

- `IMAGE_GEN_PROVIDER=MockAPI|OpenAICompatible`
- `IMAGE_GEN_API_KEY`
- `IMAGE_GEN_BASE_URL`
- `IMAGE_GEN_MODEL`
- `AUTO_GENERATE_COVER_ON_DRAFT=True|False`
- `AUTO_GENERATE_COVER_STRICT=True|False`

发布联动：

- `XHS_MCP_BASE_URL=http://127.0.0.1:18060`
- `XHS_MCP_API_KEY=`（本地一般可空）
- `PUBLISH_GUARD_TOKEN=`（设置后发布接口需请求头令牌）

调度：

- `SCHEDULER_ENABLED=True|False`
- `HOT_NEWS_INTERVAL_MINUTES=30`
- `HOT_NEWS_DEFAULT_QUERY`
- `HOT_NEWS_DEFAULT_LIMIT`

## 5.2 MCP 服务 `xiaohongshu-mcp-python/.env`

- `APP_HOST` / `APP_PORT`（默认 `18060`）
- `MCP_PROTOCOL_VERSION`
- `HEADLESS`（常规自动化）
- `PUBLISH_HEADLESS`（发布时建议 `false`，提高稳定性）
- `BROWSER_TIMEOUT_MS`
- `STORAGE_STATE_PATH=./cookies.json`
- `DOWNLOAD_DIR=./downloads`

## 6. 典型业务流程

1. 打开管理页 `http://127.0.0.1:5108/admin`
2. 检查 MCP 连通和登录状态
3. 如果未登录，执行扫码登录
4. 抓取热点（`/api/news/hot/fetch`）
5. 生成草稿（`/api/drafts/generate`）
6. 在草稿页编辑并审核通过（`approve`）
7. 调用发布（`/api/publish/{draft_id}`）
8. 查看发布状态（`/api/publish/{draft_id}/status`）

## 7. API 速览

## 7.1 主服务 API

- `GET /health`
- `GET /api/system/status`
- `POST /api/news/hot/fetch`
- `GET /api/news/hot`
- `POST /api/drafts/generate`
- `GET /api/drafts`
- `GET /api/drafts/{draft_id}`
- `PUT /api/drafts/{draft_id}`
- `POST /api/drafts/{draft_id}/approve`
- `POST /api/drafts/{draft_id}/reject`
- `POST /api/publish/{draft_id}`
- `GET /api/publish/{draft_id}/status`
- `GET /api/jobs/history`
- `GET /api/xhs/login-status`
- `GET /api/xhs/login-qrcode`
- `POST /api/xhs/reset-login`
- `POST /api/uploads/cover`
- `GET /api/cover/provider`
- `POST /api/cover/generate`

## 7.2 MCP API

- `GET /health`
- `POST /mcp`（JSON-RPC）

MCP 常用方法：

- `initialize`
- `tools/list`
- `tools/call`

内置 13 个工具（登录、发帖、搜索、评论、点赞、收藏等）。

## 8. 测试

主服务：

```bash
cd News_xiaohongshu_mcp/News_xiaohongshu
pytest tests/test_api.py -q
```

MCP 服务：

```bash
cd News_xiaohongshu_mcp/xiaohongshu-mcp-python
pytest tests/test_mcp_protocol.py tests/test_tools_dispatch.py -q
```

## 9. 常见问题

## 9.1 发布时报 “not logged in / creator center not logged in”

- 重新扫码登录
- 保持浏览器会话有效，不要中途清理 `cookies.json`

## 9.2 发布点击后未确认成功

- 保持小红书创作页在前台
- 重试发布
- 检查 MCP `downloads/debug` 截图

## 9.3 图片上传失败

- 优先使用本地图片路径（绝对路径最稳）
- 远程图片需可直接访问且为图片 MIME

## 9.4 第三方搜索 API 不可用

- 主服务会回退到 Mock 数据，便于链路联调
- 生产使用前请配置稳定供应商 Key

## 10. 许可证

按你的发布计划补充，例如 `MIT`、`Apache-2.0` 或私有许可证。
