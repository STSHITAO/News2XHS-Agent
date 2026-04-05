# Review Rules

## Draft State Model

Important draft states:

- `pending_review`
- `approved`
- `rejected`
- `published`
- `failed`

## Review Gate

Before publish, verify all of these:

- draft exists
- draft status is `approved`
- title is non-empty and within platform limit
- content is non-empty and within platform limit
- cover image path or URL is valid
- Xiaohongshu login is valid

## Human-in-the-Loop Rule

Do not silently skip manual review.

If the task is “fully automate publish,” keep the review gate explicit unless the user clearly requests removal of that safeguard.

## When To Reject

Reject or send back for edit when:

- title is too long or too vague
- content is obviously unfinished
- topic and content are misaligned
- cover image is missing or invalid
- publish prerequisites are not met
