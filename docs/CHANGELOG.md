# TechSensing Changelog

## 2026-04-15 — Product Improvements

### Removed
- **USPTO Patent Search** — consolidated into Google Patents (single patent source)
- **EPO Patent Search** — consolidated into Google Patents
- **DEV.to** — removed from default pipeline (source file retained for future opt-in)

### Changed
- **YouTube enrichment** — now opt-in via `include_videos` toggle (default off)
- **Source Discovery TTL** — reduced from 180 days to 75 days for fresher source lists
- **Google Patents authority** — set to 0.85 in signal scoring (was USPTO at 0.9)
- **Parallel ingest** — all 8 sources now fetched via `asyncio.gather()` (both pipelines)
- **Semantic dedup** — added TF-IDF cosine similarity tier (threshold 0.65, requires scikit-learn)
- **Signal scoring** — now async, incorporates user source feedback modifiers
- **Report generation** — supports stakeholder-specific audience prompts (CTO, developer, etc.)

### Added
- **Report confidence scoring** — `report_confidence` field (high/medium/low) with factor breakdown
- **Technology lifecycle detection** — source-type heuristic (research → prototype → early_adoption → mainstream)
- **Funding signal enrichment** — DDG-powered funding/investment signal search for radar items
- **Source quality feedback** — upvote/downvote sources; feedback adjusts authority weights (±0.3)
- **Cross-domain dashboard** — aggregated view across all tracked domains (`/sensing/dashboard`)
- **Natural language query** — "Ask your radar" LLM-powered Q&A over stored reports (`/sensing/query`)
- **Stakeholder role selector** — audience toggle (General, CTO, Engineering Lead, Developer, PM)
- **Platform status page** — auto-generated capabilities summary (`/sensing/platform-status`)

### Frontend
- Confidence badge in report header
- Lifecycle stage pills on radar item details
- Funding badge on funded radar items
- Source feedback thumbs on notable articles
- YouTube toggle switch in config panel
- Audience/stakeholder role dropdown in config panel
- "Ask your radar" query bar above domain selector
- Dashboard tab with cross-domain card grid

### Archived
- `docs/tech-sensing-improvement-plan.md` → `docs/archive/tech-sensing-improvement-plan-v1.md`
