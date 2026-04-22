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
    "convergence": 0.20,
    "velocity": 0.20,
    "novelty": 0.15,
    "authority": 0.15,
    "pattern_match": 0.10,
    "persistence": 0.10,
    "cross_platform": 0.10,
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

# ──────────────────────── Persistence parameters (EScore-inspired) ────────────────────────

PERSISTENCE_MIN_SIGNALS = 7       # Minimum signal count to start scoring
PERSISTENCE_MIN_MONTHS = 3        # Minimum distinct months with signals
PERSISTENCE_FULL_SIGNALS = 20     # Signals for full persistence score
PERSISTENCE_FULL_MONTHS = 6       # Months for full persistence score

# ──────────────────────── Cross-platform parameters ────────────────────────

CROSS_PLATFORM_MIN_SOURCES = 2    # Minimum unique source_ids for >0
CROSS_PLATFORM_FULL_SOURCES = 5   # Source_ids for full score
CROSS_PLATFORM_TIER_BONUS = 0.15  # Bonus per tier beyond the first

# ──────────────────────── Velocity decay detection ────────────────────────

VELOCITY_DECAY_THRESHOLD = 0.50   # >50% drop from peak = hype flag
VELOCITY_DECAY_WINDOW_WEEKS = 4   # Recent window to check for decay
VELOCITY_DECAY_PENALTY = 0.3      # Multiplier applied to velocity if decaying

# ──────────────────────── EScore novelty blend ────────────────────────

ESCORE_NOVELTY_WEIGHT = 0.40      # Weight for objective novelty ratio
LLM_NOVELTY_WEIGHT = 0.60         # Weight for LLM stated_novelty

# ──────────────────────── Global velocity baseline ────────────────────────
# Fallback signals-per-week by tier when concept has no historical baseline

GLOBAL_VELOCITY_BASELINE = {
    "T1": 0.5,   # Academic sources are slower
    "T2": 2.0,   # Open-source/ecosystem moderate
    "T3": 5.0,   # Community chatter is frequent
    "T4": 3.0,   # Mainstream press moderate
}
