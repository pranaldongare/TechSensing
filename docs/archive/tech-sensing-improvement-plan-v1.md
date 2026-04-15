# Tech Sensing — Product Improvement Plan

## 1. Current State Assessment

### What We Have (Feature Inventory)

| Capability | Implementation | Maturity |
|---|---|---|
| Multi-source ingestion | RSS (5 general + 30 domain-specific feeds) + DuckDuckGo search | Solid |
| Deduplication | URL normalization + fuzzy title matching (85% threshold) | Basic |
| Full text extraction | trafilatura with fallback to snippet | Solid |
| LLM classification | Batch classification (6/batch) with radar placement | Solid |
| Report generation | Structured multi-section report via LLM | Solid |
| Relevance verification | Post-report LLM filter for off-topic content | New |
| Technology Radar viz | SVG interactive radar (4 quadrants x 4 rings) | Solid |
| PDF export | Multi-section styled PDF via pdfmake | Solid |
| Keyword filtering | Must Include / Don't Include with pipeline + LLM integration | Solid |
| Domain-aware feeds | Dynamic feed selection based on domain keywords | Solid |
| Date range control | Last Week / Last Month / Custom days | Solid |
| Report history | File-based storage, list/load/delete/regenerate | Solid |
| Real-time progress | Socket.IO events + polling fallback (6-stage pipeline) | Solid |

### What We Don't Have (Gaps)

| Gap | Impact | Competitive Relevance |
|---|---|---|
| No historical comparison between reports | Can't show technology movement over time | ThoughtWorks tracks blip movement; ITONICS has timeline views |
| No additional data sources (GitHub, patents, papers, jobs) | Missing key adoption signals | Cypris, CB Insights, Elicit all use multi-source triangulation |
| No semantic deduplication | Similar articles with different titles slip through | Feedly Leo, AlphaSense use AI-based dedup |
| No collaborative features | Single-user, no team input or discussion | ITONICS has voting, comments, structured decision workflows |
| No scheduling/automation | Manual trigger only | Feedly, AlphaSense, CB Insights offer continuous monitoring |
| No technology tracking across runs | Each report is an isolated snapshot | All enterprise tools track entities over time |
| Radar visualization not in PDF | PDF has table but not the visual radar | ITONICS exports to PPT with visual radar |
| No signal strength indicators | All sources weighted equally | Elicit has quality signals; Consensus has Consensus Meter |
| No org-context awareness | Generic scanning, no awareness of user's tech stack | This is a major market gap — almost nobody does this well |

---

## 2. Competitive Positioning

### Where We Sit

```
                    Manual Curation ◄──────────────► Fully Automated
                         │
    ThoughtWorks BYOR ───┤
    ITONICS ─────────────┤                              ┌─ Feedly (content only)
                         │                              │
    Gartner ─────────────┤         ┌── US (here) ──┐   │
                         │         │                │   │
                         │         │  Automated +   │   ├─ TopicRadar (raw data)
                         │         │  Radar Viz +   │   │
                         │         │  Assessment    │   └─ npm/pip trends (narrow)
                         │         └────────────────┘
    CB Insights ─────────┤                              ┌─ AlphaSense (financial)
    Cypris ──────────────┤                              │
    Wellspring ──────────┤                              └─ Elicit (academic)
                         │
                  Expensive ◄───────────────────────► Affordable
```

**Our unique position:** We combine automated multi-source data collection + AI-powered radar assessment + interactive visualization at zero marginal cost (self-hosted, local LLM). No other product occupies this exact intersection.

### Key Competitive Advantages to Protect
1. **Self-hosted / local LLM** — no per-query API costs, full data privacy
2. **End-to-end automation** — from raw sources to structured radar in one click
3. **Integrated into existing platform** — not a standalone tool, leverages existing auth/UI/infra

### Key Competitive Disadvantages to Address
1. **Single-source signal** — only RSS + web search (no patents, papers, GitHub, jobs)
2. **Snapshot-only** — no temporal tracking, no movement history
3. **Single-user** — no collaboration, no organizational context
4. **Reactive-only** — manual trigger, no scheduled/continuous monitoring

---

## 3. Improvement Plan

