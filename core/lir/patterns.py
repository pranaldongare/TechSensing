"""
LIR pattern matching — fingerprint YAML loading + DTW/cosine similarity.

Phase 3: Compares concept signal timeseries against known technology
emergence fingerprints (e.g., foundation-model-emergence, protocol-
standardization) to boost scoring.
"""

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger("lir.patterns")

PATTERNS_DIR = "data/lir/patterns"


@dataclass
class Fingerprint:
    """A technology emergence fingerprint loaded from YAML."""

    pattern_id: str
    name: str
    description: str
    # Normalized weekly signal counts (length = duration_weeks)
    timeseries: List[float]
    duration_weeks: int
    # Ring threshold that the concept should reach, and by which week
    expected_ring: str = "assess"
    consensus_week: int = 0  # Week at which mainstream adoption happens
    tags: List[str] = field(default_factory=list)


def load_fingerprints() -> Dict[str, Fingerprint]:
    """Load all fingerprint YAML files from the patterns directory."""
    if not os.path.exists(PATTERNS_DIR):
        logger.debug(f"Patterns directory not found: {PATTERNS_DIR}")
        return {}

    fingerprints: Dict[str, Fingerprint] = {}

    for fname in os.listdir(PATTERNS_DIR):
        if not fname.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(PATTERNS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or not isinstance(data, dict):
                continue

            fp = Fingerprint(
                pattern_id=data.get("pattern_id", fname.replace(".yaml", "")),
                name=data.get("name", ""),
                description=data.get("description", ""),
                timeseries=data.get("timeseries", []),
                duration_weeks=data.get("duration_weeks", len(data.get("timeseries", []))),
                expected_ring=data.get("expected_ring", "assess"),
                consensus_week=data.get("consensus_week", 0),
                tags=data.get("tags", []),
            )
            if fp.timeseries:
                fingerprints[fp.pattern_id] = fp
                logger.debug(f"Loaded fingerprint: {fp.pattern_id} ({len(fp.timeseries)} weeks)")

        except Exception as e:
            logger.warning(f"Failed to load fingerprint {fname}: {e}")

    logger.info(f"Loaded {len(fingerprints)} fingerprints from {PATTERNS_DIR}")
    return fingerprints


# ──────────────────────── DTW similarity ────────────────────────


def _dtw_distance(seq_a: List[float], seq_b: List[float]) -> float:
    """Compute Dynamic Time Warping distance between two sequences.

    Uses a full cost matrix (O(n*m)). Both sequences should be
    normalized to [0,1] range for meaningful comparison.
    """
    n, m = len(seq_a), len(seq_b)
    if n == 0 or m == 0:
        return float("inf")

    # Cost matrix with +inf borders
    dtw = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    dtw[0][0] = 0.0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = abs(seq_a[i - 1] - seq_b[j - 1])
            dtw[i][j] = cost + min(
                dtw[i - 1][j],      # insertion
                dtw[i][j - 1],      # deletion
                dtw[i - 1][j - 1],  # match
            )

    return dtw[n][m]


def _normalize_series(series: List[float]) -> List[float]:
    """Normalize a timeseries to [0, 1] range."""
    if not series:
        return []
    max_val = max(series)
    if max_val == 0:
        return [0.0] * len(series)
    return [v / max_val for v in series]


def dtw_similarity(
    concept_series: List[float],
    fingerprint_series: List[float],
) -> float:
    """Compute DTW-based similarity score between two timeseries.

    Returns a float in [0, 1] where 1.0 = perfect match.
    """
    if not concept_series or not fingerprint_series:
        return 0.0

    # Normalize both series
    norm_a = _normalize_series(concept_series)
    norm_b = _normalize_series(fingerprint_series)

    distance = _dtw_distance(norm_a, norm_b)

    # Convert distance to similarity: sim = 1 / (1 + distance/len)
    avg_len = (len(norm_a) + len(norm_b)) / 2.0
    normalized_dist = distance / max(avg_len, 1.0)

    similarity = 1.0 / (1.0 + normalized_dist)
    return min(1.0, similarity)


# ──────────────────────── Cosine similarity (fast alternative) ────────────────


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors of equal length.

    If lengths differ, truncate to the shorter.
    """
    min_len = min(len(a), len(b))
    if min_len == 0:
        return 0.0

    a = a[:min_len]
    b = b[:min_len]

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return max(0.0, dot / (mag_a * mag_b))


# ──────────────────────── Pattern match scoring ────────────────────────


def compute_pattern_match(
    concept_weekly_counts: List[float],
    fingerprints: Optional[Dict[str, Fingerprint]] = None,
) -> float:
    """Compute the pattern_match score for a concept.

    Tries both DTW and cosine similarity against all fingerprints,
    returns the best match score.

    Args:
        concept_weekly_counts: Weekly signal counts for the concept
            (oldest first, same as velocity_trend).
        fingerprints: Pre-loaded fingerprints. If None, loads from disk.

    Returns:
        Float in [0, 1] — best pattern match score.
    """
    if not concept_weekly_counts or sum(concept_weekly_counts) == 0:
        return 0.0

    if fingerprints is None:
        fingerprints = load_fingerprints()

    if not fingerprints:
        return 0.0

    best_score = 0.0

    for fp_id, fp in fingerprints.items():
        # Use a sliding window if concept series is shorter than fingerprint
        fp_series = fp.timeseries
        concept_len = len(concept_weekly_counts)

        # If concept is much shorter, compare against the tail of the fingerprint
        if concept_len < len(fp_series):
            # Try matching against the most recent portion of the fingerprint
            fp_tail = fp_series[-concept_len:]
            dtw_score = dtw_similarity(concept_weekly_counts, fp_tail)
            cos_score = _cosine_similarity(
                _normalize_series(concept_weekly_counts),
                _normalize_series(fp_tail),
            )
        else:
            dtw_score = dtw_similarity(concept_weekly_counts, fp_series)
            cos_score = _cosine_similarity(
                _normalize_series(concept_weekly_counts),
                _normalize_series(fp_series),
            )

        # Blend: 60% DTW + 40% cosine
        blended = 0.6 * dtw_score + 0.4 * cos_score
        if blended > best_score:
            best_score = blended

    return min(1.0, best_score)


def find_matching_patterns(
    concept_weekly_counts: List[float],
    fingerprints: Optional[Dict[str, Fingerprint]] = None,
    min_score: float = 0.3,
) -> List[Dict]:
    """Find all fingerprints that match a concept's timeseries.

    Returns a list of {pattern_id, name, score, description} dicts
    sorted by score descending, filtered by min_score.
    """
    if not concept_weekly_counts or sum(concept_weekly_counts) == 0:
        return []

    if fingerprints is None:
        fingerprints = load_fingerprints()

    matches = []

    for fp_id, fp in fingerprints.items():
        concept_len = len(concept_weekly_counts)
        fp_series = fp.timeseries

        if concept_len < len(fp_series):
            fp_tail = fp_series[-concept_len:]
        else:
            fp_tail = fp_series

        dtw_score = dtw_similarity(concept_weekly_counts, fp_tail)
        cos_score = _cosine_similarity(
            _normalize_series(concept_weekly_counts),
            _normalize_series(fp_tail),
        )
        blended = 0.6 * dtw_score + 0.4 * cos_score

        if blended >= min_score:
            matches.append({
                "pattern_id": fp_id,
                "name": fp.name,
                "description": fp.description,
                "score": round(blended, 4),
                "expected_ring": fp.expected_ring,
                "consensus_week": fp.consensus_week,
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches
