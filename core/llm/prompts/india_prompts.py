"""
India-focused prompt set for the India Focus report mode.

Kept FULLY SEPARATE from the general sensing prompts (rather than injecting a
directive into them) for reliability: when India Focus is ON the entire report
is India-scoped, and these prompts drive classification and all four report
phases.

Signatures intentionally mirror the general builders in ``sensing_prompts.py``
so ``classify.py`` / ``report_generator.py`` can swap them in unchanged.

Region/category framing only — never pin to specific vendor or model names.
"""

from core.llm.prompts.sensing_prompts import (
    _custom_requirements_block,
    _recency_block_classify,
    _recency_block_report,
    tense_rules_block,
)

# Shared India scope definition reused across prompts.
_INDIA_SCOPE = (
    "This report is EXCLUSIVELY about INDIA's developments in '{domain}'. "
    "'India' covers Indian companies, AI labs, universities and research "
    "institutes (IITs, IISc, etc.), startups, open-source projects, investors, "
    "and government / policy bodies (e.g. IndiaAI Mission, MeitY). Developments "
    "led by non-Indian organizations are OUT OF SCOPE except where explicitly "
    "used for comparison."
)

# Shared JSON output rules (schema itself is injected by invoke_llm).
_OUTPUT_RULES = (
    "OUTPUT RULES:\n"
    "- Return ONLY valid JSON for the requested schema.\n"
    "- Do NOT include schema definitions, $defs, $ref, properties, or type metadata.\n"
    "- Newlines inside string values MUST be written as \\n (escaped).\n"
    '- Double quotes inside string values MUST be escaped as \\".\n'
)

# The four India streams used to frame topic categorization.
_STREAMS_BLOCK = (
    "FOUR STREAMS (use these to frame topic categories and coverage):\n"
    "- Business: funding, commercialization, partnerships, policy and market moves.\n"
    "- Technology: model/system releases, hardware/chips, infrastructure.\n"
    "- Implementation: agentic AI and other real-world deployments, products, applications.\n"
    "- Research: novel or incremental research papers, open-source/GitHub, benchmarks.\n\n"
)