### Phase 1: Foundation Hardening (High Impact, Low Effort)

These improvements strengthen the existing feature without adding new complexity.

#### 1.1 — Radar Movement Tracking

**Problem:** Each report is an isolated snapshot. The `moved_in` field on radar items exists but is never populated. Users can't see how technologies are evolving across reports.

**Solution:** When generating a new report, load the most recent previous report for the same domain and compare radar items by name. Populate `moved_in` (e.g., "Assess" if a tech moved from Assess to Trial). In the UI, show movement indicators (arrows up/down) on radar blips and in the report renderer.

**Value:** This is what makes the ThoughtWorks Radar valuable — not just where things are, but where they're moving. It turns a static snapshot into a dynamic intelligence tool.

**Scope:**
- Backend: Load previous report in pipeline, match technologies by name (fuzzy), compute ring changes
- Frontend: Movement arrows on radar blips, "moved from X" badges in renderer
- PDF: Movement column in radar table

---

#### 1.2 — Radar Visualization in PDF

**Problem:** The PDF export has a table of radar items but not the actual radar visualization. The visual radar is the signature element of the feature.

**Solution:** Render the SVG radar to a canvas, export as PNG, and embed in the PDF. Alternatively, generate a simplified radar layout directly in pdfmake using circles and positioned text.

**Value:** Makes the PDF a complete, shareable artifact. The radar visual is immediately recognizable and communicates the entire landscape at a glance.

**Scope:**
- Frontend: SVG-to-canvas-to-PNG conversion, embed in PDF before the radar table section

---

#### 1.3 — Report Comparison View

**Problem:** Users can view individual reports but cannot compare two reports side-by-side to see what changed.

**Solution:** Add a "Compare" button that lets users select two reports (from history) and renders a diff view showing: new technologies added, technologies removed, ring movements, new/removed trends, new/removed market signals.

**Value:** Answers the critical question: "What changed since last time?" This is the core value of periodic sensing.

**Scope:**
- Frontend: New comparison view/tab, diff algorithm for radar items/trends/signals
- No backend changes needed (both reports already stored)

---

#### 1.4 — Scheduled / Recurring Reports

**Problem:** Users must manually trigger each report. For continuous sensing, they need to remember to come back.

**Solution:** Allow users to set up a schedule (weekly, biweekly, monthly) for automatic report generation. Store schedule config per user. Backend cron job checks for due reports and runs the pipeline.

**Value:** Transforms the feature from a point-in-time tool into a continuous intelligence system. This is what separates professional tools (Feedly, AlphaSense) from one-off scripts.

**Scope:**
- Backend: Schedule storage (user config JSON), scheduler task (APScheduler or simple cron check on server startup), auto-trigger pipeline
- Frontend: Schedule toggle in config panel (off / weekly / biweekly / monthly), next run indicator
- Notifications: Email or in-app notification when a scheduled report is ready

---

#### 1.5 — Article Cache & Incremental Ingestion

**Problem:** Every run re-fetches and re-processes all articles, even if most were seen in a previous run. Wastes time and LLM tokens on repeated classification.

**Solution:** Cache ingested articles by URL hash. On subsequent runs, skip articles already classified. Only classify new articles and merge with cached classifications before report generation.

**Value:** Reduces pipeline execution time by 40-70% for recurring reports on the same domain. Makes scheduled reports practical.

**Scope:**
- Backend: Article cache (JSON file or SQLite per user/domain), cache lookup in dedup stage, merge cached + new classifications before report generation
- Cache invalidation: TTL-based (e.g., 30 days) or manual clear

---

### Phase 2: Signal Enrichment (High Impact, Medium Effort)

These improvements significantly expand the intelligence value by adding new data sources.

#### 2.1 — GitHub Trending Integration

**Problem:** Developer adoption is one of the strongest signals of technology maturity, but we don't capture it. A library trending on GitHub with 5K stars in a week is a stronger signal than an RSS mention.

**Solution:** Add a GitHub data source to the ingestion stage. Fetch trending repositories (via GitHub API or scraping), repository metadata (stars, forks, recent commit activity), and map them to technology radar items.

**Data Points:**
- Trending repos in relevant topics (last week/month)
- Star growth velocity (stars gained in lookback period)
- Contributor count and growth
- Language/framework signals

