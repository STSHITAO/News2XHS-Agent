---
name: news2xhs-workflow
description: Execute the News2XHS content-ops SOP for topic research, draft generation, cover handling, review handoff, and Xiaohongshu publishing with MCP tools. Use when working inside the News2XHS-Agent project to run, refine, or explain the end-to-end workflow.
---

# News2XHS Workflow

Run the News2XHS SOP as a controlled workflow, not as free-form tool use.

Use this skill when the task involves any of:

- fetching hot news and turning it into Xiaohongshu drafts
- deciding which search route to use for a topic
- preparing a draft for review or publish
- checking Xiaohongshu login or calling MCP publishing tools
- explaining or updating the News2XHS workflow inside this repo

## Workflow

Follow this order unless the user explicitly asks to start from a later step:

1. Confirm the operating stage: `research`, `draft`, `cover`, `review`, `publish`, or `debug`.
2. Read the current SOP in [sop.md](./references/sop.md).
3. If the task touches platform automation, read [mcp-tools.md](./references/mcp-tools.md).
4. If the task touches review gates or publish safety, read [review-rules.md](./references/review-rules.md).
5. If something fails, read [failure-handling.md](./references/failure-handling.md).

## Operating Rules

- Treat `News_xiaohongshu` as the workflow owner.
- Treat `xiaohongshu-mcp-python` as the tool execution layer.
- Do not bypass draft review when the workflow expects manual approval.
- Do not publish unless login, cover image, and draft status are all valid.
- Prefer calling existing API routes and services instead of inventing parallel logic.
- Preserve the current state machine unless the user explicitly asks for a workflow redesign.

## Project Map

Use these locations as the source of truth:

- Main service: [`../../News_xiaohongshu`](../../News_xiaohongshu)
- MCP service: [`../../xiaohongshu-mcp-python`](../../xiaohongshu-mcp-python)
- Main API routes: [`../../News_xiaohongshu/app/api/routes.py`](../../News_xiaohongshu/app/api/routes.py)
- Draft flow: [`../../News_xiaohongshu/app/services/draft_service.py`](../../News_xiaohongshu/app/services/draft_service.py)
- Publish flow: [`../../News_xiaohongshu/app/services/publish_service.py`](../../News_xiaohongshu/app/services/publish_service.py)
- MCP client: [`../../News_xiaohongshu/app/services/xhs_mcp_client.py`](../../News_xiaohongshu/app/services/xhs_mcp_client.py)
- MCP tool registry: [`../../xiaohongshu-mcp-python/app/tools.py`](../../xiaohongshu-mcp-python/app/tools.py)
- Browser automation: [`../../xiaohongshu-mcp-python/app/browser_automation.py`](../../xiaohongshu-mcp-python/app/browser_automation.py)

## Typical Requests

- "Fetch hot news for a topic and generate a draft."
- "Check whether this draft is publish-ready."
- "Map this API to the MCP tool it should call."
- "Explain the News2XHS workflow for an interview."
- "Update the publish SOP without breaking review gates."

## Notes

- Keep the skill focused on process and decision rules.
- Keep implementation details in project code, not in the skill body.
- Add new references only when the workflow gains a genuinely new branch.
