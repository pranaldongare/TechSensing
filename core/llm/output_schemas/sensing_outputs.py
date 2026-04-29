from typing import List, Optional

from pydantic import BaseModel, Field

from core.llm.output_schemas.base import LLMOutputBase


# --- Stage: Classification (per-batch) ---


class ClassifiedArticle(BaseModel):
    title: str = Field(description="Article title.")
    source: str = Field(description="Source name (e.g., 'TechCrunch', 'arXiv').")
    url: str = Field(description="Original article URL.")
    published_date: str = Field(description="Publication date in ISO format.")
    summary: str = Field(description="2-3 sentence summary of the article content.")
    relevance_score: float = Field(
        description="Relevance score 0.0-1.0 to the target domain."
    )
    quadrant: str = Field(
        description="Technology Radar quadrant: 'Techniques', 'Platforms', 'Tools', or 'Languages & Frameworks'."
    )
    ring: str = Field(
        description="Technology Radar ring: 'Adopt', 'Trial', 'Assess', or 'Hold'."
    )
    technology_name: str = Field(
        description="Short name of the technology or technique (for radar blip label)."
    )
    reasoning: str = Field(
        description="Brief reasoning for quadrant and ring placement."
    )
    topic_category: str = Field(
        default="",
        description="Topic category as defined in the classification prompt.",
    )
    industry_segment: str = Field(
        default="",
        description="Industry segment as defined in the classification prompt.",
    )


class ArticleBatchClassification(LLMOutputBase):
    articles: List[ClassifiedArticle] = Field(
        default_factory=list,
        description="List of classified articles from the batch.",
    )


# --- Stage: Document topic extraction ---


class DocumentTopicExtraction(LLMOutputBase):
    """LLM-extracted topics and search parameters from an uploaded document."""

    document_summary: str = Field(
        description="2-3 sentence summary of the document's main subject matter."
    )
    refined_domain: str = Field(
        description=(
            "A refined domain description based on document content. "
            "E.g., if user selected 'Robotics' but document is about "
            "'surgical robot arms', refine to 'Medical Robotics'."
        )
    )
    search_queries: List[str] = Field(
        description=(
            "5-10 DuckDuckGo search queries to find current web articles "
            "related to the document's key themes. Each should be a natural "
            "language search query like 'autonomous mobile robots "
            "warehouse logistics 2026'."
        )
    )
    technology_keywords: List[str] = Field(
        description=(
            "3-8 specific technology names, frameworks, or techniques "
            "mentioned or implied in the document. Used for arXiv, GitHub, "
            "and patent searches. E.g., ['ROS 2', 'SLAM', "
            "'sim-to-real transfer', 'inverse kinematics']."
        )
    )
    key_entities: List[str] = Field(
        default_factory=list,
        description=(
            "0-5 companies, organizations, or notable people referenced "
            "in the document. Used to enhance search specificity."
        ),
    )
    patent_keywords: List[str] = Field(
        default_factory=list,
        description=(
            "3-5 patent-appropriate keyword phrases for USPTO/EPO search. "
            "E.g., ['retrieval augmented generation system', "
            "'vector similarity search method']."
        ),
    )


# --- Stage: Domain Intelligence ---