**Value:** GitHub signals are the most direct proxy for developer adoption. No enterprise tool (CB Insights, AlphaSense, Cypris) captures this — it's a unique differentiator.

**Scope:**
- Backend: New `github_source.py` in sensing module, GitHub API integration (unauthenticated rate limit: 60 req/hr, authenticated: 5000), merge GitHub signals into article pipeline
- Classification prompt update: Include GitHub signals as a separate evidence type

---

#### 2.2 — arXiv / Academic Paper Integration

**Problem:** Breakthrough technologies appear in academic papers 6-18 months before they hit mainstream news. We have arXiv RSS feeds, but they only capture titles/abstracts from the feed — we don't systematically search for papers or extract key findings.

**Solution:** Add arXiv API search (free, no key needed) as a structured data source. Search for papers matching the domain, extract abstracts, and feed them into classification alongside news articles.

**Data Points:**
- Paper title, authors, abstract
- Publication date
- Citation count (via Semantic Scholar API — free)
- "Papers with Code" linkage (bridges theory → implementation)

**Value:** Early signal detection. Technologies in the "Assess" ring often show up in papers first. Elicit and Consensus are paper-only tools — we'd integrate papers alongside news and GitHub for a more complete picture.

**Scope:**
- Backend: arXiv API client, Semantic Scholar API for citation counts, new source type in RawArticle
- Prompt update: Teach classifier to handle academic papers differently (weight innovation potential higher, maturity lower)

---

#### 2.3 — Hacker News Signal Integration

**Problem:** We have an HN RSS feed but it only captures recent front-page items. HN is the premier discussion forum for developer technology assessment — the comments often contain more signal than the article itself.

**Solution:** Use the Algolia HN Search API (free, no key) to search for domain-related discussions. Extract top-voted comments as additional signal. An HN post with 300+ points and substantive discussion is a strong technology signal.

**Data Points:**
- Story title, URL, points, comment count
- Top comments (first 3-5 by score) as supplementary content
- HN-specific engagement metrics

**Value:** Community-validated signal. HN's audience self-selects for technically sophisticated discussion. A technology getting traction on HN is meaningfully different from a PR puff piece on TechCrunch.

**Scope:**
- Backend: Algolia HN API client (`hn.algolia.com/api/v1/search`), comment extraction, new source type
- Low effort — API is simple, free, and well-documented

---

#### 2.4 — Signal Strength / Confidence Score

**Problem:** All articles and signals are treated equally. A breakthrough paper with 500 citations carries the same weight as a random blog post. Users can't distinguish high-confidence signals from noise.

**Solution:** Compute a composite signal strength score for each technology based on multiple factors:
- Source authority (arXiv paper > TechCrunch > random blog)
- Engagement metrics (HN points, GitHub stars, citation count)
- Cross-source corroboration (mentioned in 3+ independent sources = stronger)
- Recency weighting (newer = higher weight within lookback window)

Display signal strength as a visual indicator (1-5 bars or a confidence percentage) on radar items and in the report.

**Value:** Directly addresses the "cutting through the noise" problem identified by Deloitte as the #1 challenge in tech sensing. This is what separates intelligence from aggregation.

**Scope:**
- Backend: Signal strength calculator in pipeline (post-classification, pre-report), scoring rubric
- Frontend: Signal strength bars/indicator on radar blips and in report renderer
- Prompt: Include signal strength context for report generation

---

### Phase 3: User Experience (Medium Impact, Medium Effort)

These improvements make the feature more usable and engaging.

#### 3.1 — Interactive Report with Drill-Through

**Problem:** The report renderer and radar are in separate tabs. Users can't click a radar blip and immediately see its detailed analysis, or click a trend and see the supporting articles.

**Solution:** Make the radar interactive with the report. Clicking a radar blip scrolls to and highlights its Technology Deep Dive section. Clicking a trend shows its evidence articles. Add anchor links between related sections (e.g., market signal → related radar items).

**Value:** Transforms the report from a linear document into an explorable intelligence dashboard. This is the UX pattern used by CB Insights and ITONICS.

