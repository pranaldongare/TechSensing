"""
Technology Relationship Extraction — evidence-based relationship mapping
between radar technologies using article co-occurrence analysis.

Approach:
1. Pre-compute co-occurrence: scan articles for mentions of radar item names
2. Send co-occurrence pairs (with article evidence) to LLM for classification
3. Ground relationship strength in data (co-occurrence count + relevance + confidence)
4. Filter out weak/coincidental edges
"""

import json
import logging
import re
from collections import defaultdict
from typing import List

from core.constants import GPU_SENSING_REPORT_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import (
    ClassifiedArticle,
    TechRelationshipMap,
    TechSensingReport,
)
from core.llm.prompts.sensing_prompts import sensing_relationship_prompt

logger = logging.getLogger("sensing.relationships")

# Maximum co-occurrence pairs to send to LLM (keeps prompt manageable)
MAX_PAIRS = 50

# Minimum strength to keep a relationship in the final output
MIN_STRENGTH = 0.25

# Confidence label -> numeric score for strength computation
CONFIDENCE_SCORES = {"high": 1.0, "medium": 0.6, "low": 0.3}


def _build_name_pattern(name: str) -> re.Pattern | None:
    """
    Build a word-boundary regex pattern for a radar item name.

    For short names (<=3 chars like "Go", "R", "C++"), requires exact
    word boundaries to avoid false positives. Returns None for single-char
    names that can't be reliably matched.
    """
    escaped = re.escape(name)
    if len(name) <= 1:
        return None  # Single chars produce too many false positives
    # Word-boundary match for all names
    return re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)


def _build_cooccurrence(
    radar_items: list,
    classified_articles: List[ClassifiedArticle],
) -> list[dict]:
    """
    Scan each article's title+summary for mentions of radar item names.
    Build co-occurrence pairs: (tech_a, tech_b) that share articles.

    Returns list of dicts sorted by co-occurrence count (descending):
    [
        {
            "tech_a": "LangChain",
            "tech_b": "GPT-4",
            "count": 4,
            "avg_relevance": 0.82,
            "articles": [{"title": "...", "relevance": 0.85}, ...]
        },
        ...
    ]
    """
    # Build name -> canonical radar item name mapping
    item_names = {item.name.lower().strip(): item.name for item in radar_items}
    # Build regex patterns for each radar item
    name_patterns: dict[str, re.Pattern] = {}
    for lower_name, canonical in item_names.items():
        pattern = _build_name_pattern(canonical)
        if pattern:
            name_patterns[canonical] = pattern

    # For each article, find which technologies it mentions
    article_techs: list[tuple[ClassifiedArticle, set[str]]] = []

    for article in classified_articles:
        text = f"{article.title} {article.summary}".lower()
        mentioned: set[str] = set()

        # The article's own technology_name is a guaranteed match
        tech_name_lower = article.technology_name.lower().strip()
        if tech_name_lower in item_names:
            mentioned.add(item_names[tech_name_lower])

        # Scan for other radar item names in the text
        for canonical, pattern in name_patterns.items():
            if pattern.search(text):
                mentioned.add(canonical)

        if len(mentioned) >= 2:
            article_techs.append((article, mentioned))

    # Build pair -> articles mapping
    pair_articles: dict[tuple[str, str], list[ClassifiedArticle]] = defaultdict(list)
    for article, techs in article_techs:
        techs_list = sorted(techs)  # Sort for consistent pair keys
        for i in range(len(techs_list)):
            for j in range(i + 1, len(techs_list)):
                pair = (techs_list[i], techs_list[j])
                pair_articles[pair].append(article)

    # Convert to sorted list
    pairs = []
    for (tech_a, tech_b), articles in pair_articles.items():
        avg_rel = sum(a.relevance_score for a in articles) / len(articles)
        pairs.append({
            "tech_a": tech_a,
            "tech_b": tech_b,
            "count": len(articles),
            "avg_relevance": round(avg_rel, 2),
            "articles": [
                {"title": a.title, "relevance": round(a.relevance_score, 2)}
                for a in articles[:5]  # Cap displayed articles per pair
            ],
        })

    # Sort by count descending, then by avg_relevance descending
    pairs.sort(key=lambda p: (p["count"], p["avg_relevance"]), reverse=True)
    return pairs


def _format_cooccurrence_text(pairs: list[dict]) -> str:
    """Format co-occurrence pairs into readable text for the LLM prompt."""
    if not pairs:
        return "No co-occurrences found between radar technologies in the article corpus."

    lines = []
    for i, pair in enumerate(pairs, 1):
        lines.append(
            f"PAIR {i}: \"{pair['tech_a']}\" <-> \"{pair['tech_b']}\" "
            f"(co-occur in {pair['count']} article{'s' if pair['count'] != 1 else ''})"
        )
        for art in pair["articles"]:
            lines.append(f"  - \"{art['title']}\" (relevance: {art['relevance']})")
        lines.append("")

    return "\n".join(lines)


