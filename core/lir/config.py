"""
LIR configuration — default categories, scoring weights, thresholds, ring mappings.
"""

# arXiv categories to poll (Phase 1)
ARXIV_CATEGORIES = [
    "cs.CL",   # Computation and Language (NLP)
    "cs.LG",   # Machine Learning
    "cs.AI",   # Artificial Intelligence
    "cs.CV",   # Computer Vision
    "cs.CR",   # Cryptography and Security
    "cs.SE",   # Software Engineering
    "cs.DC",   # Distributed Computing
]

# Default lookback for ingestion (days)
LIR_LOOKBACK_DAYS = 90

# Maximum items per adapter per poll
LIR_MAX_PER_SOURCE = 100

# Minimum composite score to surface as a candidate
LIR_MIN_COMPOSITE_SCORE = 0.25

# Maximum number of candidates to return from the API
LIR_MAX_CANDIDATES = 50

# ──────────────────────── Scoring weights ────────────────────────

SCORE_WEIGHTS = {
    "convergence": 0.30,
    "velocity": 0.25,
    "novelty": 0.20,
    "authority": 0.15,
    "pattern_match": 0.10,
}

# ──────────────────────── Ring thresholds ────────────────────────
# Composite score → radar ring mapping (from spec section 6)

RING_THRESHOLDS = {
    "adopt": 0.85,     # Strong signal, multiple tiers, high velocity
    "trial": 0.70,     # Solid evidence, worth experimenting
    "assess": 0.50,    # Emerging signal, monitor closely
    "hold": 0.25,      # Weak signal, keep on radar
}

def score_to_ring(composite: float) -> str:
    """Map a composite score to a radar ring name."""
    if composite >= RING_THRESHOLDS["adopt"]:
        return "adopt"
    elif composite >= RING_THRESHOLDS["trial"]:
        return "trial"
    elif composite >= RING_THRESHOLDS["assess"]:
        return "assess"
    elif composite >= RING_THRESHOLDS["hold"]:
        return "hold"
    return "noise"

# ──────────────────────── Source tier authority priors ────────────────────────

SOURCE_TIER_AUTHORITY = {
    "T1": 0.85,  # Academic papers, patents — 12-36 month lead
    "T2": 0.70,  # Open-source repos, standards — 6-18 month lead
    "T3": 0.50,  # Community chatter, VC, jobs — 1-6 month lead
    "T4": 0.30,  # Mainstream press — lagging indicator
}

# ──────────────────────── Velocity parameters ────────────────────────

VELOCITY_SIGMOID_K = 5.0       # Steepness of sigmoid
VELOCITY_SIGMOID_X0 = 2.0     # Midpoint (MADs above baseline)
VELOCITY_BASELINE_WEEKS = 12   # Weeks to compute baseline

# ──────────────────────── Convergence parameters ────────────────────────

CONVERGENCE_TIER_BONUS = 0.15  # Bonus per additional unique source tier
MAX_CONVERGENCE_BONUS = 0.45   # Cap on tier-diversity bonus

# ──────────────────────── Batch sizes ────────────────────────

EXTRACTION_BATCH_SIZE = 10     # Items per LLM extraction call
CANONICALIZATION_BATCH_SIZE = 5  # Concepts per LLM canonicalization call