class DomainIntelligence(LLMOutputBase):
    """LLM-generated domain intelligence for configuring the sensing pipeline."""

    domain_name: str = Field(
        description="Canonical name for this domain."
    )
    domain_summary: str = Field(
        description="2-3 sentence overview of the current state of this domain."
    )
    topic_categories: List[str] = Field(
        description=(
            "Exactly 5 domain-specific topic category definitions. Each should be "
            "a string like 'Category Name: Brief description of what belongs here'."
        )
    )
    industry_segments: List[str] = Field(
        description=(
            "Exactly 5 industry segment definitions. Each should be "
            "a string like 'Segment Name: Key players and description'."
        )
    )
    key_people: List[str] = Field(
        description=(
            "5-10 key people (researchers, executives, thought leaders) "
            "currently influential in this domain. Full names only."
        )
    )
    search_queries: List[str] = Field(
        description=(
            "10-15 targeted web search queries to find current news and "
            "developments in this domain. Mix broad and specific queries."
        )
    )
    rss_feed_urls: List[str] = Field(
        description=(
            "5-15 relevant RSS/Atom feed URLs for this domain. Include "
            "arXiv category feeds, subreddits (.rss), tech news sites, "
            "and official blogs. Only suggest URLs you are confident exist."
        )
    )
    arxiv_categories: List[str] = Field(
        default_factory=list,
        description="1-5 relevant arXiv category codes (e.g., 'cs.AI', 'quant-ph').",
    )
    patent_keywords: List[str] = Field(
        description=(
            "5-10 formal patent-appropriate keyword phrases for USPTO/EPO search."
        )
    )
    technology_keywords: List[str] = Field(
        description=(
            "10-20 specific technology names, frameworks, tools, techniques, "
            "and methodologies to watch in this domain."
        )
    )
    generic_terms_blocklist: List[str] = Field(
        description=(
            "10-20 terms that are too broad or generic to be standalone radar "
            "items in this domain. Include the domain name itself, broad category "
            "labels, and well-known product family names without version specifics."
        )
    )
    legacy_terms_blocklist: List[str] = Field(
        description=(
            "5-15 outdated or superseded technologies in this domain that "
            "should not appear as radar items."
        )
    )


# --- Stage: Final report ---


class TrendItem(BaseModel):
    trend_name: str = Field(description="Name of the identified trend.")
    description: str = Field(
        description="Description of the trend and its significance."
    )
    evidence: List[str] = Field(
        description="Article titles or sources supporting this trend."
    )
    impact_level: str = Field(
        description="Impact level: 'High', 'Medium', or 'Low'."
    )
    time_horizon: str = Field(
        description="Expected time to mainstream: 'Immediate (0-6mo)', 'Near-term (6-18mo)', 'Medium-term (1-3yr)', 'Long-term (3+yr)'."
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="URLs of articles supporting this trend.",
    )
    deep_dive: str = Field(
        default="",
        description="Optional deep-dive analysis in markdown (200-500 words). Populated from report_sections when a matching section exists.",
    )


class RadarItem(BaseModel):
    name: str = Field(description="Technology or technique name (radar blip label).")
    quadrant: str = Field(
        description="One of: 'Techniques', 'Platforms', 'Tools', 'Languages & Frameworks'."
    )
    ring: str = Field(
        description="One of: 'Adopt', 'Trial', 'Assess', 'Hold'."
    )
    description: str = Field(description="One-sentence description for tooltip.")
    is_new: bool = Field(
        description="Whether this technology FIRST APPEARED or was FIRST RELEASED within the lookback window. "
        "False for established technologies that are merely buzzing or trending."
    )
    moved_in: Optional[str] = Field(
        default=None,
        description="If moved, the previous ring. None if unchanged.",
    )
    signal_strength: float = Field(
        default=0.0,
        description="Composite signal confidence 0.0-1.0.",
    )
    source_count: int = Field(
        default=0,
        description="Number of distinct sources mentioning this technology.",
    )
    trl: int = Field(
        default=5,
        description=(
            "Technology Readiness Level (1-9). "
            "1=Basic principles observed, 2=Concept formulated, 3=Proof of concept, "
            "4=Lab validated, 5=Validated in relevant environment, "
            "6=Demonstrated in relevant environment, 7=Prototype in operational environment, "
            "8=System complete and qualified, 9=Proven in operational environment."
        ),
    )
    patent_count: int = Field(
        default=0,
        description="Number of related patents found for this technology.",
    )
    lifecycle_stage: str = Field(
        default="",
        description="Technology lifecycle: 'research', 'prototype', 'early_adoption', 'mainstream', 'legacy'",
    )
    funding_signal: str = Field(
        default="",
        description="Recent funding or investment signal, if any.",
    )
    momentum: str = Field(
        default="",
        description="Momentum direction: 'rising', 'stable', or 'declining'. Computed from movement history.",
    )


