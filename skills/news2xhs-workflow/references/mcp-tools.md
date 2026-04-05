# MCP Tools

## Role

Use MCP as the execution layer. Do not treat it as the workflow owner.

The main service decides when to call a tool. MCP performs the browser action.

## Common Tool Mapping

- Login check
  - MCP tool: `check_login_status`
- QR login
  - MCP tool: `get_login_qrcode`
- Reset login state
  - MCP tool: `delete_cookies`
- Publish image post
  - MCP tool: `publish_content`
- Publish video post
  - MCP tool: `publish_with_video`
- Search Xiaohongshu feeds
  - MCP tool: `search_feeds`
- Read feed details
  - MCP tool: `get_feed_detail`
- Read user profile
  - MCP tool: `user_profile`
- Interaction actions
  - MCP tools: `like_feed`, `favorite_feed`, `post_comment_to_feed`, `reply_comment_in_feed`

## Main-Service Mapping

The main service reaches MCP through:

- `XhsMcpClient`
- MCP endpoint: `/mcp`
- RPC methods: `initialize`, `tools/list`, `tools/call`

## Usage Rules

- Always prefer the existing client wrapper over hand-written MCP payloads when working inside the app.
- Reuse the tool schema already exposed by `xiaohongshu-mcp-python`.
- When changing publish behavior, update the main service and MCP expectations together.
- Do not move business state into MCP.
