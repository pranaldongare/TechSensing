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
                + (
                    f"\nADDITIONAL USER REQUIREMENTS:\n{custom_requirements}\n"
                    if custom_requirements
                    else ""
                )
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
                + industry_segments_text + "\n"
                + people_block
                + "SECTION GUIDELINES:\n"
                "- Headline moves: Identify the TOP 10 most impactful developments of the week, "
                "ranked by significance across ALL segments. Each move should name the actor "
                "(person or organization), describe what happened in 1-2 sentences, and tag its "
                "industry segment.\n\n"
                "- Executive summary: decisive, forward-looking, 200-350 words. "
                "Use markdown formatting: bold (**term**) for key technologies, "
                "bullet points for the top 3-5 highlights, and separate paragraphs. "
                "Do NOT write it as a single wall of text.\n\n"
                "- Key trends: identify 5-10 major trends with supporting evidence from the articles. "
                "Each trend should have a clear description of WHY it matters.\n\n"
                "GROUNDING AND CITATION RULES:\n"
                "- Every claim MUST be grounded in the provided articles.\n"
                "- Use article URLs to populate source_urls arrays (1-5 per entry).\n"
                "- If an article includes a 'content_excerpt' field, use it for deeper context.\n"
                "- Do NOT fabricate information not present in the articles.\n\n"
                + (
                    f"ADDITIONAL USER REQUIREMENTS:\n{custom_requirements}\n\n"
                    if custom_requirements
                    else ""
                )
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
                "Generate the report core: report_title, executive_summary, domain, "
                "date_range, total_articles_analyzed, headline_moves, key_trends. "
                "Return ONLY valid JSON."
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
                "RADAR GUIDELINES:\n"
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
                "- ONLY include technologies that are NEW or have been SIGNIFICANTLY UPDATED "
                "within the last 6 months.\n"
                "- Do NOT create radar items for legacy or well-established technologies "
                "that are merely MENTIONED in articles as historical context, comparison, "
                "or background.\n"
                "- If an article compares a new technology with an older one, only the NEW one "
                "should be a radar item — the older one is just context.\n"
                "- Technologies in the 'Hold' ring must still be recent enough to warrant tracking.\n\n"
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
                "Phase 1 (executive summary, headline moves, key trends) and "
                "Phase 2 (technology radar items) have already been generated. "
                "You will now generate: market signals, deep-dive report sections, "
                "recommendations, and notable articles.\n\n"
                "Use the Phase 1 and Phase 2 context to ensure consistency.\n\n"
                f"DOMAIN FOCUS: All content must be directly relevant to '{domain}'. "
                "Exclude market signals and recommendations about other technology domains.\n\n"
                + industry_segments_text + "\n"
                + people_block
                + "SECTION GUIDELINES:\n"
                "- Market signals: 5-10 signals from companies AND key individual leaders "
                "(CEO statements, researcher announcements, investor moves). For each signal:\n"
                "  * What the company/person announced or is doing\n"
                "  * Their strategic intent (why they are doing this)\n"
                "  * How it impacts the broader industry direction\n"
                "  * Industry segment tag\n"
                "  * Related technologies from the radar\n\n"
                "- Report sections: 3-6 deep-dive sections with markdown formatting. "
                "Elaborate on the most important themes with practical context and technical depth.\n\n"
                "- Recommendations: actionable, prioritized, linked to trends. "
                "Frame for an enterprise technology and strategy leader.\n\n"
                "- Notable articles: select the 5-10 most impactful articles.\n\n"
                "GROUNDING AND CITATION RULES:\n"
                "- Every claim MUST be grounded in the provided articles.\n"
                "- Use article URLs to populate source_urls arrays (1-5 per entry).\n"
                "- If an article includes a 'content_excerpt' field, use it for deeper context.\n"
                "- Do NOT fabricate information not present in the articles.\n\n"
                "ATTRIBUTION ACCURACY RULES:\n"
                "- Distinguish between research authors and implementation authors.\n"
                "- For market_signals: The company_or_player must be the entity that TOOK THE ACTION.\n"
                "- If the articles don't clearly state who built something, say so.\n\n"
                + (
                    f"ADDITIONAL USER REQUIREMENTS:\n{custom_requirements}\n\n"
                    if custom_requirements
                    else ""
                )
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DATE RANGE: {date_range}\n"
                f"DOMAIN: {domain}\n\n"
                f"PHASE 1 CONTEXT (headline moves and key trends):\n{core_context_json}\n\n"
                f"PHASE 2 CONTEXT (radar items):\n{radar_context_json}\n\n"
                f"CLASSIFIED ARTICLES:\n\n{classified_articles_json}\n\n"
                "Generate: market_signals, report_sections, recommendations, "
                "notable_articles. Return ONLY valid JSON."
            ),
        },
    ]
    return contents