**Scope:**
- Frontend: Anchor links between sections, click handlers on radar blips that switch to report tab and scroll to section, highlight animation

---

#### 3.2 — Export to PowerPoint

**Problem:** PDF is read-only. For presentations and stakeholder communication, users need editable slides.

**Solution:** Generate a PowerPoint file using a library like pptxgenjs (client-side). Include: title slide, executive summary, radar visualization, key trends, market signals, recommendations.

**Value:** Enterprise users frequently need to present technology landscape insights to leadership. PPT export is offered by ITONICS and is a common request.

**Scope:**
- Frontend: New export option using pptxgenjs, structured slide deck with consistent styling

---

#### 3.3 — Email Digest / Notification

**Problem:** Once a scheduled report is generated, the user has no way to know until they open the app.

**Solution:** When a report completes (especially scheduled ones), send an email digest with the executive summary and key highlights. Include a link to open the full report in the app.

**Value:** Reduces friction for continuous sensing. Users stay informed without needing to actively check. This is a standard feature in Feedly, AlphaSense, and all enterprise tools.

**Scope:**
- Backend: Email service integration (SMTP or SendGrid), digest template, trigger on report completion
- Frontend: Email preference settings

---

#### 3.4 — Custom Feed Management UI

**Problem:** The `feed_urls` and `search_queries` parameters exist in the API but are not exposed in the UI. Power users can't add their own RSS feeds or customize search queries.

**Solution:** Add an "Advanced Sources" collapsible panel in the config card. Allow users to add/remove custom RSS feed URLs and custom search queries. Persist these per-domain so they're loaded on regeneration.