def india_classify_prompt(
    articles_text: str,
    domain: str = "Technology",
    custom_requirements: str = "",
    key_people: list[str] | None = None,
    topic_categories_text: str = "",
    industry_segments_text: str = "",
    custom_quadrant_names: list[str] | None = None,
    date_range: str = "",
) -> list[dict]:
    """India-focused classification of a batch of articles."""
    people_block = ""
    if key_people:
        names = ", ".join(key_people)
        people_block = (
            f"\nKEY PEOPLE WATCHLIST:\n"
            f"Pay special attention to articles mentioning these leaders: {names}.\n"
            "Boost relevance_score by ~0.1 for articles featuring their actions or statements.\n"
        )

    scope = _INDIA_SCOPE.format(domain=domain)

    contents = [
        {
            "role": "system",
            "parts": (
                f"You are a senior analyst specializing in INDIA's '{domain}' landscape.\n\n"
                "Classify and summarize each article below. For each, determine:\n"
                "1. A concise summary (2-3 sentences)\n"
                "2. Relevance score (0.0-1.0)\n"
                "3. Topic category\n"
                "4. Industry segment\n\n"
                "DOMAIN + REGION FOCUS — CRITICAL:\n"
                f"{scope}\n"
                f"- An article is relevant ONLY if its PRIMARY subject is an INDIAN development "
                f"in '{domain}' (an Indian company, lab, university, startup, project, investor, or policy).\n"
                "- Articles primarily about non-Indian organizations should receive relevance_score < 0.2, "
                "even if they mention India in passing.\n"
                "- Articles about other technology domains should receive relevance_score < 0.2.\n"
                "- When in doubt, prefer EXCLUDING over INCLUDING.\n\n"
                + _STREAMS_BLOCK
                + _custom_requirements_block(custom_requirements)
                + (_recency_block_classify(date_range) if date_range else "")
                + topic_categories_text + "\n"
                + industry_segments_text + "\n"
                + people_block
                + _OUTPUT_RULES
                + "- Each element must have: title, source, url, published_date, summary, "
                "relevance_score, topic_category, industry_segment.\n"
                "- Filter out articles with relevance_score < 0.3.\n"
                "- Omit non-India or off-domain articles entirely.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"ARTICLES TO CLASSIFY:\n\n{articles_text}\n\n"
                f"Classify each article that is DIRECTLY about INDIA's developments in '{domain}'. "
                "Exclude non-Indian or off-domain articles. The articles array MUST contain "
                "classified entries — do NOT return an empty array. Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def india_report_core_prompt(
    classified_articles_json: str,
    domain: str = "Technology",
    date_range: str = "",
    custom_requirements: str = "",
    org_context: str = "",
    key_people: list[str] | None = None,
    industry_segments_text: str = "",
    experience_block: str = "",
    prompt_patch: str = "",
    feedback_block: str = "",
    audience_label: str = "the reader",  # accepted for call-site parity; region framing is fixed
) -> list[dict]:
    """Phase 1 (India): title, bottom line, executive summary, top events, key trends."""
    people_block = ""
    if key_people:
        names = ", ".join(key_people)
        people_block = (
            f"\nKEY PEOPLE WATCHLIST:\nTrack actions/statements by: {names}.\n"
        )

    scope = _INDIA_SCOPE.format(domain=domain)

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist producing a weekly "
                f"INDIA FOCUS report on the '{domain}' domain.\n\n"
                f"{scope}\n\n"
                "Generate the CORE of the report: report_title, bottom_line, executive_summary, "
                "topic_highlights, top_events, and key_trends — ALL about India's activity in "
                f"'{domain}'.\n\n"
                + _STREAMS_BLOCK
                + "SECTION GUIDELINES:\n"
                "- report_title: must make the India focus explicit, e.g. "
                f"\"India Focus: {domain} — {date_range}\".\n"
                "- bottom_line: 2-3 sentences — the single most important takeaway about India this period.\n"
                "- top_events: the TOP ~10 most impactful INDIAN events of the period, each with "
                "headline, actor (Indian org/person), event_type, impact_summary, strategic_intent, "
                "segment, related_technologies, source_urls, and a recommendation.\n"
                "- executive_summary: 200-350 words, markdown, structured as **What Happened** / "
                "**Why It Matters** / **What To Do**, framed for a reader tracking India's "
                f"'{domain}' ecosystem.\n"
                "- topic_highlights: 4-8 scannable India updates (short label + 1-2 sentences).\n"
                "- key_trends: 5-10 India-specific trends with evidence and why they matter.\n\n"
                "GROUNDING AND CITATION RULES:\n"
                "- Every claim MUST be grounded in the provided articles (all India-scoped).\n"
                "- Populate source_urls (1-5 per entry) from the article URLs.\n"
                "- If an article includes a 'content_excerpt', use it for deeper context.\n"
                "- Do NOT fabricate information not present in the articles.\n\n"
                + _recency_block_report()
                + tense_rules_block()
                + (f"{org_context}\n\n" if org_context else "")
                + people_block
                + _OUTPUT_RULES
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DATE RANGE: {date_range}\n"
                f"DOMAIN: {domain} (INDIA FOCUS)\n\n"
                f"CLASSIFIED INDIA ARTICLES:\n\n{classified_articles_json}\n\n"
                "Generate the India-focused report core: report_title, bottom_line, executive_summary, "
                "topic_highlights, domain, date_range, total_articles_analyzed, top_events, key_trends. "
                "Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def india_report_radar_prompt(
    classified_articles_json: str,
    core_context_json: str,
    domain: str = "Technology",
    date_range: str = "",
    custom_quadrant_names: list[str] | None = None,
    custom_requirements: str = "",
    experience_block: str = "",
    prompt_patch: str = "",
    feedback_block: str = "",
) -> list[dict]:
    """Phase 2 (India): technology radar entries from the Indian ecosystem."""
    scope = _INDIA_SCOPE.format(domain=domain)
    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist building the Technology Radar for a "
                f"weekly INDIA FOCUS report on the '{domain}' domain.\n\n"
                f"{scope}\n\n"
                "Phase 1 (executive summary, events, trends) is done. Generate the radar entries, "
                "aligned with the Phase 1 context.\n\n"
                "RADAR RULES:\n"
                f"- Every radar item must be a SPECIFIC technology, model, technique, tool, or "
                f"framework from INDIA's '{domain}' ecosystem.\n"
                "- NEVER use a company/organization name alone as a radar item — name the specific technology.\n"
                "- NEVER use overly broad/generic terms or the domain name itself.\n"
                "- Only include technologies that are recent and currently relevant; if a newer version "
                "exists, include only the newest.\n"
                "- Assign quadrant and ring (Adopt/Trial/Assess/Hold) and set is_new appropriately.\n\n"
                "GROUNDING:\n"
                "- Ground every radar item in the provided India articles; do not fabricate.\n\n"
                + _custom_requirements_block(custom_requirements)
                + _OUTPUT_RULES
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DATE RANGE: {date_range}\n"
                f"DOMAIN: {domain} (INDIA FOCUS)\n\n"
                f"PHASE 1 CONTEXT:\n{core_context_json}\n\n"
                f"CLASSIFIED INDIA ARTICLES:\n\n{classified_articles_json}\n\n"
                "Generate radar_items for India's technologies in this domain. Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def india_report_insights_prompt(
    classified_articles_json: str,
    core_context_json: str,
    radar_context_json: str,
    domain: str = "Technology",
    date_range: str = "",
    custom_requirements: str = "",
    key_people: list[str] | None = None,
    industry_segments_text: str = "",
) -> list[dict]:
    """Phase 3 (India): market signals, report sections, recommendations, notable articles."""
    people_block = ""
    if key_people:
        names = ", ".join(key_people)
        people_block = f"\nKEY PEOPLE WATCHLIST:\nTrack moves by: {names}.\n"

    scope = _INDIA_SCOPE.format(domain=domain)
    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist continuing a weekly INDIA FOCUS report on "
                f"the '{domain}' domain.\n\n"
                f"{scope}\n\n"
                "Phase 1 (core) and Phase 2 (radar) are done. Now generate: market_signals, "
                "report_sections (3-6 detailed markdown sections), recommendations (3-7 actionable, "
                "with rationale/effort/urgency), and notable_articles.\n\n"
                "FRAMING:\n"
                "- All content is about India's activity in this domain.\n"
                "- recommendations are for a reader/organization TRACKING India — e.g. what to watch, "
                "evaluate, or respond to given these Indian developments.\n\n"
                + _STREAMS_BLOCK
                + "GROUNDING:\n- Ground everything in the provided India articles; cite source_urls; do not fabricate.\n\n"
                + _custom_requirements_block(custom_requirements)
                + (industry_segments_text + "\n" if industry_segments_text else "")
                + people_block
                + _OUTPUT_RULES
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DATE RANGE: {date_range}\n"
                f"DOMAIN: {domain} (INDIA FOCUS)\n\n"
                f"PHASE 1 CONTEXT:\n{core_context_json}\n\n"
                f"RADAR CONTEXT:\n{radar_context_json}\n\n"
                f"CLASSIFIED INDIA ARTICLES:\n\n{classified_articles_json}\n\n"
                "Generate market_signals, report_sections, recommendations, notable_articles. "
                "Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def india_details_prompt(
    selected_technologies_json: str,
    classified_articles_json: str,
    domain: str = "Technology",
    custom_requirements: str = "",
    org_context: str = "",
) -> list[dict]:
    """Phase 4 (India): detailed deep-dive write-ups for selected Indian technologies."""
    scope = _INDIA_SCOPE.format(domain=domain)
    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist writing detailed technology radar entries "
                f"for an INDIA FOCUS report on the '{domain}' domain.\n\n"
                f"{scope}\n\n"
                + _custom_requirements_block(custom_requirements)
                + (
                    f"ORGANIZATION CONTEXT:\n{org_context}\n\n"
                    "- In 'why_it_matters', note relevance to the org's priorities where supported.\n"
                    "- Do NOT fabricate org-specific connections unsupported by articles.\n\n"
                    if org_context else ""
                )
                + "For each selected technology, write a grounded deep dive (what it is, why it "
                "matters, maturity, practical applications) based on the India articles provided. "
                "Do not fabricate details not present in the articles.\n\n"
                + _OUTPUT_RULES
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain} (INDIA FOCUS)\n\n"
                f"SELECTED TECHNOLOGIES:\n{selected_technologies_json}\n\n"
                f"CLASSIFIED INDIA ARTICLES:\n\n{classified_articles_json}\n\n"
                "Generate radar_item_details for each selected technology. Return ONLY valid JSON."
            ),
        },
    ]
    return contents