class RadarItemDetail(BaseModel):
    technology_name: str = Field(
        description="Technology name (must match a RadarItem name)."
    )
    what_it_is: str = Field(
        description="Clear explanation of what this technology is and how it works (2-4 sentences)."
    )
    why_it_matters: str = Field(
        description="Why this technology is significant and what problems it solves (2-3 sentences)."
    )
    current_state: str = Field(
        description="Current maturity, adoption level, and key developments this week (2-3 sentences)."
    )
    key_players: List[str] = Field(
        description=(
            "Companies or organizations that actively develop, maintain, or officially "
            "release this technology. Do NOT include entities that only published the "
            "underlying research paper unless they also released the implementation."
        )
    )
    practical_applications: List[str] = Field(
        description="Real-world use cases and applications (2-4 items)."
    )
    quantitative_highlights: List[str] = Field(
        default_factory=list,
        description=(
            "2-5 specific quantitative facts extracted from the articles — "
            "benchmark scores, performance metrics, adoption numbers, speed/cost comparisons, "
            "accuracy percentages, latency figures, parameter counts, etc. "
            "Each item must cite the number and its context, e.g. "
            "'Achieves 92.3% accuracy on MMLU, up from 86.4% in the previous version' or "
            "'Reduces inference cost by 40% compared to GPT-4 Turbo'. "
            "Only include numbers explicitly stated in the articles — do NOT fabricate metrics."
        ),
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="URLs of articles informing this technology write-up.",
    )
    hiring_indicators: str = Field(
        default="",
        description=(
            "Brief summary of hiring trends related to this technology "
            "(e.g. growing demand, notable job postings, skill requirements). "
            "Leave empty if no hiring signals found in articles."
        ),
    )
    recommendation: str = Field(
        default="",
        description=(
            "1-2 sentence actionable recommendation for technology leaders "
            "regarding this technology. What should they evaluate, adopt, "
            "pilot, or monitor? Be specific and grounded in the evidence."
        ),
    )


class TrendingVideoItem(BaseModel):
    """A trending YouTube video associated with a radar technology."""

    technology_name: str = Field(
        description="Radar item name this video is associated with."
    )
    title: str = Field(description="Video title.")
    url: str = Field(description="YouTube video URL.")
    description: str = Field(default="", description="Video description excerpt.")
    uploader: str = Field(default="", description="YouTube channel name.")
    duration: str = Field(default="", description="Video duration (e.g., '12:34').")
    published: str = Field(default="", description="Publication date.")
    view_count: int = Field(default=0, description="Number of views.")
    thumbnail_url: str = Field(default="", description="Thumbnail image URL.")


class HeadlineMove(BaseModel):
    """A top headline development of the week, ranked by significance."""

    headline: str = Field(description="1-2 sentence description of the move.")
    actor: str = Field(description="Person or organization that made this move.")
    segment: str = Field(
        description="Industry segment of the actor."
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="URLs of articles reporting this move.",
    )


class MarketSignal(BaseModel):
    company_or_player: str = Field(
        description="Name of the company, major player, or key individual leader."
    )
    signal: str = Field(
        description="What they announced, released, or are doing (2-3 sentences)."
    )
    strategic_intent: str = Field(
        description="Why they are doing this — strategic reasoning (1-2 sentences)."
    )
    industry_impact: str = Field(
        description="How this affects the broader industry direction (1-2 sentences)."
    )
    segment: str = Field(
        default="",
        description="Industry segment of the company or player.",
    )
    related_technologies: List[str] = Field(
        description="Technology names related to this signal."
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="URLs of articles reporting this signal.",
    )


class ReportSection(BaseModel):
    section_title: str = Field(description="Section heading.")
    content: str = Field(description="Section body content in markdown format.")
    source_urls: List[str] = Field(
        default_factory=list,
        description="URLs of articles referenced in this section.",
    )


