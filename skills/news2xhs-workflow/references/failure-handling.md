# Failure Handling

## Publish Failures

Check in this order:

1. Is the draft approved?
2. Is Xiaohongshu logged in?
3. Is the cover image valid?
4. Did the MCP tool return a structured error?
5. Did Playwright hit page-change or risk-control issues?

## Common Failure Sources

- login expired
- cover path invalid
- remote image URL is not directly usable
- title/content exceeds platform constraints
- Xiaohongshu page structure changed
- platform risk control blocked the session

## Recovery Strategy

- Keep publish task history.
- Preserve friendly error messages for the main service.
- Keep raw error payloads when possible for debugging.
- If automation is blocked by page or network risk control, stop and surface the issue instead of retrying blindly.

## Design Rule

When adding new workflow branches, prefer:

- keeping the state transition in the main service
- keeping browser actions in MCP
- keeping troubleshooting notes in this reference