def sensing_details_prompt(
    radar_items_json: str,
    classified_articles_json: str,
    domain: str = "Technology",
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
                "You are given a list of RADAR ITEMS (name, quadrant, ring) and the "
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
                "  * source_urls: URLs of articles informing this write-up.\n\n"
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
                "OUTPUT RULES:\n"
                "- Return ONLY a valid JSON object with one key: radar_item_details (array).\n"
                "- Each element must have: technology_name, what_it_is, why_it_matters, "
                "current_state, key_players, practical_applications, source_urls.\n"
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
    radar_items_json: str,
    classified_articles_json: str,
    domain: str = "Technology",
) -> list[dict]:
    """
    Build a prompt to extract technology relationships and clusters
    from the radar items and supporting articles.
    """
    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology strategist analyzing the relationships "
                f"between technologies in the {domain} domain.\n\n"
                "Given a list of RADAR ITEMS and CLASSIFIED ARTICLES, identify:\n\n"
                "1. RELATIONSHIPS between technologies (10-30):\n"
                "   For each relationship, provide:\n"
                "   - source_tech: Name of the source technology (must match a radar item)\n"
                "   - target_tech: Name of the target technology (must match a radar item)\n"
                "   - relationship_type: One of:\n"
                "     * 'builds_on' — source extends or is built upon target\n"
                "     * 'competes_with' — source and target serve similar purpose\n"
                "     * 'enables' — source enables or powers target\n"
                "     * 'integrates_with' — source and target commonly used together\n"
                "     * 'alternative_to' — source is an alternative to target\n"
                "   - strength: 0.0-1.0 (how strong the relationship is)\n"
                "   - evidence: 1-2 sentence justification from the articles\n\n"
                "2. CLUSTERS of related technologies (3-6):\n"
                "   - cluster_name: Descriptive cluster name\n"
                "   - technologies: List of technology names in the cluster\n"
                "   - theme: Brief theme description\n\n"
                "RULES:\n"
                "- Technology names MUST exactly match radar item names.\n"
                "- Every relationship must be grounded in article evidence.\n"
                "- Do NOT create self-referencing relationships.\n"
                "- Avoid duplicate pairs (if A→B exists, don't add B→A with same type).\n"
                "- Do NOT fabricate relationships not supported by the articles.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n\n"
                f"RADAR ITEMS:\n{radar_items_json}\n\n"
                f"CLASSIFIED ARTICLES:\n{classified_articles_json}\n\n"
                "Extract technology relationships and clusters. "
                "Return ONLY valid JSON with 'relationships' and 'clusters' arrays."
            ),
        },
    ]
    return contents


def sensing_deep_dive_followup_prompt(
    technology_name: str,
    domain: str,
    question: str,
    conversation_history: list[dict],
    original_report_context: str,
    fresh_search_results: str = "",
) -> list[dict]:
    """
    Build a prompt for conversational follow-up on a deep dive report.

    Includes the original deep dive context and conversation history.
    """
    # Format conversation history (last 10 exchanges)
    history_block = ""
    recent_history = conversation_history[-10:]
    if recent_history:
        turns = []
        for msg in recent_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            turns.append(f"{role.upper()}: {content}")
        history_block = (
            "\nCONVERSATION HISTORY:\n"
            + "\n".join(turns)
            + "\n"
        )

    search_block = ""
    if fresh_search_results:
        search_block = (
            "\nFRESH SEARCH RESULTS (use these for current information):\n"
            f"{fresh_search_results}\n"
        )

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology analyst having a deep-dive conversation "
                f"about {technology_name} in the {domain} domain.\n\n"
                "You have already produced a detailed deep dive report on this technology. "
                "The user is asking follow-up questions to learn more.\n\n"
                "ORIGINAL DEEP DIVE CONTEXT:\n"
                f"{original_report_context}\n"
                + history_block
                + search_block
                + "\nRULES:\n"
                "- Answer the question thoroughly in markdown format.\n"
                "- Reference the original report context where relevant.\n"
                "- If fresh search results are provided, incorporate new information.\n"
                "- Suggest 3 natural follow-up questions the user might want to ask next.\n"
                "- Be concise but substantive (200-500 words for the answer).\n"
                "- If you don't have enough context, say so honestly.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"Question about {technology_name}:\n\n{question}\n\n"
                "Provide a detailed answer, list any sources used, and suggest "
                "3 follow-up questions. Return ONLY valid JSON."
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
                f"relevant to the {domain} domain.\n"
                + (
                    f"\nADDITIONAL USER REQUIREMENTS:\n{custom_requirements}\n"
                    if custom_requirements
                    else ""
                )
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

    requirements_block = ""
    if custom_requirements:
        requirements_block = (
            f"\nADDITIONAL USER REQUIREMENTS:\n{custom_requirements}\n"
        )

    contents = [
        {
            "role": "system",
            "parts": (
                "You are a senior technology intelligence analyst. Your task is to "
                f"generate comprehensive domain intelligence for the '{domain}' domain "
                "to configure a technology sensing pipeline.\n\n"
                "This intelligence will be used to:\n"
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
                + requirements_block
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