class TopEvent(BaseModel):
    """A top event of the week, merging headline moves and market signals."""

    headline: str = Field(description="1-2 sentence description of the event.")
    actor: str = Field(description="Person or organization behind this event.")
    event_type: str = Field(
        description=(
            "Event category: 'product_launch', 'partnership', 'funding', "
            "'regulation', 'research', or 'strategic_move'."
        )
    )
    impact_summary: str = Field(
        default="",
        description="Why this event matters — strategic implications (1-2 sentences).",
    )
    strategic_intent: str = Field(
        default="",
        description="Why the actor is doing this — strategic reasoning (1-2 sentences).",
    )
    segment: str = Field(
        default="",
        description="Industry segment of the actor.",
    )
    related_technologies: List[str] = Field(
        default_factory=list,
        description="Radar item names related to this event.",
    )
    source_urls: List[str] = Field(
        default_factory=list,
        description="URLs of articles reporting this event.",
    )
    recommendation: str = Field(
        default="",
        description=(
            "1-2 sentence actionable recommendation for technology leaders "
            "based on this event. What should they do, evaluate, or watch? "
            "Leave empty only if no actionable takeaway is possible."
        ),
    )


class BlindSpot(BaseModel):
    """A coverage gap or underrepresented area in the report."""

    area: str = Field(description="Topic, region, or perspective that is missing.")
    why_it_matters: str = Field(
        description="Why this gap matters for decision-making (1-2 sentences)."
    )
    suggested_sources: List[str] = Field(
        default_factory=list,
        description="Suggested sources or search terms to fill this gap.",
    )


class Recommendation(BaseModel):
    title: str = Field(description="Recommendation title.")
    description: str = Field(description="Actionable recommendation description.")
    priority: str = Field(
        description="Priority: 'Critical', 'High', 'Medium', 'Low'."
    )
    related_trends: List[str] = Field(
        description="Names of trends this recommendation relates to."
    )
    rationale: str = Field(
        default="",
        description="Why this recommendation matters now — the driving context (1-2 sentences).",
    )
    effort: str = Field(
        default="",
        description="Implementation effort: 'Low', 'Medium', or 'High'.",
    )
    urgency: str = Field(
        default="",
        description="Time urgency: 'Immediate', 'Short-term', 'Medium-term', or 'Long-term'.",
    )


class CompetitorEntry(BaseModel):
    name: str = Field(description="Competitor or alternative name.")
    approach: str = Field(description="Their approach or methodology.")
    strengths: str = Field(description="Key strengths.")
    weaknesses: str = Field(description="Key weaknesses.")


class KeyResource(BaseModel):
    title: str = Field(description="Resource title.")
    url: str = Field(default="", description="URL if available.")
    type: str = Field(description="Resource type: 'paper', 'repo', 'article', 'docs'.")


class DeepDiveReport(LLMOutputBase):
    technology_name: str = Field(description="Name of the technology analyzed.")
    comprehensive_analysis: str = Field(
        description="Detailed analysis (500-1000 words) in markdown format."
    )
    technical_architecture: str = Field(
        description="Technical architecture or how it works (200-400 words)."
    )
    competitive_landscape: List[CompetitorEntry] = Field(
        description="3-6 competitors or alternatives with comparison."
    )
    adoption_roadmap: str = Field(
        description="Recommended adoption roadmap for organizations (200-300 words)."
    )
    risk_assessment: str = Field(
        description="Risk assessment and mitigation strategies (150-300 words)."
    )
    key_resources: List[KeyResource] = Field(
        description="5-10 key resources (papers, repos, articles, docs)."
    )
    recommendations: List[str] = Field(
        description="3-5 actionable recommendations."
    )


class TopicHighlight(BaseModel):
    """A brief topic-level update for the executive summary."""

    topic: str = Field(
        description="Short topic label (2-4 words), e.g. 'Video Generation', 'Agentic AI', 'LLM Efficiency'."
    )
    update: str = Field(
        description="1-2 sentence summary of the most important development in this topic area this week."
    )


