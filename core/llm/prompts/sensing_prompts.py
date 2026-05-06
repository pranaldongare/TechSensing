import json
from datetime import datetime, timezone
from typing import Optional

from core.llm.prompts.shared import tense_rules_block


def _experience_memory_block(
    experience_block: str = "",
    prompt_patch: str = "",
    feedback_block: str = "",
) -> str:
    """Combine experience memory, prompt patches, and feedback into a prompt block.

    Returns empty string if no learning data is available.
    """
    parts = []
    if experience_block:
        parts.append(experience_block)
    if prompt_patch:
        parts.append(f"LEARNED GUIDANCE (from past runs):\n{prompt_patch}")
    if feedback_block:
        parts.append(feedback_block)
    return "\n\n".join(parts) + "\n\n" if parts else ""


def _custom_requirements_block(custom_requirements: str) -> str:
    """Build a high-priority custom requirements block for LLM prompts.

    Positioned near the TOP of system prompts with authoritative language
    so the LLM treats it as a hard constraint, not a suggestion.
    """
    if not custom_requirements:
        return ""
    return (
        "USER FOCUS REQUIREMENTS (MANDATORY — READ FIRST):\n"
        "The user has specified constraints that MUST guide your entire analysis:\n"
        f"---\n{custom_requirements}\n---\n"
        "Apply these requirements as a PRIMARY filter. Content matching these "
        "requirements should receive SIGNIFICANTLY higher relevance. Content "
        "that does NOT match these requirements should be EXCLUDED or receive "
        "very low relevance scores (< 0.3).\n"
        "CRITICAL: Do NOT fabricate or invent connections between content and "
        "the user's focus requirements. If a technology, model, or development "
        "has NO genuine connection to the focus area, either EXCLUDE it or "
        "present it accurately WITHOUT attributing it to the focus area. "
        "NEVER claim a technology is related to the focus area unless the "
        "source articles explicitly support that connection.\n\n"
    )


def _stale_years_str() -> str:
    """Return comma-separated list of years that are considered stale.

    Everything from 2020 through the previous calendar year is stale for
    a weekly tech sensing report.  This keeps the prompt evergreen
    instead of relying on hardcoded year lists.
    """
    current_year = datetime.now(timezone.utc).year
    return ", ".join(str(y) for y in range(2020, current_year))


def _recency_block_classify(date_range: str) -> str:
    """Build the RECENCY RULES block for the classifier prompt."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%B %d, %Y")
    stale = _stale_years_str()
    return (
        f"RECENCY RULES (CRITICAL — READ CAREFULLY):\n"
        f"- The target date range is: {date_range}.\n"
        f"- Today's date is: {today_str}.\n"
        "- Articles published MORE THAN 6 months before today should "
        "receive relevance_score < 0.2.\n"
        "- STALE RE-SYNDICATION DETECTION: News aggregators (Google News, "
        "DuckDuckGo) frequently re-surface old articles with new dates. "
        "You MUST detect this.  If an article describes a product launch, "
        "announcement, model release, or event from a PREVIOUS YEAR "
        f"({stale}), it is OLD NEWS regardless of the 'Date' field "
        "shown above — score it 0.0.\n"
        "- EXAMPLES of stale content to reject (score 0.0):\n"
        "  * Product launches from any year before the current year\n"
        "  * 'Sora is here' (OpenAI Sora launched Dec 2024 — old)\n"
        "  * 'Gemma 3 release' (Google Gemma 3 launched Mar 2025 — old)\n"
        "  * 'Wan 2.1' (Alibaba Wan 2.1 released Feb 2025 — old)\n"
        "  * Any article whose core subject is a product/event from >6 months ago\n"
        "  * Comparison articles about older models (e.g. 'Llama 3 vs GPT-4')\n"
        "- If the article's Date field says 'Unknown' or looks recent but the "
        "CONTENT clearly describes an old event, trust the CONTENT over the "
        "date field.\n"
        "- Prioritize articles about developments from the last 1-3 months.\n"
        "- For published_date: output the ACTUAL publication date from the "
        "content, NOT the aggregator date. If the article is about a 2024 "
        "event, output '2024-...' even if the source says 2026.\n\n"
    )


def _recency_block_report() -> str:
    """Build the RECENCY ENFORCEMENT block for report-phase prompts."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%B %d, %Y")
    stale = _stale_years_str()
    return (
        "RECENCY ENFORCEMENT (CRITICAL):\n"
        f"- Today is {today_str}.\n"
        "- Focus ONLY on developments from the DATE RANGE specified below.\n"
        "- Do NOT feature technologies or events that occurred BEFORE the "
        "date range as if they are current news. This is the #1 quality "
        "issue to avoid.\n"
        "- STALE CONTENT CHECK: If an article describes a product launch, "
        "model release, processor unveiling, partnership announcement, or "
        "research paper from a PREVIOUS YEAR "
        f"({stale}), it is OLD regardless of its 'published_date'. "
        "Do NOT create headline_moves or key_trends for old events.\n"
        "- If an article mentions an older product/technology as context "
        "or comparison, do NOT create a headline_move or key_trend for "
        "it — only for NEW developments.\n"
        "- Old product launches, discontinued products, legacy models, "
        "and legacy technologies should not appear as headline moves, "
        "trends, or radar items.\n\n"
    )

_DEFAULT_QUADRANT_DEFS = (
    "QUADRANT DEFINITIONS:\n"
    "- Techniques: Processes, methodologies, architectural patterns\n"
    "- Platforms: Infrastructure, cloud services, compute platforms\n"
    "- Tools: Software tools, libraries, frameworks for development\n"
    "- Languages & Frameworks: Programming languages, major frameworks\n\n"
)


_DEFAULT_QUADRANT_NAMES = ["Techniques", "Platforms", "Tools", "Languages & Frameworks"]


def _quadrant_names_inline(custom_quadrant_names: list[str] | None = None) -> str:
    """Return quadrant names as a slash-separated inline string."""
    names = custom_quadrant_names if custom_quadrant_names and len(custom_quadrant_names) == 4 else _DEFAULT_QUADRANT_NAMES
    return "/".join(names)


def _quadrant_definitions_block(custom_quadrant_names: list[str] | None = None) -> str:
    """Return the QUADRANT DEFINITIONS block, using custom names if provided."""
    if not custom_quadrant_names or len(custom_quadrant_names) != 4:
        return _DEFAULT_QUADRANT_DEFS
    return (
        "QUADRANT DEFINITIONS (CUSTOM):\n"
        f"- {custom_quadrant_names[0]}: First quadrant category\n"
        f"- {custom_quadrant_names[1]}: Second quadrant category\n"
        f"- {custom_quadrant_names[2]}: Third quadrant category\n"
        f"- {custom_quadrant_names[3]}: Fourth quadrant category\n\n"
    )


