# Getting Started

BotCheck documentation now ships with the same web application deployment. This keeps product docs, screenshots, and rollout state aligned with the actual version your operators are using.

## How This Docs Framework Works

- Documentation pages live as Markdown files in `web/content/docs/`.
- Navigation and page metadata live in `web/src/lib/docs.ts`.
- The app serves docs from `/docs/...` using the same deployment as the dashboard.
- Junior contributors can add new pages without touching the main app shell.

## Authoring Workflow

1. Add a new Markdown file under `web/content/docs/`.
2. Register it in `web/src/lib/docs.ts` with a title, description, section, order, and slug.
3. Keep headings shallow and practical.
4. Use fenced code blocks for CLI snippets, API payloads, and YAML examples.

## Supported Markdown

- `#`, `##`, and `###` headings
- paragraphs
- bulleted and numbered lists
- block quotes
- fenced code blocks
- inline code like `uv run pytest`
- links like [Schedules](/schedules)

## Suggested Initial Docs Set

- platform overview
- scenario builder workflow
- AI scenarios workflow
- packs and schedules
- admin and audit surfaces
- speech providers and transport profiles

> This page is the starter template. Replace or extend it as real product documentation lands.