class ReportCore(LLMOutputBase):
    """Phase 1 output: executive overview, top events, and key trends."""

    report_title: str = Field(description="Report title including date range.")
    bottom_line: str = Field(
        default="",
        description="2-3 sentence 'so what' — the single most important takeaway for a CTO this week.",
    )
    executive_summary: str = Field(
        description=(
            "Executive summary in markdown (200-350 words), structured in three parts: "
            "**What Happened** (key facts), **Why It Matters** (strategic implications), "
            "**What To Do** (recommended actions). Use bold, bullets, and separate paragraphs."
        )
    )
    topic_highlights: List[TopicHighlight] = Field(
        default_factory=list,
        description=(
            "4-8 quick topic-level updates summarizing the key development in each major "
            "area covered by the report. Each entry has a short topic label and a 1-2 sentence "
            "update. These provide a scannable at-a-glance view of what moved this week."
        ),
    )
    domain: str = Field(description="The domain analyzed.")
    date_range: str = Field(
        description="Date range covered (e.g., 'Mar 20-27, 2026')."
    )
    total_articles_analyzed: int = Field(
        description="Total number of articles analyzed."
    )
    top_events: List[TopEvent] = Field(
        default_factory=list,
        description="Top 10 most impactful events of the week, ranked by significance.",
    )
    headline_moves: List[HeadlineMove] = Field(
        default_factory=list,
        description="(Legacy) Top headline developments. Populated from top_events for backward compat.",
    )
    key_trends: List[TrendItem] = Field(
        description="List of 5-10 key trends identified."
    )


class ReportRadar(LLMOutputBase):
    """Phase 2 output: technology radar entries."""

    radar_items: List[RadarItem] = Field(
        description="Technology radar entries (10-20 items)."
    )


class ReportInsights(LLMOutputBase):
    """Phase 3 output: analysis sections, recommendations, notable articles, blind spots."""

    market_signals: List[MarketSignal] = Field(
        default_factory=list,
        description="(Legacy) Market signals. Kept for backward compat; new reports populate from top_events.",
    )
    report_sections: List[ReportSection] = Field(
        description="3-6 detailed report sections in markdown. Each should align with a key trend for deep-dive linking."
    )
    recommendations: List[Recommendation] = Field(
        description="3-7 actionable recommendations with rationale, effort, and urgency."
    )
    notable_articles: List[ClassifiedArticle] = Field(
        description="Top 5-10 most notable articles with full classification."
    )
    blind_spots: List[BlindSpot] = Field(
        default_factory=list,
        description="2-4 coverage blind spots — topics, regions, or perspectives underrepresented in this report.",
    )


class RadarDetailsOutput(LLMOutputBase):
    """Phase 4 output: detailed write-ups for each radar item."""

    radar_item_details: List[RadarItemDetail] = Field(
        description="Detailed write-up for each radar item — what it is, why it matters, who is using it, practical applications."
    )


