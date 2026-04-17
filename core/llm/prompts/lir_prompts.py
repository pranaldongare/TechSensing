"""
LIR prompt templates — signal extraction, concept canonicalization,
and rationale generation.
"""


def lir_extraction_prompt(items_text: str, domain: str = "Technology") -> list[dict]:
    """Build chat prompt for extracting weak signals from raw items.

    Args:
        items_text: Formatted text block of raw items (title, abstract, source).
        domain: Domain context for relevance scoring.

    Returns:
        Chat messages list for invoke_llm.
    """
    return [
        {
            "role": "system",
            "content": (
                "You are a technology intelligence analyst specializing in detecting "
                "early-stage, forward-looking technology signals. Your job is to identify "
                "specific, named technology concepts that represent emerging trends — "
                "things that will matter in 6-24 months but aren't yet mainstream.\n\n"
                "RULES:\n"
                "- Extract SPECIFIC technology concepts, not broad categories.\n"
                "  GOOD: 'Mixture of Experts', 'Ring Attention', 'Constitutional AI'\n"
                "  BAD: 'machine learning', 'AI safety', 'cloud computing'\n"
                "- Each concept should be 2-5 words, a proper noun or technical term.\n"
                "- stated_novelty: 0.0 = incremental/well-known, 1.0 = breakthrough/novel.\n"
                "  Rate based on the text's own framing, not your prior knowledge.\n"
                "- relevance_score: How relevant is this to forward-looking technology trends?\n"
                "  0.0 = tangential, 1.0 = core emerging technology.\n"
                "- Skip items that are purely about business/funding/hiring without "
                "  a specific technology concept.\n"
                "- Multiple signals can come from one item if it covers multiple concepts.\n"
                "- evidence_quote: Include a key phrase that supports the signal.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Domain context: {domain}\n\n"
                f"Extract forward-looking technology signals from these items:\n\n"
                f"{items_text}\n\n"
                "For each item, identify specific named technology concepts that "
                "represent emerging trends. Return all extracted signals."
            ),
        },
    ]


def lir_canonicalization_prompt(
    raw_labels: list[str],
    existing_concepts: dict,
) -> list[dict]:
    """Build chat prompt for canonicalizing concept labels against the registry.

    Args:
        raw_labels: List of raw concept labels to canonicalize.
        existing_concepts: Dict of concept_id -> {canonical_name, aliases, description}.

    Returns:
        Chat messages list for invoke_llm.
    """
    # Format existing registry for the prompt
    if existing_concepts:
        registry_lines = []
        for cid, info in existing_concepts.items():
            name = info.get("canonical_name", cid)
            aliases = info.get("aliases", [])
            desc = info.get("description", "")
            alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
            desc_str = f" — {desc}" if desc else ""
            registry_lines.append(f"  - id='{cid}': {name}{alias_str}{desc_str}")
        registry_block = "EXISTING CONCEPT REGISTRY:\n" + "\n".join(registry_lines)
    else:
        registry_block = "EXISTING CONCEPT REGISTRY: (empty — all concepts are new)"

    labels_block = "\n".join(f"  - \"{label}\"" for label in raw_labels)

    return [
        {
            "role": "system",
            "content": (
                "You are a taxonomy specialist for technology concepts. Your job is to "
                "maintain a clean, deduplicated concept registry by deciding whether new "
                "concept labels match existing entries or represent genuinely new concepts.\n\n"
                "RULES:\n"
                "- 'match': The label refers to the SAME concept as an existing entry.\n"
                "  Example: 'MoE' matches 'Mixture of Experts'.\n"
                "- 'alias': The label is a valid alternative name. Add it as an alias.\n"
                "  Example: 'Sparse MoE' is an alias for 'Mixture of Experts'.\n"
                "- 'new': The label represents a genuinely distinct concept not in the registry.\n"
                "  Provide a canonical_name (clean, title-cased, 2-5 words) and a 1-sentence description.\n"
                "- When in doubt, prefer 'new' over incorrect matching.\n"
                "- domain_tags: 1-3 high-level tags like 'NLP', 'Computer Vision', 'MLOps', "
                "'Reinforcement Learning', 'Systems', 'Security'.\n"
            ),
        },
        {
            "role": "user",
            "content": (
                f"{registry_block}\n\n"
                f"NEW LABELS TO CANONICALIZE:\n{labels_block}\n\n"
                "For each label, decide: match, alias, or new. "
                "If match/alias, provide the matched_concept_id. "
                "If new, provide canonical_name, description, and domain_tags."
            ),
        },
    ]


def lir_rationale_prompt(
    concept_name: str,
    description: str,
    scores: dict,
    signal_count: int,
    source_tiers: list[str],
    top_evidence: list[dict],
    ring: str,
    pattern_matches: list[dict] | None = None,
) -> list[dict]:
    """Build chat prompt for generating a human-readable rationale.

    Args:
        concept_name: Canonical concept name.
        description: Concept description.
        scores: Dict of {convergence, velocity, novelty, authority, pattern_match}.
        signal_count: Number of linked signals.
        source_tiers: List of unique tiers (T1, T2, etc.).
        top_evidence: Top evidence items [{url, title, source, date}].
        ring: Current ring assignment.
        pattern_matches: Optional matched fingerprint patterns.

    Returns:
        Chat messages list for invoke_llm.
    """
    evidence_lines = []
    for ev in top_evidence[:5]:
        evidence_lines.append(
            f"  - [{ev.get('source', '?')}] {ev.get('title', 'untitled')} "
            f"({ev.get('date', 'unknown date')})"
        )
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "  (no evidence)"

    pattern_block = ""
    if pattern_matches:
        pm_lines = [f"  - {p['name']} (score: {p['score']:.2f})" for p in pattern_matches[:3]]
        pattern_block = f"\nMATCHED PATTERNS:\n" + "\n".join(pm_lines)

    return [
        {
            "role": "system",
            "content": (
                "You are a technology strategist writing concise, actionable rationales "
                "for an early-warning technology radar. Your audience is engineering "
                "leadership who need to decide what to investigate.\n\n"
                "Be specific, evidence-based, and avoid hype. Mention concrete signals."
            ),
        },
        {
            "role": "user",
            "content": (
                f"CONCEPT: {concept_name}\n"
                f"DESCRIPTION: {description}\n"
                f"RING: {ring}\n"
                f"SIGNAL COUNT: {signal_count}\n"
                f"SOURCE TIERS: {', '.join(source_tiers)}\n"
                f"SCORES:\n"
                f"  Convergence: {scores.get('convergence', 0):.2f}\n"
                f"  Velocity:    {scores.get('velocity', 0):.2f}\n"
                f"  Novelty:     {scores.get('novelty', 0):.2f}\n"
                f"  Authority:   {scores.get('authority', 0):.2f}\n"
                f"  Pattern:     {scores.get('pattern_match', 0):.2f}\n"
                f"\nTOP EVIDENCE:\n{evidence_block}"
                f"{pattern_block}\n\n"
                "Write a rationale explaining why this concept deserves attention, "
                "what's driving its score, any risks, and a recommended action."
            ),
        },
    ]
