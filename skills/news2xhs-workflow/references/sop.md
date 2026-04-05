# SOP

## End-to-End Flow

The current News2XHS process is:

1. Fetch hot news.
2. Select the search route for the topic.
3. Store news items.
4. Generate a Xiaohongshu draft.
5. Generate or upload a cover image.
6. Hand off for manual review.
7. Approve or reject the draft.
8. Check Xiaohongshu login state.
9. Publish through MCP-backed browser automation.
10. Record publish result and expose task status.

## Stage Meanings

- `research`: collect hot news and pick the search strategy
- `draft`: generate or edit the Xiaohongshu draft
- `cover`: attach generated or uploaded cover media
- `review`: human review and state transition
- `publish`: perform login check and publish
- `debug`: inspect failed runs or platform issues

## Main-Service Ownership

The main service owns:

- API routes
- database state
- draft lifecycle
- review lifecycle
- publish task records
- scheduler startup

The MCP service owns:

- MCP protocol endpoint
- tool registration
- Playwright browser automation
- concrete Xiaohongshu page actions

## Default Decision Path

When no special instruction is given:

1. Start from research if there is no stored news.
2. Start from draft if news already exists.
3. Start from review if a draft exists but is not approved.
4. Start from publish only when the draft is already approved.

## Files To Read For Each Stage

- Research: `../../News_xiaohongshu/app/services/search_selector.py`, `../../News_xiaohongshu/app/services/news_service.py`
- Draft: `../../News_xiaohongshu/app/services/draft_service.py`
- Cover: `../../News_xiaohongshu/app/services/image_generation_service.py`
- Review: `../../News_xiaohongshu/app/api/routes.py`
- Publish: `../../News_xiaohongshu/app/services/publish_service.py`, `../../News_xiaohongshu/app/services/xhs_mcp_client.py`
- MCP execution: `../../xiaohongshu-mcp-python/app/tools.py`, `../../xiaohongshu-mcp-python/app/browser_automation.py`