class ModelRelease(BaseModel):
    """A recently released AI model."""

    model_name: str = Field(description="Model name (e.g., 'Llama 4 Maverick').")
    organization: str = Field(description="Organization that released the model.")
    release_date: str = Field(
        description=(
            "Release / announcement date in YYYY-MM-DD format. Use the "
            "exact date when known; if only a month is known, use the "
            "first of the month. This may be a FUTURE date if the model "
            "has been announced but not yet shipped. Leave empty if no "
            "date can be established from the sources."
        )
    )
    release_status: str = Field(
        default="Unknown",
        description=(
            "Current status of the model. One of: 'Released' (generally "
            "available / weights downloadable as of today), 'Announced' "
            "(publicly announced but not yet shipped — includes private "
            "preview, waitlist, early access, and any future-dated "
            "launch), 'Upcoming' (dated release scheduled for a future "
            "date), 'Preview' (public preview/beta accessible to some "
            "users), or 'Unknown'. When the article says 'plans to "
            "release', 'will launch', 'is expected to ship', 'coming "
            "soon', or gives a future date, use 'Announced' or "
            "'Upcoming' — NOT 'Released'."
        ),
    )
    parameters: str = Field(
        default="Unknown",
        description="Parameter count (e.g., '400B MoE (17B active)').",
    )
    license: str = Field(
        default="Unknown",
        description="License type (e.g., 'Apache 2.0', 'Proprietary').",
    )
    is_open_source: str = Field(
        default="Unknown",
        description=(
            "Open-source status. One of: 'Open' (weights publicly "
            "downloadable under an OSI/open-weights license such as MIT, "
            "Apache 2.0, Llama Community, Mistral-style, etc.), 'Closed' "
            "(API-only or proprietary weights), 'Mixed' (partially open — "
            "e.g. small variants open, flagship closed), or 'Unknown'."
        ),
    )
    model_type: str = Field(
        default="Unknown",
        description=(
            "Architecture type (e.g., 'Transformer', 'MoE', 'Mamba', "
            "'Hybrid', 'Diffusion', 'State-space', 'Flow-matching')."
        ),
    )
    modality: str = Field(
        default="Text",
        description=(
            "Primary modality or task category. Prefer one of: 'Text' "
            "(LLMs), 'Multimodal' (accepts multiple modalities), 'Image' "
            "(image generation/editing), 'Video' (video generation or "
            "understanding), 'Audio' (speech/music/general audio), "
            "'Speech' (ASR/TTS), 'Code' (code generation), 'World Model' "
            "(world simulation / predictive world models), 'Action' "
            "(robotic action / VLA / agentic control), 'Embedding' "
            "(retrieval/encoder), '3D' (3D/scene generation), 'Reasoning' "
            "(reasoning-focused), 'Other'."
        ),
    )
    notable_features: str = Field(
        default="",
        description="1-2 sentence summary of notable features.",
    )
    source_url: str = Field(default="", description="Link to announcement or paper.")
    data_source: str = Field(
        default="",
        description="Data source identifier (e.g., 'Artificial Analysis', 'HuggingFace').",
    )


class ModelReleasesOutput(LLMOutputBase):
    """LLM extraction output for model releases."""

    model_releases: List[ModelRelease] = Field(
        default_factory=list,
        description="List of recently released models.",
    )


class EnhancerOutput(LLMOutputBase):
    """LLM output: additional report entries from orphan articles missed in the first pass."""

    additional_events: List[TopEvent] = Field(
        default_factory=list,
        description=(
            "0-3 significant events from orphan articles that were missed in the report. "
            "Only include events that are genuinely important and distinct from existing coverage."
        ),
    )
    additional_radar_items: List[RadarItem] = Field(
        default_factory=list,
        description=(
            "0-5 technology radar entries from orphan articles not covered in the report. "
            "Only include technologies with clear evidence from the provided articles."
        ),
    )
    additional_recommendations: List[Recommendation] = Field(
        default_factory=list,
        description=(
            "0-2 actionable recommendations based on gaps found in orphan articles. "
            "Only include if the gap reveals a meaningful strategic consideration."
        ),
    )
    skipped_articles: List[str] = Field(
        default_factory=list,
        description="Titles of orphan articles that were correctly omitted (not important enough to add).",
    )
    enhancement_summary: str = Field(
        default="",
        description="1-2 sentence summary of what was added, or 'No enhancements needed' if nothing was added.",
    )


