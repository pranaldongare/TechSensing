"""
LIR data models — dataclasses for raw items, concepts, signals, and scores.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class LIRRawItem:
    """A single item ingested from a LIR source adapter."""

    item_id: str               # Unique ID (source_id:hash)
    source_id: str             # e.g. "arxiv", "github", "hackernews"
    tier: str                  # "T1", "T2", "T3", "T4"
    title: str
    url: str
    published_date: str        # ISO format
    snippet: str = ""
    content: str = ""
    authors: str = ""
    categories: str = ""       # Pipe-separated tags/categories
    metadata: Dict = field(default_factory=dict)


@dataclass
class LIRSignalRecord:
    """An extracted signal from a raw item, linked to a concept."""

    signal_id: str             # Unique ID
    item_id: str               # Source LIRRawItem.item_id
    source_id: str
    tier: str
    concept_label: str         # Raw concept label from extraction
    canonical_concept_id: Optional[str] = None  # Linked after canonicalization
    stated_novelty: float = 0.5  # 0-1 from LLM extraction
    relevance_score: float = 0.5
    summary: str = ""
    evidence_quote: str = ""
    url: str = ""
    published_date: str = ""
    extracted_at: str = ""     # ISO timestamp of extraction


@dataclass
class LIRConcept:
    """A canonical concept in the LIR registry."""

    concept_id: str            # Slugified unique ID
    canonical_name: str        # Display name
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    domain_tags: List[str] = field(default_factory=list)
    created_at: str = ""       # ISO timestamp
    updated_at: str = ""       # ISO timestamp
    signal_count: int = 0      # Number of linked signals
    source_tiers: List[str] = field(default_factory=list)  # Unique tiers seen


@dataclass
class LIRScoreSet:
    """7-component score for a concept at a point in time."""

    convergence: float = 0.0
    velocity: float = 0.0
    novelty: float = 0.5       # Default prior
    authority: float = 0.5     # Default prior
    pattern_match: float = 0.0
    persistence: float = 0.0   # EScore-inspired temporal persistence
    cross_platform: float = 0.0  # Multi-source confirmation

    @property
    def composite(self) -> float:
        """Weighted composite score."""
        from core.lir.config import SCORE_WEIGHTS

        return (
            self.convergence * SCORE_WEIGHTS["convergence"]
            + self.velocity * SCORE_WEIGHTS["velocity"]
            + self.novelty * SCORE_WEIGHTS["novelty"]
            + self.authority * SCORE_WEIGHTS["authority"]
            + self.pattern_match * SCORE_WEIGHTS["pattern_match"]
            + self.persistence * SCORE_WEIGHTS["persistence"]
            + self.cross_platform * SCORE_WEIGHTS["cross_platform"]
        )


@dataclass
class CandidateTrend:
    """A concept scored and ready for the candidate feed."""

    concept_id: str
    canonical_name: str
    description: str
    ring: str                  # "adopt", "trial", "assess", "hold", "noise"
    scores: LIRScoreSet = field(default_factory=LIRScoreSet)
    composite_score: float = 0.0
    signal_count: int = 0
    source_tiers: List[str] = field(default_factory=list)
    domain_tags: List[str] = field(default_factory=list)
    top_evidence: List[Dict] = field(default_factory=list)  # [{url, title, source, date}]
    first_seen: str = ""
    last_seen: str = ""
    velocity_trend: List[float] = field(default_factory=list)  # Weekly signal counts


@dataclass
class LIRPipelineResult:
    """Result of a complete LIR pipeline run."""

    candidates: List[CandidateTrend]
    total_items_ingested: int
    total_items_after_dedup: int
    total_signals_extracted: int
    total_concepts: int
    new_concepts: int
    execution_time_seconds: float
    sources_polled: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
