# xiaohongshu-mcp-python

Pure Python replacement of `xiaohongshu-mcp` (MCP Streamable HTTP style), used to avoid Go binary runtime issues on Windows.

## 1. Environment

Run in your conda env:

```cmd
conda activate Xiaohhongshu
cd /d C:\Users\admin\Desktop\BettaFish-main\xiaohongshu-mcp-python
```

## 2. Install

```cmd
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 3. Configure

```cmd
copy .env.example .env
```

Recommended defaults are already in `.env.example`.

## 4. Start MCP server

```cmd
uvicorn app.main:app --host 0.0.0.0 --port 18060
```

Health check:

```cmd
curl http://127.0.0.1:18060/health
```

## 5. MCP protocol quick check

Initialize:

```cmd
curl -X POST http://127.0.0.1:18060/mcp ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/json, text/event-stream" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\"}}"
```

Then call `tools/list` with returned `Mcp-Session-Id`.

## 6. Tool parity (13 tools)

- `check_login_status`
- `get_login_qrcode`
- `delete_cookies`
- `publish_content`
- `publish_with_video`
- `list_feeds`
- `search_feeds`
- `get_feed_detail`
- `user_profile`
- `post_comment_to_feed`
- `reply_comment_in_feed`
- `like_feed`
- `favorite_feed`

## 7. Connect from News_xiaohongshu

In `News_xiaohongshu/.env`:

```env
XHS_MCP_BASE_URL=http://127.0.0.1:18060
XHS_MCP_API_KEY=
```

`XHS_MCP_API_KEY` can stay empty for local deployment.