def sensing_classify_prompt(
    articles_text: str,
    domain: str = "Technology",
    custom_requirements: str = "",
    key_people: list[str] | None = None,
    topic_categories_text: str = "",
    industry_segments_text: str = "",
    custom_quadrant_names: list[str] | None = None,
    date_range: str = "",
) -> list[dict]:
    """
    Build a chat prompt to classify and summarize a batch of articles.

    NOTE: Do NOT embed the JSON schema here — invoke_llm() already injects
    the schema via PydanticOutputParser.get_format_instructions().  Embedding
    it twice causes the LLM to echo the schema definition back instead of
    producing actual classified article data.

    topic_categories_text and industry_segments_text are pre-rendered text
    blocks from the domain preset (see core/sensing/config.py).
    """
    # Build optional key-people watchlist block
    people_block = ""
    if key_people:
        names = ", ".join(key_people)
        people_block = (
            f"\nKEY PEOPLE WATCHLIST:\n"
            f"Pay special attention to articles mentioning these leaders: {names}.\n"
            "Boost relevance_score by ~0.1 for articles featuring their actions or statements.\n"
        )

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology analyst specializing in "
                f"{domain}.\n\n"
                "Your task is to classify and summarize each article below.\n"
                "For each article, determine:\n"
                "1. A concise summary (2-3 sentences)\n"
                "2. Relevance score (0.0-1.0) to the domain\n"
                "3. Technology Radar quadrant placement\n"
                "4. Technology Radar ring placement\n"
                "5. A short technology name for the radar blip\n"
                "6. Topic category\n"
                "7. Industry segment\n\n"
                f"DOMAIN FOCUS — CRITICAL:\n"
                f"This report is EXCLUSIVELY about '{domain}'. Apply these rules strictly:\n"
                f"- An article is relevant ONLY if its PRIMARY subject is '{domain}' "
                "or a specific sub-topic/technology within that domain.\n"
                "- Articles about OTHER technology domains (e.g., general AI/LLM news, "
                "cryptocurrency, cloud infrastructure, cybersecurity) that merely MENTION "
                f"'{domain}' in passing should receive relevance_score < 0.2.\n"
                "- An article about a big-tech company's strategy is NOT relevant unless "
                f"it specifically discusses their work on '{domain}' technologies.\n"
                "- When in doubt, prefer EXCLUDING over INCLUDING. It is better to have "
                "a focused report with fewer items than a diluted report with off-topic noise.\n\n"
                + _custom_requirements_block(custom_requirements)
                + (_recency_block_classify(date_range) if date_range else "")
                + _quadrant_definitions_block(custom_quadrant_names)
                + "RING DEFINITIONS:\n"
                "- Adopt: Proven technology, recommend for wide use\n"
                "- Trial: Worth pursuing in projects that can handle some risk\n"
                "- Assess: Worth exploring to understand its impact\n"
                "- Hold: Proceed with caution, not recommended for new work\n\n"
                + topic_categories_text + "\n"
                + industry_segments_text + "\n"
                + people_block
                + "OUTPUT RULES:\n"
                "- Return ONLY a valid JSON object with an \"articles\" array.\n"
                "- Each element must have: title, source, url, published_date, summary, "
                "relevance_score, quadrant, ring, technology_name, reasoning, "
                "topic_category, industry_segment.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, or type metadata.\n"
                "- Newlines inside string values MUST be written as \\n (escaped), NOT as actual line breaks.\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
                "- Filter out articles with relevance_score < 0.3.\n"
                "- If an article is not relevant to the domain, omit it from the output.\n"
                "- The articles array MUST contain actual classified data, not be empty.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"ARTICLES TO CLASSIFY:\n\n{articles_text}\n\n"
                f"Classify each article that is DIRECTLY relevant to '{domain}'. "
                "Exclude articles about other technology domains even if they are interesting. "
                "The articles array in your response MUST contain classified entries — "
                "do NOT return an empty array. Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def sensing_report_core_prompt(
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
) -> list[dict]:
    """
    Phase 1 prompt: executive summary, headline moves, and key trends.

    NOTE: Do NOT embed the JSON schema here — invoke_llm() already injects
    the schema via PydanticOutputParser.get_format_instructions().
    """
    people_block = ""
    if key_people:
        names = ", ".join(key_people)
        people_block = (
            f"\nKEY PEOPLE WATCHLIST:\n"
            f"Track actions and statements by these leaders: {names}.\n"
            "Include their moves in headline_moves where relevant.\n"
        )

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist creating a weekly "
                f"Tech Sensing Report EXCLUSIVELY for the '{domain}' domain.\n\n"
                "Based on the classified articles provided, generate the CORE "
                "of the report: the executive summary, headline moves, and key trends.\n\n"
                f"DOMAIN FOCUS: Every item in this report must be directly about '{domain}'. "
                "Do NOT include developments from other technology domains (e.g., general AI/LLM "
                "news, cryptocurrency, cloud platforms) unless they specifically involve "
                f"'{domain}' technologies. When an article covers multiple domains, only "
                f"discuss the aspects relevant to '{domain}'.\n\n"
                + _custom_requirements_block(custom_requirements)
                + _experience_memory_block(experience_block, prompt_patch, feedback_block)
                + industry_segments_text + "\n"
                + people_block
                + "SECTION GUIDELINES:\n"
                "- Bottom line: Write a 2-3 sentence 'bottom line' — the single most important "
                "takeaway a CTO should know this week. Be direct and actionable.\n\n"
                "- Top events: Identify the TOP 10 most impactful events of the week, "
                "ranked by significance across ALL segments. For each event provide:\n"
                "  * headline: 1-2 sentence description of what happened\n"
                "  * actor: person or organization behind this event\n"
                "  * event_type: one of 'product_launch', 'partnership', 'funding', "
                "'regulation', 'research', or 'strategic_move'\n"
                "  * impact_summary: why it matters (1-2 sentences)\n"
                "  * strategic_intent: why the actor is doing this (1-2 sentences, if discernible)\n"
                "  * segment: industry segment\n"
                "  * related_technologies: radar-level technology names related to this event\n"
                "  * source_urls: article URLs reporting this event\n"
                "  * recommendation: 1-2 sentence actionable takeaway for technology leaders — "
                "what should they do, evaluate, or watch based on this event? Be specific "
                "(e.g., 'Evaluate [X] for [use case]' or 'Monitor [Y] for competitive impact'). "
                "Leave empty only if no actionable takeaway is possible.\n\n"
                "- Executive summary: decisive, forward-looking, 200-350 words. "
                "Structure in three parts:\n"
                "  * **What Happened** — key facts and developments this week\n"
                "  * **Why It Matters** — strategic implications for technology leaders\n"
                "  * **What To Do** — recommended immediate actions or areas to watch\n"
                "Use markdown formatting: bold (**term**) for key technologies, "
                "bullet points for highlights, and separate paragraphs. "
                "Do NOT write it as a single wall of text.\n\n"
                "- Topic highlights: 4-8 quick at-a-glance updates, one per major topic area covered. "
                "Each has a short topic label (2-4 words like 'Video Generation', 'Agentic AI', "
                "'LLM Efficiency', 'AI Safety') and a 1-2 sentence summary of the key development. "
                "These should be scannable — a reader should understand what moved this week "
                "just from the topic highlights alone.\n\n"
                "- Key trends: identify 5-10 major trends with supporting evidence from the articles. "
                "Each trend should have a clear description of WHY it matters.\n\n"
                "GROUNDING AND CITATION RULES:\n"
                "- Every claim MUST be grounded in the provided articles.\n"
                "- Use article URLs to populate source_urls arrays (1-5 per entry).\n"
                "- If an article includes a 'content_excerpt' field, use it for deeper context.\n"
                "- Do NOT fabricate information not present in the articles.\n\n"
                + _recency_block_report()
                + tense_rules_block()
                + (
                    f"{org_context}\n\n"
                    if org_context
                    else ""
                )
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DATE RANGE: {date_range}\n"
                f"DOMAIN: {domain}\n\n"
                f"CLASSIFIED ARTICLES:\n\n{classified_articles_json}\n\n"
                "Generate the report core: report_title, bottom_line, executive_summary, "
                "topic_highlights, domain, date_range, total_articles_analyzed, top_events, "
                "key_trends. Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def sensing_report_radar_prompt(
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
    """
    Phase 2 prompt: technology radar items only.

    Receives Phase 1 core context for alignment with identified trends.
    """
    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist building the Technology Radar "
                f"for a weekly Tech Sensing Report EXCLUSIVELY on the '{domain}' domain.\n\n"
                "Phase 1 (executive summary, headline moves, key trends) has already "
                "been generated. You will now generate the technology radar entries.\n\n"
                "Use the Phase 1 context to ensure your radar items align with the "
                "identified trends and headline moves.\n\n"
                f"DOMAIN FOCUS: Every radar item must be a technology SPECIFIC to '{domain}'. "
                "Do NOT include technologies from other domains (e.g., general-purpose LLMs, "
                "cloud platforms, cryptocurrency tools) unless they are specifically designed "
                f"for or significantly adapted to '{domain}' use cases.\n\n"
                + _custom_requirements_block(custom_requirements)
                + _experience_memory_block(experience_block, prompt_patch, feedback_block)
                + "RADAR GUIDELINES:\n"
                "- 10-20 distinct technologies/techniques — STRICTLY consolidate duplicates.\n"
                "- Each entry: name, quadrant ("
                + _quadrant_names_inline(custom_quadrant_names)
                + "), "
                "ring (Adopt/Trial/Assess/Hold), brief description (1-2 sentences), "
                "is_new flag, signal_strength (0.0-1.0), source_count, trl (1-9).\n"
                "- Keep descriptions concise to stay within output limits.\n\n"
                "DEDUPLICATION RULES (CRITICAL):\n"
                "- NEVER include two radar items that refer to the same technology or "
                "closely related versions of the same technology.\n"
                "- Merge variations into one entry: e.g., 'TechX v2' and 'TechX v3' → single "
                "entry for the most current version.\n"
                "- If the same technology appears in multiple articles with different names, "
                "pick the most specific, current name.\n\n"
                "RECENCY RULES (CRITICAL):\n"
                f"- Today is {datetime.now(timezone.utc).strftime('%B %d, %Y')}.\n"
                "- ONLY include technologies that are NEW or have been SIGNIFICANTLY UPDATED "
                "within the last 6 months.\n"
                f"- STALE CONTENT: If an article describes a product launch, model release, "
                f"or announcement from a previous year ({_stale_years_str()}), that is OLD "
                "NEWS — do NOT create a radar item for it. The article's date field may be "
                "misleading (aggregators re-syndicate old content with new dates). Trust "
                "the CONTENT over the date.\n"
                "- EXAMPLES of stale content that must NOT become radar items:\n"
                "  * OpenAI Sora (launched Dec 2024), Gemma 3 (Mar 2025), Wan 2.1 (Feb 2025)\n"
                "  * Any model or product whose initial release was >6 months ago\n"
                "  * Comparison articles about older models (e.g. 'Llama 3 vs GPT-4')\n"
                "- Do NOT create radar items for legacy or well-established technologies "
                "that are merely MENTIONED in articles as historical context, comparison, "
                "or background.\n"
                "- If an article compares a new technology with an older one, only the NEW one "
                "should be a radar item — the older one is just context.\n"
                "- Technologies in the 'Hold' ring must still be recent enough to warrant tracking.\n\n"
                "NOVELTY vs BUZZ (CRITICAL):\n"
                "- is_new=true ONLY for technologies that FIRST APPEARED or were FIRST RELEASED within "
                "the lookback window. If a technology existed before the lookback period but is currently "
                "buzzing or trending, set is_new=false.\n"
                "- ESTABLISHED TECHNOLOGIES that are merely receiving continued attention, discussion, "
                "or incremental updates are NOT new. Examples of things that must NOT be radar items:\n"
                "  * Established patterns: 'Agentic RAG', 'Self-RAG', 'Graph RAG', 'AI Agents', "
                "'LLM Agents', 'AI Agent Frameworks', 'Prompt Engineering', 'Vibe Coding', "
                "'Chain of Thought', 'Fine-tuning', 'RLHF'\n"
                "  * Generic categories: 'AI Agent Interaction Infrastructure', 'LLM Confidence "
                "Calibration', 'Agentic World Modeling' — these describe broad research AREAS, "
                "not specific new technologies\n"
                "  * Hardware platforms: 'Mac Mini', 'Mac Studio', 'NVIDIA H100' — these are "
                "compute infrastructure, not domain-specific technologies\n"
                "- SUPERSEDED MODELS: If an article mentions a model AND a newer version exists, "
                "only include the NEWEST version. Example: if Qwen3.6 exists, do NOT create a "
                "radar item for Qwen3.5. If the article itself discusses the older version as "
                "background, skip it entirely.\n"
                "- A new VERSION or SIGNIFICANT UPDATE of an existing technology IS new (e.g., "
                "'GPT-5' would be new even though GPT existed before).\n"
                "- CROSS-TECHNOLOGY developments (e.g., 'Company A partners with Company B for X') "
                "should be captured as a SINGLE radar item named after the novel outcome or "
                "collaboration — NOT as separate items for each established entity.\n"
                "- APIs that were released MORE THAN 6 months ago are NOT new even if new "
                "tutorials or guides appear. Example: 'GPT-4o Realtime Audio API' was released "
                "in 2024 — a 2026 tutorial about it does NOT make it a new radar item.\n\n"
                "SPECIFICITY RULES (CRITICAL):\n"
                "- Radar items MUST be specific technologies, models, techniques, tools, or frameworks "
                f"within the {domain} domain.\n"
                "- NEVER use company/organization names as radar items (e.g., NOT 'Google', "
                "'Microsoft', 'Meta', or any other company name).\n"
                "- NEVER use overly broad or generic terms as radar items (e.g., NOT the domain "
                "name itself, not broad category labels).\n"
                "- Instead, use the SPECIFIC technology, version, technique, or framework name.\n"
                "- If an article discusses a company's strategy without a specific technology, "
                "it belongs in market_signals, NOT in the radar.\n\n"
                "TECHNOLOGY READINESS LEVEL (TRL):\n"
                "For each radar item, assign a TRL score (1-9) based on the article evidence:\n"
                "  TRL 1-2: Basic research, concept formulation — early academic papers only\n"
                "  TRL 3-4: Proof of concept, lab validation — benchmarks and experimental demos\n"
                "  TRL 5-6: Validated/demonstrated in relevant environment — pilot deployments, limited real use\n"
                "  TRL 7: Prototype in operational environment — beta/preview products\n"
                "  TRL 8-9: Production-ready, proven at scale — GA products, wide enterprise adoption\n"
                "Use the ring as a baseline (Adopt=8-9, Trial=6-7, Assess=3-5, Hold=1-4), "
                "then adjust based on specific article evidence about maturity and adoption.\n\n"
                "GROUNDING AND CITATION RULES:\n"
                "- Every radar item MUST be grounded in the provided articles.\n"
                "- Do NOT fabricate technologies not mentioned in the articles.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DATE RANGE: {date_range}\n"
                f"DOMAIN: {domain}\n\n"
                f"PHASE 1 CONTEXT (headline moves and key trends):\n{core_context_json}\n\n"
                f"CLASSIFIED ARTICLES:\n\n{classified_articles_json}\n\n"
                "Return a JSON object with a single key `radar_items` containing the array of radar entries.\n"
                "Example structure: {\"radar_items\": [{...}, ...]}\n"
                "Return ONLY valid JSON — no commentary or markdown fencing."
            ),
        },
    ]
    return contents