**Value:** Power users and domain experts often know the best sources for their field. Letting them add niche feeds (e.g., a specific company's engineering blog, a niche subreddit) dramatically improves relevance.

**Scope:**
- Frontend: Expandable panel with feed URL and search query chip inputs (same pattern as keywords)
- Backend: Persist custom feeds in report metadata (already supported via `feed_urls` param)

---

### Phase 4: Advanced Intelligence (High Impact, High Effort)

These are differentiating features that move the product toward a true intelligence platform.

#### 4.1 — Multi-Report Technology Timeline

**Problem:** Individual report comparison (Phase 1.3) shows what changed between two points. But users need to see the full trajectory of a technology across all reports — when it first appeared, how it moved through rings, when signals strengthened.

**Solution:** Build a timeline view that aggregates all reports for a domain and plots each technology's ring position over time. Show entry date, ring transitions, and signal strength evolution as a timeline chart.

**Visualization:** Horizontal timeline with technologies as rows, time as the x-axis, and colored dots/lines showing ring position at each report date.

**Value:** This is the single most requested feature in technology management (per ITONICS and Wellspring user research). No freely available tool provides this.

**Scope:**
- Backend: Timeline aggregation endpoint that scans all reports for a domain
- Frontend: New "Timeline" tab alongside Report and Radar, timeline chart using Recharts

---

#### 4.2 — Organization Context Awareness

**Problem:** Reports are generated in a vacuum with no awareness of what technologies the user's organization already uses. A report recommending "Adopt Kubernetes" is useless if the org is already running Kubernetes in production.

**Solution:** Allow users to define their current tech stack (manual input or auto-detect from uploaded package.json / requirements.txt / Dockerfile). The report generation prompt then factors in the org's stack: highlight what's new to them, de-prioritize what they already use, and specifically call out upcoming replacements or complementary tools.

**Value:** This is the most significant market gap identified in competitive research. Almost nobody does this well. It transforms generic industry intelligence into personalized strategic guidance.

**Scope:**
- Frontend: Tech stack input (chip-based, or file upload for auto-detection)
- Backend: Parse tech stack, include in report generation prompt as organizational context
- Prompt: "The user's organization currently uses: [list]. Frame recommendations relative to their existing stack."

---

#### 4.3 — Multi-Agent Deep Dive

**Problem:** The current pipeline generates one report in one pass. For complex domains, users may want to go deeper on a specific technology or trend identified in the initial report.

**Solution:** Add a "Deep Dive" button on any radar item or trend. This triggers a focused secondary pipeline that:
1. Searches specifically for that technology (more targeted queries)
2. Fetches more detailed sources (academic papers, GitHub repos, benchmarks)
3. Generates a focused analysis report with: technical architecture, implementation considerations, vendor comparison, adoption roadmap

**Value:** Mirrors the CB Insights "Deep Analyst" agent pattern. Users often start broad (landscape scan) and then need to go deep on 2-3 specific technologies for decision-making.

**Scope:**
- Backend: New "deep dive" pipeline variant with targeted ingestion and focused prompts
- Frontend: "Deep Dive" button per radar item, separate renderer for focused reports

---

#### 4.4 — Collaborative Radar with Team Input

**Problem:** Technology assessment is inherently a team activity. The ThoughtWorks radar is produced by a Technology Advisory Board, not one person. Our radar is single-user with no way to incorporate team perspectives.

**Solution:** Add lightweight collaboration:
- Share a report via link (read-only)
- Team members can vote on ring placement (agree/disagree)
- Team members can add comments on specific technologies
- Admin can manually override ring positions based on team consensus

**Value:** Transforms the tool from individual research into organizational decision-making. This is the core value proposition of ITONICS Radar.

**Scope:**
- Backend: Sharing tokens, vote/comment storage, override mechanism
- Frontend: Share button, voting UI on radar items, comment threads

---

## 4. Prioritized Roadmap

| Priority | Item | Effort | Impact | Dependencies |
|---|---|---|---|---|
| **P0** | 1.1 Radar Movement Tracking | Small | High | None |
| **P0** | 1.2 Radar Visualization in PDF | Small | Medium | None |
| **P1** | 1.3 Report Comparison View | Medium | High | 1.1 |
| **P1** | 2.3 Hacker News Integration | Small | Medium | None |
| **P1** | 2.4 Signal Strength Score | Medium | High | None |
| **P1** | 3.4 Custom Feed Management UI | Small | Medium | None |
| **P2** | 2.1 GitHub Trending Integration | Medium | High | None |
| **P2** | 1.5 Article Cache & Incremental | Medium | Medium | None |
| **P2** | 3.1 Interactive Report Drill-Through | Medium | Medium | None |
| **P2** | 1.4 Scheduled Reports | Medium | High | 1.5 |
| **P3** | 2.2 arXiv / Academic Paper Integration | Medium | Medium | None |
| **P3** | 3.2 PowerPoint Export | Medium | Medium | None |
| **P3** | 3.3 Email Digest | Medium | Medium | 1.4 |
| **P4** | 4.1 Multi-Report Timeline | Large | High | 1.1, 1.3 |
| **P4** | 4.2 Org Context Awareness | Medium | High | None |
| **P4** | 4.3 Multi-Agent Deep Dive | Large | High | None |
| **P4** | 4.4 Collaborative Radar | Large | Medium | Sharing infra |

---

## 5. Success Metrics

| Metric | Current Baseline | Phase 1 Target | Phase 2 Target |
|---|---|---|---|
| Report generation time | ~20 min | ~12 min (with caching) | ~8 min (incremental) |
| Unique data sources | 2 (RSS + DDG) | 2 | 5 (+ GitHub, HN, arXiv) |
| Report accuracy (off-topic rate) | ~15% items off-topic | <5% (verifier tuning) | <2% (multi-source corroboration) |
| User return rate | N/A (new feature) | Weekly active use | Scheduled + auto |
| Shareable artifacts | PDF only | PDF + radar image | PDF + PPT + email digest |

---

## 6. Key Principles

1. **Signal over noise** — Every improvement should increase the signal-to-noise ratio. More sources are only valuable if they bring stronger signals, not more noise.

2. **Temporal is the differentiator** — Static snapshots are commodity. Movement tracking, timelines, and trajectory analysis are what make technology sensing genuinely useful for decision-making.

3. **Local-first advantage** — Our self-hosted, local-LLM architecture is a genuine competitive advantage for data-sensitive organizations. Protect this by keeping all data processing on-premises.

4. **Automation enables adoption** — Manual trigger tools get used once. Scheduled, incremental tools become embedded in workflow.

5. **Breadth, then depth** — Start with a broad landscape scan (radar), then allow drill-down into specifics. This mirrors how real technology decisions are made.
