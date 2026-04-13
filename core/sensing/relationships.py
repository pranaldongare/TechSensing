"""
Technology Relationship Extraction — identifies relationships and clusters
between radar technologies using LLM analysis.
"""

import json
import logging
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


async def extract_relationships(
    report: TechSensingReport,
    classified_articles: List[ClassifiedArticle],
    domain: str = "Generative AI",
) -> TechRelationshipMap:
    """
    Extract technology relationships and clusters from radar items
    and their supporting articles.

    For large radar sets (>10 items), processes in overlapping batches
    of 10 items with 3-item overlap, then deduplicates.
    """
    radar_items = list(report.radar_items)
    if not radar_items:
        return TechRelationshipMap(relationships=[], clusters=[])

    # Prepare articles JSON (top 30 by relevance, trimmed)
    sorted_articles = sorted(
        classified_articles, key=lambda a: a.relevance_score, reverse=True
    )[:30]
    articles_json = json.dumps(
        [a.model_dump() for a in sorted_articles],
        indent=2,
        ensure_ascii=False,
    )

    if len(radar_items) <= 10:
        # Single batch
        return await _extract_batch(radar_items, articles_json, domain)

    # Overlapping batches of 10 with 3-item overlap
    BATCH_SIZE = 10
    OVERLAP = 3
    all_relationships = []
    all_clusters = []
    seen_pairs = set()

    step = BATCH_SIZE - OVERLAP
    for i in range(0, len(radar_items), step):
        batch = radar_items[i : i + BATCH_SIZE]
        if len(batch) < 3:
            break  # Skip tiny trailing batches

        batch_num = i // step + 1
        logger.info(
            f"[Relationships] Batch {batch_num}: "
            f"{', '.join(item.name for item in batch[:3])}... ({len(batch)} items)"
        )

        result = await _extract_batch(batch, articles_json, domain)

        # Deduplicate relationships by source/target pair
        for rel in result.relationships:
            pair = tuple(sorted([rel.source_tech.lower(), rel.target_tech.lower()]))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                all_relationships.append(rel)

        all_clusters.extend(result.clusters)

    # Deduplicate clusters by name
    seen_cluster_names = set()
    unique_clusters = []
    for cluster in all_clusters:
        if cluster.cluster_name.lower() not in seen_cluster_names:
            seen_cluster_names.add(cluster.cluster_name.lower())
            unique_clusters.append(cluster)

    logger.info(
        f"[Relationships] Total: {len(all_relationships)} relationships, "
        f"{len(unique_clusters)} clusters"
    )

    return TechRelationshipMap(
        relationships=all_relationships,
        clusters=unique_clusters,
    )


async def _extract_batch(
    radar_items: list,
    articles_json: str,
    domain: str,
) -> TechRelationshipMap:
    """Extract relationships for a batch of radar items."""
    radar_json = json.dumps(
        [
            {"name": item.name, "quadrant": item.quadrant, "ring": item.ring}
            for item in radar_items
        ],
        indent=2,
        ensure_ascii=False,
    )

    prompt = sensing_relationship_prompt(
        radar_items_json=radar_json,
        classified_articles_json=articles_json,
        domain=domain,
    )

    result = await invoke_llm(
        gpu_model=GPU_SENSING_REPORT_LLM.model,
        response_schema=TechRelationshipMap,
        contents=prompt,
        port=GPU_SENSING_REPORT_LLM.port,
    )

    validated = TechRelationshipMap.model_validate(result)

    # Filter out self-references and invalid tech names
    radar_names_lower = {item.name.lower().strip() for item in radar_items}
    valid_rels = [
        r for r in validated.relationships
        if (
            r.source_tech.lower().strip() != r.target_tech.lower().strip()
            and r.source_tech.lower().strip() in radar_names_lower
            and r.target_tech.lower().strip() in radar_names_lower
        )
    ]

    return TechRelationshipMap(
        relationships=valid_rels,
        clusters=validated.clusters,
    )