def sensing_report_insights_prompt(
    classified_articles_json: str,
    core_context_json: str,
    radar_context_json: str,
    domain: str = "Technology",
    date_range: str = "",
    custom_requirements: str = "",
    key_people: list[str] | None = None,
    industry_segments_text: str = "",
) -> list[dict]:
    """
    Phase 3 prompt: market signals, report sections, recommendations,
    and notable articles.

    Receives Phase 1 core + Phase 2 radar items as grounding context.
    """
    people_block = ""
    if key_people:
        names = ", ".join(key_people)
        people_block = (
            f"\nKEY PEOPLE WATCHLIST:\n"
            f"Track actions and statements by these leaders: {names}.\n"
            "Include their moves in market_signals where relevant.\n"
        )

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist continuing a weekly "
                f"Tech Sensing Report EXCLUSIVELY for the '{domain}' domain.\n\n"
                "Phase 1 (executive summary, top events, key trends) and "
                "Phase 2 (technology radar items) have already been generated. "
                "You will now generate: deep-dive report sections, "
                "recommendations, notable articles, and blind spots.\n\n"
                "Use the Phase 1 and Phase 2 context to ensure consistency.\n\n"
                f"DOMAIN FOCUS: All content must be directly relevant to '{domain}'. "
                "Exclude recommendations about other technology domains.\n\n"
                + _custom_requirements_block(custom_requirements)
                + industry_segments_text + "\n"
                + people_block
                + "SECTION GUIDELINES:\n"
                "- Report sections: 3-6 deep-dive sections with markdown formatting. "
                "Each section should elaborate on one of the key trends identified in Phase 1. "
                "Use the trend name as the section title where possible so sections can be "
                "linked as deep-dives for their corresponding trends.\n\n"
                "- Recommendations: 3-7 actionable recommendations. For each include:\n"
                "  * title: clear, concise recommendation name\n"
                "  * description: actionable description (2-4 sentences)\n"
                "  * priority: 'Critical', 'High', 'Medium', or 'Low'\n"
                "  * rationale: why this matters NOW — the driving context (1-2 sentences)\n"
                "  * effort: implementation effort — 'Low', 'Medium', or 'High'\n"
                "  * urgency: time urgency — 'Immediate', 'Short-term', 'Medium-term', or 'Long-term'\n"
                "  * related_trends: names of trends this recommendation relates to\n"
                "Frame for an enterprise technology and strategy leader.\n\n"
                "- Notable articles: select the 5-10 most impactful articles.\n\n"
                "- Blind spots: Identify 2-4 coverage blind spots — topics, geographic regions, "
                "industry segments, or perspectives that SHOULD be covered for the '{domain}' "
                "domain but are missing or underrepresented in the provided articles. For each:\n"
                "  * area: what is missing\n"
                "  * why_it_matters: why this gap matters for decision-making\n"
                "  * suggested_sources: 1-3 sources or search terms to fill this gap\n\n"
                "GROUNDING AND CITATION RULES:\n"
                "- Every claim MUST be grounded in the provided articles.\n"
                "- Use article URLs to populate source_urls arrays (1-5 per entry).\n"
                "- If an article includes a 'content_excerpt' field, use it for deeper context.\n"
                "- Do NOT fabricate information not present in the articles.\n\n"
                "RECENCY ENFORCEMENT (CRITICAL):\n"
                f"- Today is {datetime.now(timezone.utc).strftime('%B %d, %Y')}.\n"
                "- Focus ONLY on developments from the DATE RANGE. Do not feature old events as current.\n"
                f"- STALE CONTENT: Articles from news aggregators sometimes describe events from "
                f"{_stale_years_str()} with misleading recent dates. If the content describes "
                "an old product launch, model release, announcement, or event, do NOT include "
                "it in sections or recommendations.\n"
                "- Old product launches, discontinued products, legacy models, and legacy "
                "technologies should not appear in sections or recommendations.\n\n"
                + tense_rules_block()
                + "ATTRIBUTION ACCURACY RULES:\n"
                "- Distinguish between research authors and implementation authors.\n"
                "- If a company's blog post MENTIONS or REFERENCES an external open-source project "
                "or third-party technology, do NOT attribute that technology to the company. "
                "The company is referencing it, not announcing it. Only attribute a technology "
                "to a company if the article clearly states the company CREATED, DEVELOPED, "
                "or RELEASED it.\n"
                "- If the articles don't clearly state who built something, say so.\n\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DATE RANGE: {date_range}\n"
                f"DOMAIN: {domain}\n\n"
                f"PHASE 1 CONTEXT (top events and key trends):\n{core_context_json}\n\n"
                f"PHASE 2 CONTEXT (radar items):\n{radar_context_json}\n\n"
                f"CLASSIFIED ARTICLES:\n\n{classified_articles_json}\n\n"
                "Generate: report_sections, recommendations, "
                "notable_articles, blind_spots. Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def sensing_details_prompt(
    radar_items_json: str,
    classified_articles_json: str,
    domain: str = "Technology",
    custom_requirements: str = "",
    org_context: str = "",
) -> list[dict]:
    """
    Build a chat prompt to generate detailed write-ups for each radar item.

    This is Phase 2 of report generation — called after the skeleton (Phase 1)
    has produced the radar_items list.  Keeping this separate avoids exceeding
    output token limits by splitting the heaviest section into its own call.
    """
    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist writing detailed technology "
                f"radar entries for the {domain} domain.\n\n"
                + _custom_requirements_block(custom_requirements)
                + (
                    f"ORGANIZATION CONTEXT:\n{org_context}\n\n"
                    "When writing technology details:\n"
                    "- In 'why_it_matters', note relevance to the org's priorities where supported by evidence.\n"
                    "- In 'practical_applications', include applications relevant to the org's tech stack.\n"
                    "- Do NOT fabricate org-specific connections unsupported by articles.\n\n"
                    if org_context else ""
                )
                + "You are given a list of RADAR ITEMS (name, quadrant, ring) and the "
                "CLASSIFIED ARTICLES that were used to create them.\n\n"
                "For EVERY radar item, generate a detailed write-up covering:\n"
                "  * what_it_is: Clear explanation of what this technology is and how it works (2-4 sentences).\n"
                "  * why_it_matters: Why this technology is significant and what problems it solves (2-3 sentences).\n"
                "  * current_state: Current maturity, adoption level, and RECENT key developments (2-3 sentences). "
                "Focus on what has happened in the last 6 months — not historical background.\n"
                "  * key_players: Companies/organizations that actively develop, maintain, or officially "
                "release this technology. Do NOT include entities that only published the underlying "
                "research paper unless they also released the implementation.\n"
                "  * practical_applications: Real-world use cases and applications (2-4 items).\n"
                "  * source_urls: URLs of articles informing this write-up.\n"
                "  * quantitative_highlights: 2-5 specific numbers, metrics, or benchmarks "
                "extracted from the articles. Examples: benchmark scores, performance comparisons, "
                "adoption figures, speed/cost improvements, accuracy percentages, parameter counts. "
                "Each item must cite the concrete number and its context, e.g. "
                "'Achieves 92.3% on MMLU, up from 86.4% in v1' or "
                "'Reduces inference cost by 40% vs GPT-4 Turbo'. "
                "Only include numbers explicitly stated in the articles — do NOT fabricate. "
                "If no quantitative data is found for a technology, return an empty list.\n"
                "  * hiring_indicators: Brief summary of hiring trends for this technology "
                "(growing demand, notable job postings, skill requirements). "
                "Leave empty string if no hiring signals found in articles.\n"
                "  * recommendation: 1-2 sentence actionable recommendation for technology leaders "
                "regarding this technology. Be specific about what to do: 'Pilot [X] for [use case]', "
                "'Add [Y] to your evaluation pipeline', 'Monitor [Z] — it may displace [W] within 12 months'. "
                "Ground the recommendation in the evidence from the articles.\n\n"
                "NOVELTY FOCUS (CRITICAL):\n"
                "- These deep dives are for GENUINELY NEW technologies only. The items you "
                "receive have already been filtered to include only novel entries.\n"
                "- Focus on what is NEW and UNPRECEDENTED — do not write explainer-style "
                "deep dives about well-known concepts.\n"
                "- In 'what_it_is', emphasize what makes this different from prior art.\n"
                "- In 'current_state', focus on the specific recent development, not background history.\n"
                "- CROSS-TECHNOLOGY items (collaborations, integrations): Focus the deep dive on "
                "the novel intersection or outcome. Briefly contextualize each participating "
                "technology but keep the narrative centered on the new combined capability, "
                "partnership, or breakthrough — not on explaining each technology separately.\n\n"
                "ATTRIBUTION ACCURACY RULES:\n"
                "- Distinguish between research authors and implementation authors.\n"
                "- For key_players: List ONLY entities that actively develop, maintain, or officially "
                "release the technology.\n"
                "- Clearly state origin: 'Based on [Company] research' vs 'Released by [Company]' "
                "vs 'Community/open-source implementation'.\n"
                "- If the articles don't clearly state who built something, say so.\n\n"
                "GROUNDING RULES:\n"
                "- Every claim MUST be grounded in the provided articles.\n"
                "- Use article URLs to populate source_urls (1-5 per entry).\n"
                "- Do NOT fabricate information not present in the articles.\n\n"
                + tense_rules_block()
                + "OUTPUT RULES:\n"
                "- Return ONLY a valid JSON object with one key: radar_item_details (array).\n"
                "- Each element must have: technology_name, what_it_is, why_it_matters, "
                "current_state, key_players, practical_applications, quantitative_highlights, "
                "source_urls, hiring_indicators, recommendation.\n"
                "- technology_name MUST exactly match the radar item name provided.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, or type metadata.\n"
                "- Newlines inside string values MUST be written as \\n (escaped).\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"RADAR ITEMS:\n{radar_items_json}\n\n"
                f"CLASSIFIED ARTICLES:\n{classified_articles_json}\n\n"
                "Generate detailed write-ups for EVERY radar item listed above. "
                "Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def sensing_relationship_prompt(
    cooccurrence_text: str,
    radar_items_json: str,
    domain: str = "Technology",
) -> list[dict]:
    """
    Build an evidence-based prompt to classify technology relationships.

    Instead of asking the LLM to invent relationships, we provide pre-computed
    co-occurrence pairs (technologies that appear together in the same articles)
    and ask the LLM to classify and interpret each pair.
    """
    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist. You are given EVIDENCE of "
                "technology co-occurrences — pairs of technologies that appear together "
                f"in articles about {domain}.\n\n"
                "Your task:\n\n"
                "1. CLASSIFY each co-occurrence pair into a relationship:\n"
                "   - source_tech / target_tech: MUST exactly match the names given\n"
                "   - relationship_type — one of:\n"
                "     * 'enables' — source powers, underpins, or is a foundation for target\n"
                "     * 'competes_with' — source and target serve a similar purpose or are alternatives\n"
                "     * 'integrates_with' — commonly used together, combined, or complementary\n"
                "     * 'evolves_from' — source is a successor, evolution, or next-generation version of target\n"
                "   - confidence: 'high', 'medium', or 'low'\n"
                "     * 'high' = the articles clearly describe this relationship\n"
                "     * 'medium' = the relationship is implied or likely from context\n"
                "     * 'low' = the co-occurrence seems coincidental or the relationship is weak\n"
                "   - evidence: 1-3 sentences explaining WHY these technologies are related, "
                "citing specific findings from the articles listed\n\n"
                "2. SKIP pairs where the co-occurrence is coincidental — they just happen to be "
                "in the same article but have no real technological relationship. "
                "Quality matters more than quantity. It is better to return 5 strong, well-evidenced "
                "relationships than 20 weak ones.\n\n"
                "3. GROUP technologies into 3-6 CLUSTERS:\n"
                "   - cluster_name: Descriptive name\n"
                "   - technologies: List of technology names in this cluster\n"
                "   - theme: Brief theme description\n"
                "   - rationale: Why these belong together — what connects them\n\n"
                "RULES:\n"
                "- Technology names MUST exactly match the names provided.\n"
                "- Do NOT invent relationships not supported by the co-occurrence evidence.\n"
                "- Do NOT add relationships between technologies that don't appear in the pairs.\n"
                "- Direction matters: choose source and target so the relationship reads naturally "
                "(e.g., 'LangChain integrates_with GPT-4', not the reverse).\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"RADAR ITEMS (for reference):\n{radar_items_json}\n\n"
                f"CO-OCCURRENCE EVIDENCE:\n{cooccurrence_text}\n\n"
                "Classify the relationships and create clusters. "
                "Return ONLY valid JSON with 'relationships' and 'clusters' arrays."
            ),
        },
    ]
    return contents