def _compute_strength(
    rel,
    cooccurrence_lookup: dict[tuple[str, str], dict],
    max_count: int,
) -> float:
    """
    Compute data-grounded relationship strength.

    Formula: 0.4 * normalized_cooccurrence + 0.3 * avg_relevance + 0.3 * confidence_score
    """
    pair_key = tuple(sorted([rel.source_tech.lower().strip(), rel.target_tech.lower().strip()]))
    pair_data = cooccurrence_lookup.get(pair_key, {})

    count = pair_data.get("count", 1)
    avg_rel = pair_data.get("avg_relevance", 0.5)
    conf_score = CONFIDENCE_SCORES.get(rel.confidence, 0.3)

    # Normalize count: cap at max_count to keep scale 0-1
    norm_count = min(count / max(max_count, 1), 1.0)

    strength = 0.4 * norm_count + 0.3 * avg_rel + 0.3 * conf_score
    return round(min(strength, 1.0), 2)


async def extract_relationships(
    report: TechSensingReport,
    classified_articles: List[ClassifiedArticle],
    domain: str = "Generative AI",
) -> TechRelationshipMap:
    """
    Extract technology relationships using evidence-based co-occurrence analysis.

    1. Pre-compute which radar items co-occur in the same articles
    2. Send co-occurrence pairs to LLM for classification
    3. Ground strength in data, filter weak edges
    """
    radar_items = list(report.radar_items)
    if not radar_items:
        return TechRelationshipMap(relationships=[], clusters=[])

    # Step 1: Build co-occurrence matrix
    pairs = _build_cooccurrence(radar_items, classified_articles)
    logger.info(
        f"[Relationships] Found {len(pairs)} co-occurrence pairs "
        f"across {len(radar_items)} radar items"
    )

    if not pairs:
        logger.info("[Relationships] No co-occurrences found — skipping LLM call")
        return TechRelationshipMap(relationships=[], clusters=[])

    # Cap pairs to keep prompt manageable
    pairs_for_llm = pairs[:MAX_PAIRS]

    # Step 2: Format evidence and call LLM
    cooccurrence_text = _format_cooccurrence_text(pairs_for_llm)
    radar_json = json.dumps(
        [
            {"name": item.name, "quadrant": item.quadrant, "ring": item.ring}
            for item in radar_items
        ],
        indent=2,
        ensure_ascii=False,
    )

    prompt = sensing_relationship_prompt(
        cooccurrence_text=cooccurrence_text,
        radar_items_json=radar_json,
        domain=domain,
    )

    result = await invoke_llm(
        gpu_model=GPU_SENSING_REPORT_LLM.model,
        response_schema=TechRelationshipMap,
        contents=prompt,
        port=GPU_SENSING_REPORT_LLM.port,
    )

    validated = TechRelationshipMap.model_validate(result)

    # Step 3: Post-process — ground strength, filter
    radar_names_lower = {item.name.lower().strip() for item in radar_items}

    # Build lookup for co-occurrence data
    cooccurrence_lookup: dict[tuple[str, str], dict] = {}
    max_count = 1
    for pair in pairs:
        key = tuple(sorted([pair["tech_a"].lower().strip(), pair["tech_b"].lower().strip()]))
        cooccurrence_lookup[key] = pair
        max_count = max(max_count, pair["count"])

    # Filter invalid relationships and compute strength
    valid_rels = []
    seen_pairs = set()

    for rel in validated.relationships:
        src = rel.source_tech.lower().strip()
        tgt = rel.target_tech.lower().strip()

        # Skip self-references
        if src == tgt:
            continue
        # Skip if tech names don't match radar items
        if src not in radar_names_lower or tgt not in radar_names_lower:
            continue
        # Deduplicate pairs
        pair_key = tuple(sorted([src, tgt]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        # Attach article count from co-occurrence data
        pair_data = cooccurrence_lookup.get(pair_key, {})
        rel.article_count = pair_data.get("count", 0)

        # Compute data-grounded strength
        rel.strength = _compute_strength(rel, cooccurrence_lookup, max_count)

        # Filter weak edges
        if rel.confidence == "low" and rel.article_count < 2:
            continue
        if rel.strength < MIN_STRENGTH:
            continue

        valid_rels.append(rel)

    # Sort by strength descending
    valid_rels.sort(key=lambda r: r.strength, reverse=True)

    # Deduplicate clusters by name
    seen_cluster_names = set()
    unique_clusters = []
    for cluster in validated.clusters:
        if cluster.cluster_name.lower() not in seen_cluster_names:
            seen_cluster_names.add(cluster.cluster_name.lower())
            unique_clusters.append(cluster)

    logger.info(
        f"[Relationships] Final: {len(valid_rels)} relationships "
        f"(filtered from {len(validated.relationships)}), "
        f"{len(unique_clusters)} clusters"
    )

    return TechRelationshipMap(
        relationships=valid_rels,
        clusters=unique_clusters,
    )
