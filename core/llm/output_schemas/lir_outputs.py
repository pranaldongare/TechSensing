"""
LIR LLM output schemas — structured outputs for signal extraction
and concept canonicalization.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from core.llm.output_schemas.base import LLMOutputBase


# ──────────────────────── Signal extraction ────────────────────────


class ExtractedSignal(BaseModel):
    """A single weak signal extracted from a raw item."""

    concept_label: str = Field(
        description=(
            "Short, specific technology concept label (2-5 words). "
            "E.g., 'Mixture of Experts', 'Ring Attention', 'RLHF alternatives'."
        )
    )
    stated_novelty: float = Field(
        description=(
            "How novel is this concept? 0.0 = well-known/incremental, "
            "1.0 = genuinely new/breakthrough. Based on the text's own claims."
        )
    )
    relevance_score: float = Field(
        description="Relevance to forward-looking technology trends (0.0-1.0)."
    )
    summary: str = Field(
        description="1-2 sentence summary of what the signal is about."
    )
    evidence_quote: str = Field(
        description="Key quote or phrase from the source supporting this signal."
    )


class LIRSignalExtraction(LLMOutputBase):
    """LLM output: extracted signals from a batch of raw items."""

    signals: List[ExtractedSignal] = Field(
        default_factory=list,
        description="List of extracted weak signals from the input items.",
    )


# ──────────────────────── Concept canonicalization ────────────────────────


class ConceptMatch(BaseModel):
    """Result of matching a raw concept label to the existing registry."""

    raw_label: str = Field(
        description="The raw concept label from signal extraction."
    )
    action: str = Field(
        description=(
            "One of: 'match' (maps to existing concept), "
            "'alias' (new name for existing concept), "
            "'new' (genuinely new concept)."
        )
    )
    matched_concept_id: Optional[str] = Field(
        default=None,
        description="If action is 'match' or 'alias', the existing concept_id.",
    )
    canonical_name: Optional[str] = Field(
        default=None,
        description="If action is 'new', the canonical display name for the new concept.",
    )
    description: Optional[str] = Field(
        default=None,
        description="If action is 'new', a 1-sentence description of the concept.",
    )
    domain_tags: List[str] = Field(
        default_factory=list,
        description="Domain tags for the concept (e.g., 'NLP', 'Computer Vision', 'MLOps').",
    )
    confidence: float = Field(
        default=0.8,
        description="Confidence in this matching decision (0.0-1.0).",
    )


class LIRCanonicalization(LLMOutputBase):
    """LLM output: concept canonicalization results for a batch of labels."""

    matches: List[ConceptMatch] = Field(
        default_factory=list,
        description="Canonicalization decisions for each input concept label.",
    )


# ──────────────────────── Rationale generation ────────────────────────


class LIRRationale(LLMOutputBase):
    """LLM output: human-readable rationale for a concept's LIR ranking."""

    summary: str = Field(
        description=(
            "A 2-3 sentence summary explaining why this concept is on the radar "
            "and what its trajectory suggests. Written for a technical decision-maker."
        )
    )
    key_drivers: List[str] = Field(
        default_factory=list,
        description="1-3 bullet points identifying the main score drivers.",
    )
    risk_factors: List[str] = Field(
        default_factory=list,
        description="0-2 bullet points on risks or caveats (e.g., hype risk, narrow applicability).",
    )
    recommended_action: str = Field(
        default="",
        description=(
            "One-line recommended action for engineering teams "
            "(e.g., 'Assign a spike to evaluate X for your Y pipeline')."
        ),
    )