def sensing_document_topic_extraction_prompt(
    document_text: str,
    domain: str = "Technology",
    custom_requirements: str = "",
) -> list[dict]:
    """
    Build a prompt to extract key topics, technologies, and search queries
    from a parsed document.  Used to orient the web search pipeline so that
    a document upload drives — rather than replaces — web intelligence.

    Takes the first ~8000 characters of the document to stay within
    context limits while capturing the most important content.
    """
    truncated = document_text[:8000]

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology analyst. Given a document excerpt, "
                "extract the key technologies, themes, and entities to drive a "
                "comprehensive web search for related current developments.\n\n"
                f"The user has selected the domain: {domain}\n\n"
                "Your job is to:\n"
                "1. Summarize the document's main subject in 2-3 sentences.\n"
                "2. Refine the domain description if the document is more "
                "specific than the broad domain label.\n"
                "3. Generate 5-10 web search queries that would find CURRENT "
                "news, developments, and research related to the document's "
                "themes. Make queries specific and time-relevant.\n"
                "4. Extract 3-8 specific technology names, frameworks, "
                "techniques, or methodologies mentioned or implied.\n"
                "5. Identify 0-5 companies, organizations, or notable people.\n"
                "6. Generate 3-5 patent-appropriate keyword phrases.\n\n"
                "GUIDELINES:\n"
                "- Search queries should look for CURRENT developments "
                "(news this week/month), not the document's own content.\n"
                "- Technology keywords should be specific enough for "
                "arXiv/GitHub search (use precise names, not broad categories).\n"
                "- Patent keywords should be formal technical phrases "
                f"relevant to the {domain} domain.\n\n"
                + _custom_requirements_block(custom_requirements)
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOCUMENT EXCERPT:\n\n{truncated}\n\n"
                "Extract topics, technologies, search queries, and entities "
                "from this document. Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def sensing_domain_intelligence_prompt(
    domain: str,
    existing_reference: str = "",
    custom_requirements: str = "",
) -> list[dict]:
    """
    Build a prompt to generate comprehensive domain intelligence for the
    sensing pipeline.  When existing_reference is provided (JSON from a
    previous run), the LLM should build upon it — keeping valid items,
    adding new ones, and removing outdated ones.
    """
    existing_block = ""
    if existing_reference:
        existing_block = (
            "\nEXISTING DOMAIN REFERENCE (from previous runs):\n"
            f"{existing_reference}\n\n"
            "INSTRUCTIONS FOR UPDATING:\n"
            "- KEEP items that are still relevant and accurate.\n"
            "- ADD new items that have emerged since the last update.\n"
            "- REMOVE items that are outdated, superseded, or no longer relevant.\n"
            "- UPDATE items where details have changed (e.g., new key people, "
            "new technology versions).\n"
            "- For RSS feeds and search queries, refresh to reflect current "
            "developments and interests.\n"
            "- For blocklists, add newly-generic or newly-legacy terms and remove "
            "any that have regained specificity or relevance.\n\n"
        )

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology intelligence analyst. Your task is to "
                f"generate comprehensive domain intelligence for the '{domain}' domain "
                "to configure a technology sensing pipeline.\n\n"
                + _custom_requirements_block(custom_requirements)
                + "This intelligence will be used to:\n"
                "1. Select RSS feeds and construct search queries for article discovery\n"
                "2. Configure arXiv and patent searches\n"
                "3. Define topic categories and industry segments for article classification\n"
                "4. Identify key people to track\n"
                "5. Build blocklists to filter out generic and legacy radar items\n\n"
                "GUIDELINES:\n"
                "- Be SPECIFIC and CURRENT. Prefer names, versions, and concrete terms "
                "over vague descriptions.\n"
                "- For RSS feeds, only suggest URLs you are confident actually exist "
                "(major tech news sites, arXiv categories as http://arxiv.org/rss/CATEGORY, "
                "popular subreddits as https://www.reddit.com/r/SUBREDDIT/.rss, "
                "official company/project blogs). Prefer well-known, stable feed URLs.\n"
                "- For search queries, write natural DuckDuckGo search queries that "
                "would find recent news articles, blog posts, and announcements.\n"
                "- For patent keywords, use formal technical language that appears in "
                "patent titles and abstracts.\n"
                "- For blocklists, think about what terms are too broad to be "
                "useful radar items (generic terms) and what technologies have "
                "been superseded (legacy terms).\n"
                "- Topic categories should cover the major sub-areas of this domain "
                "and be suitable for classifying news articles.\n"
                "- Industry segments should identify the types of actors/organizations "
                "active in this domain, with example companies or groups.\n\n"
                + existing_block
            ),
        },
        {
            "role": "user",
            "parts": (
                f"Generate comprehensive domain intelligence for: {domain}\n\n"
                "Provide all requested fields with the specified counts. "
                "Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def onepager_bullets_prompt(
    events: list[dict],
    domain: str,
) -> list[dict]:
    """Build a prompt to distill selected top events into one-pager card data.

    Each event dict should have: headline, actor, event_type, impact_summary,
    strategic_intent, recommendation, segment, related_technologies.
    """
    from core.llm.output_schemas.sensing_outputs import OnepagerOutput

    schema_json = json.dumps(OnepagerOutput.model_json_schema(), indent=2)

    events_block = ""
    for i, ev in enumerate(events):
        events_block += (
            f"EVENT {i + 1}:\n"
            f"  Headline: {ev.get('headline', '')}\n"
            f"  Actor: {ev.get('actor', '')}\n"
            f"  Event Type: {ev.get('event_type', '')}\n"
            f"  Impact Summary: {ev.get('impact_summary', '')}\n"
            f"  Strategic Intent: {ev.get('strategic_intent', '')}\n"
            f"  Recommendation: {ev.get('recommendation', '')}\n"
            f"  Segment: {ev.get('segment', '')}\n"
            f"  Related Technologies: {', '.join(ev.get('related_technologies', []))}\n\n"
        )

    return [
        {
            "role": "system",
            "parts": (
                "You are a senior technology analyst producing a single-page "
                "infographic summary of the week's top technology events.\n\n"
                f"DOMAIN: {domain}\n\n"
                "You will receive up to 8 top events. For each event, produce "
                "a card with:\n\n"
                "1. card_title: A punchy headline (<=80 chars). Include the "
                "actor name (company/org). Example: 'OpenAI Releases GPT-5.5' "
                "or 'Google Introduces ReasoningBank Memory Fwk'.\n\n"
                "2. category_tag: A short UPPERCASE tag (2-8 chars) grouping "
                "the event by technology domain. Examples: 'GENAI', 'AUDIO', "
                "'AGENTS', 'CHIPS', 'CLOUD', 'SECURITY', 'ROBOTICS', "
                "'BIOTECH', 'QUANTUM', 'DATA', 'INFRA', 'ENTERPRISE'. "
                "Use the SAME tag for events in the same domain so they "
                "group together on the infographic.\n\n"
                "3. bullets: 3-5 one-line key facts (each <=150 chars). "
                "These must be CONCISE, FACTUAL, and INFORMATION-DENSE:\n"
                "   - Prioritize: quantitative data, benchmark scores, "
                "technical specs, license type, architecture details, "
                "funding amounts, user/customer counts.\n"
                "   - Each bullet is ONE fact, not a sentence summary.\n"
                "   - Example good bullets:\n"
                "     * 'Apache 2.0 license, 262K native context, hybrid "
                "thinking/non-thinking architecture'\n"
                "     * 'SWE-bench Verified: 65.4% (vs Claude 3.5 Sonnet: "
                "49.0%)'\n"
                "     * 'First fully retrained base model since GPT-4.5, "
                "designed for agentic workflows'\n"
                "   - NO filler, no generic statements, no 'this is "
                "significant because...' phrasing.\n"
                "   - Every bullet must be grounded in the provided event "
                "data. Do NOT fabricate numbers or specs.\n\n"
                "4. source_label: A short label for the source link. "
                "Choose contextually, e.g. 'See Benchmark Scores', "
                "'See Full Article', 'View Funding Details', "
                "'View Technical Specs'.\n\n"
                "OUTPUT RULES:\n"
                "- Return ONLY valid JSON matching the schema below.\n"
                "- Maintain the SAME order as the input events.\n"
                "- No markdown fencing, no commentary outside JSON.\n"
                "- Newlines inside string values MUST be written as \\n.\n"
                '- Double quotes inside string values MUST be escaped as \\".\n\n'
                f"OUTPUT SCHEMA:\n```json\n{schema_json}\n```\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"EVENTS:\n\n{events_block}\n"
                "Produce the one-pager cards. Return ONLY valid JSON."
            ),
        },
    ]


def model_release_injection_prompt(
    candidates: list[dict],
    existing_radar_items: list[dict],
    existing_top_events: list[dict],
    existing_section_titles: list[str],
    executive_summary: str,
    domain: str,
    date_range: str,
) -> list[dict]:
    """Build a prompt to decide which AA model releases to inject into the
    report and produce the structured TopEvent/RadarItem/RadarItemDetail
    payloads for accepted models.

    Each candidate dict has: model_name, organization, release_date,
    modality, parameters, license, is_open_source, notable_features,
    source_url, and web_snippets (list of {title, url, snippet}).
    """
    from core.llm.output_schemas.sensing_outputs import ModelInjectionOutput

    schema_json = json.dumps(ModelInjectionOutput.model_json_schema(), indent=2)

    candidates_block = ""
    for i, c in enumerate(candidates):
        snippets = c.get("web_snippets", []) or []
        snippets_str = ""
        for j, s in enumerate(snippets[:5]):
            snippets_str += (
                f"    Snippet {j + 1}: {s.get('title', '')}\n"
                f"      URL: {s.get('url', '')}\n"
                f"      Excerpt: {s.get('snippet', '')[:300]}\n"
            )
        if not snippets_str:
            snippets_str = "    (no web search results)\n"

        candidates_block += (
            f"CANDIDATE {i + 1}: {c.get('model_name', '')}\n"
            f"  Organization: {c.get('organization', '')}\n"
            f"  Release date: {c.get('release_date', '')}\n"
            f"  Modality: {c.get('modality', '')}\n"
            f"  Parameters: {c.get('parameters', '')}\n"
            f"  License: {c.get('license', '')}\n"
            f"  Open source: {c.get('is_open_source', '')}\n"
            f"  Notable features: {c.get('notable_features', '')}\n"
            f"  AA source URL: {c.get('source_url', '')}\n"
            f"  Web snippets:\n{snippets_str}\n"
        )

    radar_block = "\n".join(
        f"  - {r.get('name', '')} [{r.get('quadrant', '')}/{r.get('ring', '')}]"
        for r in existing_radar_items
    ) or "  (none)"
    events_block = "\n".join(
        f"  - {e.get('actor', '')}: {e.get('headline', '')}"
        for e in existing_top_events
    ) or "  (none)"
    sections_block = "\n".join(f"  - {t}" for t in existing_section_titles) or "  (none)"

    return [
        {
            "role": "system",
            "parts": (
                "You are a senior technology intelligence analyst integrating "
                "fresh AI model release data (from the Artificial Analysis API "
                "and web search) into an existing technology sensing report.\n\n"
                f"DOMAIN: {domain}\n"
                f"DATE RANGE: {date_range}\n\n"
                "TASK: For each candidate model release below, decide whether "
                "to INCLUDE or SKIP it, and — for included models — produce "
                "fully-formed report content (top event, radar item, radar "
                "item deep dive, and optional executive-summary mention).\n\n"
                "DECISION RULES:\n"
                "- BE LIBERAL with inclusion. If the release is a substantive "
                "model from a credible org and would be informative for a "
                "technology leader tracking the AI landscape, INCLUDE it.\n"
                "- SKIP only when:\n"
                "  (a) the model is already covered by an existing radar item "
                "or top event below (use case-insensitive name match), OR\n"
                "  (b) the entry is not a substantive product release (e.g. a "
                "re-quantization or minor variant of an existing model with "
                "no new capability).\n"
                "- Set is_prominent=true ONLY for major foundation-model "
                "releases from major labs (OpenAI, Anthropic, Google, Meta, "
                "Mistral, DeepSeek, Alibaba/Qwen, xAI, Cohere, etc.) OR ones "
                "with clearly headline-grade benchmarks (top-3 on major "
                "leaderboards) or licensing news (e.g. notable open-weight "
                "release at frontier scale). Cap prominent count at ~3.\n\n"
                "FOR EACH INCLUDED MODEL, PRODUCE ALL FOUR OBJECTS:\n\n"
                "1. top_event:\n"
                "   - event_type = 'product_launch'\n"
                "   - headline: 1-2 sentence event description (include model "
                "name + key capability)\n"
                "   - actor: the organization\n"
                "   - impact_summary: 1-2 sentences on strategic implications\n"
                "   - strategic_intent: 1-2 sentences on why the org released this\n"
                "   - segment: industry segment (e.g., 'Foundation Models', "
                "'Open-source AI', 'Multimodal AI')\n"
                "   - related_technologies: relevant tech names (the model "
                "name plus closely-related concepts)\n"
                "   - source_urls: AA source URL + 1-2 best web snippet URLs\n"
                "   - recommendation: 1-2 sentence actionable takeaway\n\n"
                "2. radar_item:\n"
                "   - name: the model name (use the most common form, e.g. "
                "'GPT-5.5' not 'gpt-5.5-2026-04-29')\n"
                "   - quadrant: choose from 'Techniques', 'Platforms', 'Tools', "
                "'Languages & Frameworks' (most foundation models = 'Tools' "
                "or 'Platforms')\n"
                "   - ring: default to 'Trial' for new releases. Use 'Adopt' "
                "only if there is overwhelming evidence of immediate "
                "production-readiness; use 'Assess' for early/preview models\n"
                "   - description: one-sentence tooltip\n"
                "   - is_new: true (these are fresh releases by definition)\n"
                "   - signal_strength: 0.85\n"
                "   - source_count: 1 + number of web snippets you used\n"
                "   - trl: 6-7 for released models, 4-5 for previews\n"
                "   - lifecycle_stage: 'early_adoption' (default for new releases)\n\n"
                "3. radar_detail:\n"
                "   - technology_name: must match radar_item.name EXACTLY\n"
                "   - what_it_is: 2-4 sentences explaining the model and its architecture\n"
                "   - why_it_matters: 2-3 sentences on significance\n"
                "   - current_state: 2-3 sentences on maturity, "
                "availability, and recent benchmarks\n"
                "   - key_players: just the releasing organization (and "
                "co-developers if known)\n"
                "   - practical_applications: 2-4 use cases\n"
                "   - quantitative_highlights: 2-5 specific facts from "
                "AA notable_features and web snippets — benchmark scores, "
                "context lengths, parameter counts, pricing, release dates. "
                "ONLY use numbers explicitly present in the input. Do not "
                "fabricate.\n"
                "   - source_urls: same as top_event\n"
                "   - recommendation: 1-2 sentence specific guidance\n\n"
                "4. exec_summary_mention (ONLY if is_prominent=true):\n"
                "   - 1 sentence in the same tone as the existing executive "
                "summary, naming the model and its headline significance.\n\n"
                "ALSO PRODUCE section_intro: a 2-3 sentence Markdown intro "
                "for a new 'Notable Model Releases' section that frames the "
                "included releases as a group. Empty string if no models are "
                "included.\n\n"
                "OUTPUT RULES:\n"
                "- Return ONLY valid JSON matching the schema below.\n"
                "- One decision per candidate, in the same order.\n"
                "- For SKIPPED candidates: leave top_event/radar_item/"
                "radar_detail/exec_summary_mention as null/empty; fill "
                "skip_reason briefly.\n"
                "- No markdown fencing, no commentary outside JSON.\n"
                "- Newlines inside string values MUST be written as \\n.\n"
                '- Double quotes inside string values MUST be escaped as \\".\n'
                "- Do not invent benchmarks or numbers not present in the "
                "candidate data or web snippets.\n\n"
                f"OUTPUT SCHEMA:\n```json\n{schema_json}\n```\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"EXISTING RADAR ITEMS (for dedup):\n{radar_block}\n\n"
                f"EXISTING TOP EVENTS (for dedup):\n{events_block}\n\n"
                f"EXISTING REPORT SECTIONS (titles only):\n{sections_block}\n\n"
                f"CURRENT EXECUTIVE SUMMARY (for tone matching):\n"
                f"{executive_summary[:2000]}\n\n"
                f"CANDIDATE MODEL RELEASES:\n\n{candidates_block}\n"
                "Produce per-candidate decisions. Return ONLY valid JSON."
            ),
        },
    ]
