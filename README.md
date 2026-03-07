# News2XHS-Agent

面向小红书内容运营场景的半自动自主发布系统。项目将新闻检索、草稿生成、封面生成、人工审核与平台发布串成统一流程，并通过本地 MCP 服务驱动浏览器自动化执行，形成从内容生成到页面发布的完整闭环。

## 项目组成

仓库由两个服务组成：

- `News_xiaohongshu`：主服务，负责热点抓取、草稿生成、封面处理、审核流转、发布调度与管理后台。
- `xiaohongshu-mcp-python`：MCP 自动化服务，负责登录检查、二维码登录、图文发布、搜索、互动等小红书浏览器操作。

## 核心能力

### 1. 新闻到草稿的生成链路

- 支持从 `Anspire / Bocha / Tavily / Mock` 等搜索源抓取热点新闻。
- 使用搜索路由 Agent 为不同查询选择合适的搜索工具和时间范围。
- 将热点新闻整理为小红书草稿，并维护 `pending_review -> approved -> published / failed` 状态流转。

### 2. 封面生成与素材管理

- 支持在草稿生成后自动触发封面生成。
- 可接入本地 Mock 图像生成或 OpenAI 兼容图像模型。
- 支持本地上传封面图，并将封面路径回写到草稿。

### 3. MCP 工具接入

- 主服务通过 `XhsMcpClient` 调用本地 MCP 服务。
- MCP 服务基于 `FastAPI + Playwright` 实现工具注册、JSON-RPC 调度和浏览器自动化。
- 已封装登录检查、二维码登录、图文发布、搜索、点赞、收藏、评论等工具。

### 4. 发布工作流闭环

- 将“新闻检索 -> 草稿生成 -> 封面生成 -> 人工审核 -> 发布执行”串成统一工作流。
- 发布前会校验草稿状态、封面有效性与登录状态。
- 发布失败时会返回更友好的错误提示，并保留调试截图路径，便于排查平台风控、页面结构变化等问题。

## 整体架构

```text
[News_xiaohongshu 主服务]
   ├─ 热点抓取 / 搜索路由
   ├─ 草稿生成 / 编辑 / 审核
   ├─ 封面生成 / 本地上传
   └─ 发布调度
            |
            v
[xiaohongshu-mcp-python]
   ├─ MCP 协议接口
   ├─ Tool 列表与调用分发
   └─ Playwright 浏览器自动化
            |
            v
[小红书创作中心页面]
```

## 目录结构

```text
News2XHS-Agent/
├── News_xiaohongshu/          # 主服务：管理台 + 业务 API
├── xiaohongshu-mcp-python/    # MCP 自动化服务
└── README.md
```

## 环境要求

- Python `3.10+`
- pip
- Playwright Chromium
- 数据库：
  - 本地调试可使用 SQLite
  - 持续运行建议使用 MySQL

## 启动方式

### 1. 启动 MCP 自动化服务

```bash
cd xiaohongshu-mcp-python
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

安装依赖并初始化浏览器：

```bash
pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
```

启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 18060
```

验证：

- `http://127.0.0.1:18060/health`
- `http://127.0.0.1:18060/mcp`

### 2. 启动主服务

```bash
cd News_xiaohongshu
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

安装依赖并复制配置：

```bash
pip install -r requirements.txt
copy .env.example .env
```

建议至少配置：

- `SEARCH_TOOL_TYPE`
- 对应搜索服务 API Key
- `XHS_MCP_BASE_URL=http://127.0.0.1:18060`
- 数据库连接参数

启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 5108 --reload
```

验证：

- 管理页：`http://127.0.0.1:5108/admin`
- 草稿编辑页：`http://127.0.0.1:5108/admin/draft/{draft_id}`
- OpenAPI：`http://127.0.0.1:5108/docs`
- 健康检查：`http://127.0.0.1:5108/health`

## 关键配置

### 主服务 `News_xiaohongshu/.env`

- `SEARCH_TOOL_TYPE=AnspireAPI|BochaAPI|TavilyAPI|MockAPI`
- `ENABLE_FUNCTION_CALLING=True|False`
- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `QWEN_MODEL`
- `IMAGE_GEN_PROVIDER=MockAPI|OpenAICompatible`
- `IMAGE_GEN_API_KEY`
- `IMAGE_GEN_BASE_URL`
- `IMAGE_GEN_MODEL`
- `XHS_MCP_BASE_URL`
- `XHS_MCP_API_KEY`
- `PUBLISH_GUARD_TOKEN`

### MCP 服务 `xiaohongshu-mcp-python/.env`

- `APP_PORT=18060`
- `HEADLESS`
- `PUBLISH_HEADLESS`
- `BROWSER_TIMEOUT_MS`
- `STORAGE_STATE_PATH`
- `DOWNLOAD_DIR`

## 常用接口

### 主服务

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
- `GET /api/xhs/login-status`
- `GET /api/xhs/login-qrcode`
- `POST /api/xhs/reset-login`
- `POST /api/uploads/cover`
- `POST /api/cover/generate`

### MCP 服务

- `GET /health`
- `POST /mcp`

常用工具：

- `check_login_status`
- `get_login_qrcode`
- `delete_cookies`
- `publish_content`
- `publish_with_video`
- `search_feeds`
- `get_feed_detail`
- `like_feed`
- `favorite_feed`

## 典型使用流程

1. 启动 `xiaohongshu-mcp-python`。
2. 启动 `News_xiaohongshu`。
3. 进入管理页检查登录状态。
4. 如未登录，调用二维码登录接口完成扫码。
5. 抓取热点新闻并生成草稿。
6. 自动或手动补充封面图。
7. 在草稿页编辑内容并审核通过。
8. 调用发布接口，检查发布状态与错误提示。

## 测试

主服务：

```bash
cd News_xiaohongshu
pytest tests/test_api.py -q
```

MCP 服务：

```bash
cd xiaohongshu-mcp-python
pytest tests/test_mcp_protocol.py tests/test_tools_dispatch.py -q
```

## 说明

- 仓库默认不提交 `.env`、数据库文件、运行日志、下载目录、上传封面目录与登录态文件。
- 发布链路依赖小红书页面结构与账号状态，建议在真实环境下保留人工审核环节。
- 如果你只想联调业务流程，可以先使用 `MockAPI` 搜索与封面生成配置完成端到端验证。