class SelfEvalOutput(LLMOutputBase):
    """LLM-as-judge evaluation of a completed tech sensing report."""

    coverage_score: int = Field(
        description="1-5: Did the report cover all major developments in the domain?"
    )
    specificity_score: int = Field(
        description="1-5: Are radar items specific technologies vs generic categories?"
    )
    novelty_accuracy_score: int = Field(
        description="1-5: Are items marked 'new' genuinely new, not established tech?"
    )
    actionability_score: int = Field(
        description="1-5: Are recommendations concrete and actionable?"
    )
    coherence_score: int = Field(
        description="1-5: Is the report well-structured, non-repetitive, and logically organized?"
    )
    overall_score: float = Field(
        description="Weighted average of all scores (1.0-5.0)."
    )
    strengths: List[str] = Field(
        description="2-3 specific things the report did well."
    )
    weaknesses: List[str] = Field(
        description="2-3 specific things to improve in the next report for this domain."
    )
    missed_topics: List[str] = Field(
        default_factory=list,
        description="Topics or technologies that should have been covered but weren't.",
    )
    reflection: str = Field(
        description=(
            "2-3 sentence self-reflection for the next run. Write as direct "
            "instructions to your future self, e.g., 'Next time, pay more "
            "attention to edge computing developments.'"
        ),
    )


class PromptPatchOutput(LLMOutputBase):
    """LLM-generated prompt improvements based on experience patterns."""

    classification_guidance: str = Field(
        default="",
        description=(
            "Extra guidance to inject into the article classifier prompt. "
            "Leave empty if no changes needed. Write as direct instructions."
        ),
    )
    radar_guidance: str = Field(
        default="",
        description=(
            "Extra guidance to inject into the radar generation prompt. "
            "Leave empty if no changes needed. Write as direct instructions."
        ),
    )
    verification_guidance: str = Field(
        default="",
        description=(
            "Extra guidance to inject into the verifier prompt. "
            "Leave empty if no changes needed. Write as direct instructions."
        ),
    )
    rationale: str = Field(
        description="Brief explanation of why these prompt changes were suggested."
    )


class TechSensingReport(LLMOutputBase):
    """Full report (assembled from Phase 1 core + Phase 2 radar + Phase 3 insights + Phase 4 details)."""

    schema_version: str = Field(
        default="1.0",
        description="Schema version for backward compat. '2.0' for reports with top_events/blind_spots.",
    )
    report_title: str = Field(description="Report title including date range.")
    bottom_line: str = Field(
        default="",
        description="2-3 sentence 'so what' — the single most important takeaway.",
    )
    executive_summary: str = Field(
        description="Executive summary in markdown (200-350 words)."
    )
    topic_highlights: List[TopicHighlight] = Field(
        default_factory=list,
        description="4-8 quick topic-level updates for at-a-glance scanning.",
    )
    domain: str = Field(description="The domain analyzed (e.g., 'Generative AI').")
    date_range: str = Field(
        description="Date range covered (e.g., 'Mar 20-27, 2026')."
    )
    total_articles_analyzed: int = Field(
        description="Total number of articles analyzed."
    )
    top_events: List[TopEvent] = Field(
        default_factory=list,
        description="Top 10 most impactful events of the week (v2.0+).",
    )
    headline_moves: List[HeadlineMove] = Field(
        default_factory=list,
        description="(Legacy) Top headline developments. Populated from top_events for backward compat.",
    )
    key_trends: List[TrendItem] = Field(
        description="List of 5-10 key trends identified."
    )
    report_sections: List[ReportSection] = Field(
        description="3-6 detailed report sections in markdown."
    )
    radar_items: List[RadarItem] = Field(
        description="Technology radar entries (10-20 items)."
    )
    radar_item_details: List[RadarItemDetail] = Field(
        description="Detailed write-up for each radar item."
    )
    market_signals: List[MarketSignal] = Field(
        default_factory=list,
        description="(Legacy) Market signals. Populated from top_events for backward compat.",
    )
    recommendations: List[Recommendation] = Field(
        description="3-7 actionable recommendations with rationale, effort, and urgency."
    )
    notable_articles: List[ClassifiedArticle] = Field(
        description="Top 5-10 most notable articles with full classification."
    )
    blind_spots: List["BlindSpot"] = Field(
        default_factory=list,
        description="Coverage gaps — topics/regions/perspectives underrepresented in this report.",
    )
    trending_videos: List[TrendingVideoItem] = Field(
        default_factory=list,
        description="Trending YouTube videos for radar technologies.",
    )
    weak_signals: List["WeakSignal"] = Field(
        default_factory=list,
        description="Emerging technologies with low visibility but high growth rate.",
    )
    relationships: Optional["TechRelationshipMap"] = Field(
        default=None,
        description="Technology relationship graph with edges and clusters.",
    )
    model_releases: List[ModelRelease] = Field(
        default_factory=list,
        description="Recent model releases (GenAI domain only).",
    )
    report_confidence: str = Field(
        default="medium",
        description="Overall report confidence: 'high', 'medium', or 'low'.",
    )
    confidence_note: str = Field(
        default="",
        description="Human-readable confidence explanation.",
    )
    confidence_factors: dict = Field(
        default_factory=dict,
        description="Breakdown of confidence factors.",
    )


