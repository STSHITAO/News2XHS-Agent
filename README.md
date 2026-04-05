# News2XHS-Agent

面向小红书内容运营场景的半自动内容发布系统。项目打通新闻检索、草稿生成、封面处理、人工审核与平台发布流程，并通过本地 MCP 服务驱动浏览器自动化执行，形成从内容生产到页面发布的完整闭环。

## 项目组成

当前仓库由三个部分组成：

- `News_xiaohongshu`：主服务，负责工作流编排、草稿管理、审核状态、发布调度与管理后台
- `xiaohongshu-mcp-python`：本地 MCP 服务，负责登录检查、二维码登录、图文发布、搜索与互动等平台操作
- `skills/news2xhs-workflow`：将发布 SOP 抽象为可复用 Skill，沉淀阶段划分、审核规则、MCP 工具映射与失败处理逻辑

## 系统结构

```text
[News_xiaohongshu]
   |- 热点抓取 / 搜索路由
   |- 草稿生成 / 编辑 / 审核
   |- 封面生成 / 本地上传
   |- 发布调度 / 状态管理
            |
            v
[xiaohongshu-mcp-python]
   |- MCP 协议入口
   |- Tool 注册与分发
   |- Playwright 浏览器自动化
            |
            v
[小红书创作中心页面]

[skills/news2xhs-workflow]
   |- SOP
   |- 审核规则
   |- MCP 工具映射
   |- 失败处理
```

## 核心能力

### 1. 工作流编排

- 主服务统一编排“新闻检索 -> 草稿生成 -> 封面处理 -> 人工审核 -> 发布执行”链路
- 草稿、审核状态与发布任务可独立查询和推进
- 发布前会校验草稿状态、封面有效性与小红书登录状态

### 2. Agent 与 Skill 抽象

- 在搜索路由等环节引入 Agent 决策逻辑
- 将发布 SOP 抽象为项目内 Skill，形成面向 Agent 的流程知识层
- Skill 当前包含：
  - `sop.md`
  - `mcp-tools.md`
  - `review-rules.md`
  - `failure-handling.md`

### 3. MCP 设计与接入

- 自主实现本地 MCP 服务与客户端调用链路
- 将登录检查、二维码登录、图文发布、内容搜索、互动等平台操作封装为标准化工具
- 主服务通过 `XhsMcpClient` 调用 MCP 服务，MCP 再驱动 Playwright 执行真实页面操作

### 4. 执行闭环

- 结合 Tool Calling 与 `Playwright` 浏览器自动化，完成从内容生成到平台页面发布的执行闭环
- 发布失败时保留友好错误信息与调试信息，便于排查平台风控、页面变更或图片资源异常

## 目录结构

```text
News2XHS-Agent/
├── News_xiaohongshu/              # 主服务：管理后台 + 业务 API
├── xiaohongshu-mcp-python/        # MCP 自动化服务
├── skills/
│   └── news2xhs-workflow/
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       └── references/
│           ├── sop.md
│           ├── mcp-tools.md
│           ├── review-rules.md
│           └── failure-handling.md
└── README.md
```

## 环境要求

- Python `3.10+`
- pip
- Playwright Chromium
- 数据库：
  - 本地调试可使用 SQLite
  - 长期运行建议使用 MySQL

## 启动方式

### 1. 启动 MCP 服务

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

至少需要配置：

- `SEARCH_TOOL_TYPE`
- 对应搜索服务的 API Key
- `XHS_MCP_BASE_URL=http://127.0.0.1:18060`
- 数据库连接参数

启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 5108 --reload
```

访问：

- 管理页：`http://127.0.0.1:5108/admin`
- 草稿编辑页：`http://127.0.0.1:5108/admin/draft/{draft_id}`
- OpenAPI：`http://127.0.0.1:5108/docs`
- 健康检查：`http://127.0.0.1:5108/health`

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
- `user_profile`
- `like_feed`
- `favorite_feed`

## Skill 使用方式

项目内 Skill 位于：

- `skills/news2xhs-workflow`

它不会自动接管主服务运行时逻辑，而是作为面向 Agent 的显式流程知识层使用。使用时可显式带路径，例如：

```text
Use $news2xhs-workflow at /abs/path/to/News2XHS-Agent/skills/news2xhs-workflow to run the publishing SOP.
```

## 典型流程

1. 启动 `xiaohongshu-mcp-python`
2. 启动 `News_xiaohongshu`
3. 检查小红书登录状态
4. 若未登录，获取二维码完成扫码
5. 抓取热点新闻并生成草稿
6. 自动或手动补全封面
7. 进行人工审核
8. 调用发布接口并查询发布状态

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

- 仓库默认不提交 `.env`、数据库文件、运行日志、下载目录、上传封面目录与登录态文件
- 发布链路依赖小红书页面结构与账号状态，建议在真实环境下保留人工审核环节
- 若只想联调主流程，可先使用 `MockAPI` 完成端到端验证
