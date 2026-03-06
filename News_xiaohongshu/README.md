# News_xiaohongshu

基于 FastAPI 的热点新闻检索与小红书半自动发布系统。

核心能力：
- 热点检索（Anspire/Bocha/Tavily 路由）
- 草稿生成（可启用 Function Calling）
- 自动文生图封面（OpenAI Compatible，例如 ModelScope Qwen-Image）
- 小红书发布（通过本地 Python MCP 服务）

## 1. 目录与服务

当前建议目录（你已经迁移后的结构）：

- 主服务：`C:\Users\admin\Desktop\BettaFish-main\News_xiaohongshu_mcp\News_xiaohongshu`
- MCP 服务：`C:\Users\admin\Desktop\BettaFish-main\News_xiaohongshu_mcp\xiaohongshu-mcp-python`

运行时是两个服务：

- 主服务（本项目）：默认 `5108`
- MCP 服务（小红书自动化）：`18060`

## 2. 环境准备

推荐使用你现有环境：

```cmd
conda activate Xiaohhongshu
```

安装依赖：

```cmd
cd /d C:\Users\admin\Desktop\BettaFish-main\News_xiaohongshu_mcp\News_xiaohongshu
pip install -r requirements.txt
```

## 3. 配置 `.env`

复制模板：

```cmd
copy .env.example .env
```

至少要填这些：

- 数据库
  - `DB_DIALECT=mysql`
  - `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`
- 检索供应商（至少一个）
  - `ANSPIRE_API_KEY` 或 `BOCHA_WEB_SEARCH_API_KEY` 或 `TAVILY_API_KEY`
- 文生图（若要自动封面）
  - `IMAGE_GEN_PROVIDER=OpenAICompatible`
  - `IMAGE_GEN_API_KEY`
  - `IMAGE_GEN_BASE_URL`
  - `IMAGE_GEN_MODEL`
- MCP 地址
  - `XHS_MCP_BASE_URL=http://127.0.0.1:18060`

自动封面相关开关：

```env
AUTO_GENERATE_COVER_ON_DRAFT=True
AUTO_GENERATE_COVER_STRICT=False
```

说明：

- `AUTO_GENERATE_COVER_ON_DRAFT=True`：调用草稿生成接口时自动生成封面并写入草稿。
- `AUTO_GENERATE_COVER_STRICT=False`：即使文生图失败，也会保留草稿（错误写在返回字段里）。

## 4. 启动服务

### 4.1 启动 MCP 服务（先启动）

```cmd
cd /d C:\Users\admin\Desktop\BettaFish-main\News_xiaohongshu_mcp\xiaohongshu-mcp-python
uvicorn app.main:app --host 0.0.0.0 --port 18060
```

健康检查：

```cmd
curl http://127.0.0.1:18060/health
```

### 4.2 启动主服务

```cmd
cd /d C:\Users\admin\Desktop\BettaFish-main\News_xiaohongshu_mcp\News_xiaohongshu
uvicorn app.main:app --host 0.0.0.0 --port 5108 --reload
```

健康检查：

```cmd
curl http://127.0.0.1:5108/health
```

## 5. 网页使用流程（推荐）

打开：

- 管理页：`http://127.0.0.1:5108/admin`
- 草稿页：`http://127.0.0.1:5108/admin/draft/{draft_id}`

操作顺序：

1. 在管理页确认系统状态正常。
2. 若显示未登录小红书，先在管理页完成扫码登录（或你已登录则跳过）。
3. 点击“热点抓取”。
4. 点击“生成草稿”。
   - 若自动封面成功，会提示“自动封面已生成”。
5. 进入草稿编辑页检查标题、正文、标签、封面。
6. 执行 `Approve`。
7. 执行 `Publish`。
8. 查看发布状态（成功时会返回 `succeeded`）。

## 6. API 快速使用（CMD）

### 6.1 抓取热点

```cmd
curl -X POST http://127.0.0.1:5108/api/news/hot/fetch ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"社会热点\",\"limit\":5,\"period\":\"24h\"}"
```

### 6.2 生成草稿（自动触发文生图封面）

```cmd
curl -X POST http://127.0.0.1:5108/api/drafts/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"topic\":\"社会热点\",\"max_news_items\":3}"
```

返回会包含：

- `auto_cover_generated`
- `auto_cover_provider`
- `auto_cover_error`

### 6.3 审核草稿

```cmd
curl -X POST http://127.0.0.1:5108/api/drafts/1/approve ^
  -H "Content-Type: application/json" ^
  -d "{\"notes\":\"ready to publish\"}"
```

### 6.4 发布草稿

如果未设置 `PUBLISH_GUARD_TOKEN`：

```cmd
curl -X POST http://127.0.0.1:5108/api/publish/1
```

如果设置了 `PUBLISH_GUARD_TOKEN`：

```cmd
curl -X POST http://127.0.0.1:5108/api/publish/1 ^
  -H "X-Publish-Token: your-token"
```

### 6.5 查询发布状态

```cmd
curl http://127.0.0.1:5108/api/publish/1/status
```

## 7. 常见问题

### 7.1 `publish ... not confirmed`

含义：点击发布后平台未回传成功/审核页状态。  
处理：保持小红书创作页前台可见，避免页面切换，重试发布。

### 7.2 `creator center not logged in`

含义：MCP 浏览器会话未登录。  
处理：在管理页重新扫码登录。

### 7.3 自动封面失败但草稿仍生成

这是 `AUTO_GENERATE_COVER_STRICT=False` 的预期行为。  
你可以查看 `auto_cover_error`，或手工上传封面再发布。

## 8. 一次性全链路验收清单

满足下面 8 条即可判定通过：

1. `GET /health` 返回 200。
2. `GET /api/system/status` 返回 200。
3. `GET /api/xhs/login-status` 为 `logged_in`。
4. `POST /api/news/hot/fetch` 返回 `count >= 1`。
5. `POST /api/drafts/generate` 返回 `success=true`。
6. 返回中 `auto_cover_generated=true`（或失败时有 `auto_cover_error`）。
7. `POST /api/drafts/{id}/approve` 成功。
8. `POST /api/publish/{id}` 后 `GET /api/publish/{id}/status` 为 `succeeded`。