# --- Weak Signal Models (used by weak_signals.py, rendered in report) ---


class WeakSignalTrajectoryPoint(BaseModel):
    """Historical data point for a weak signal."""

    run_date: str = Field(description="ISO date of the sensing run.")
    article_count: int = Field(description="Number of articles in that run.")
    source_count: int = Field(description="Number of distinct sources.")
    avg_relevance: float = Field(description="Average relevance score.")
    signal_strength: float = Field(description="Signal strength at that time.")


class WeakSignal(BaseModel):
    """An emerging technology with low visibility but high growth rate."""

    technology_name: str = Field(description="Name of the emerging technology.")
    current_strength: float = Field(description="Current signal strength (0.0-1.0).")
    acceleration_rate: float = Field(
        description="Growth rate vs historical average. >2.0 = breakout."
    )
    first_seen: str = Field(description="ISO date when first detected.")
    run_count: int = Field(description="Number of runs this technology appeared in.")
    trajectory: List[WeakSignalTrajectoryPoint] = Field(
        default_factory=list,
        description="Historical data points for sparkline rendering.",
    )
    dvi_score: float = Field(
        default=0.0, description="Composite DVI score (0.0-1.0)."
    )


# --- Technology Relationship Models (used by relationships.py) ---


class TechRelationship(BaseModel):
    """A relationship between two radar technologies, grounded in article evidence."""

    source_tech: str = Field(description="Source technology name (must match a radar item).")
    target_tech: str = Field(description="Target technology name (must match a radar item).")
    relationship_type: str = Field(
        description=(
            "Type of relationship: 'enables' (source powers/is foundation for target), "
            "'competes_with' (serve similar purpose or are alternatives), "
            "'integrates_with' (commonly used together), or "
            "'evolves_from' (source is successor/evolution of target)."
        )
    )
    confidence: str = Field(
        description="How confident is this relationship: 'high', 'medium', or 'low'."
    )
    evidence: str = Field(
        description="1-3 sentence explanation of WHY these technologies are related, citing specific article findings."
    )
    # Filled post-LLM from co-occurrence data, not by the LLM itself
    article_count: int = Field(
        default=0, description="Number of articles where both technologies co-occur."
    )
    strength: float = Field(
        default=0.0, description="Data-grounded relationship strength 0.0-1.0 (computed post-LLM)."
    )


class TechCluster(BaseModel):
    """A cluster of related technologies."""

    cluster_name: str = Field(description="Name of the technology cluster.")
    technologies: List[str] = Field(description="Technology names in this cluster.")
    theme: str = Field(description="Brief theme description for the cluster.")
    rationale: str = Field(
        default="",
        description="Why these technologies belong together — what connects them beyond surface similarity.",
    )


class TechRelationshipMap(LLMOutputBase):
    """Complete technology relationship graph."""

    relationships: List[TechRelationship] = Field(
        default_factory=list,
        description="Relationships between radar technologies, grounded in article co-occurrence evidence.",
    )
    clusters: List[TechCluster] = Field(
        default_factory=list,
        description="3-6 technology clusters with rationale.",
    )


# Resolve forward references
TechSensingReport.model_rebuild()
