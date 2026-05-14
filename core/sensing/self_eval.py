"""
Self-Evaluation agent — LLM-as-judge quality scoring for completed reports.

Runs AFTER the pipeline produces a final report.  Scores the report on five
criteria (1-5 each) and produces a short reflection that will be injected
into the next run's prompts via experience memory.

Uses the lightweight classify LLM for fast turnaround (~5-10 s).
Fully non-fatal — any error returns neutral default scores.
"""

import json
import logging
import time
from typing import List

from core.constants import GPU_SENSING_CLASSIFY_LLM
from core.llm.client import invoke_llm
from core.llm.output_schemas.sensing_outputs import (
    SelfEvalOutput,
    TechSensingReport,
)

logger = logging.getLogger("sensing.self_eval")


def _default_eval() -> dict:
    """Return a neutral evaluation when the LLM call fails."""
    return {
        "scores": {
            "coverage": 3,
            "specificity": 3,
            "novelty_accuracy": 3,
            "actionability": 3,
            "coherence": 3,
            "overall": 3.0,
        },
        "strengths": [],
        "weaknesses": [],
        "missed_topics": [],
        "reflection": "",
    }


def _build_report_summary(report: TechSensingReport) -> str:
    """Build a compact text summary of the report for evaluation."""
    parts = []

    parts.append(f"Title: {report.report_title}")
    parts.append(f"Domain: {report.domain}")
    parts.append(f"Confidence: {report.report_confidence}")
    parts.append(f"Articles analyzed: {report.total_articles_analyzed}")

    # Radar items
    radar_names = [f"{item.name} ({item.ring}, new={item.is_new})" for item in report.radar_items]
    parts.append(f"\nRadar items ({len(radar_names)}):")
    for name in radar_names:
        parts.append(f"  - {name}")

    # Events
    event_headlines = [e.headline for e in report.top_events]
    parts.append(f"\nTop events ({len(event_headlines)}):")
    for h in event_headlines[:10]:
        parts.append(f"  - {h}")

    # Trends
    trend_names = [t.trend_name for t in report.key_trends]
    parts.append(f"\nKey trends ({len(trend_names)}):")
    for t in trend_names:
        parts.append(f"  - {t}")

    # Recommendations
    rec_titles = [r.title for r in report.recommendations]
    parts.append(f"\nRecommendations ({len(rec_titles)}):")
    for r in rec_titles:
        parts.append(f"  - {r}")

    # Blind spots
    if report.blind_spots:
        parts.append(f"\nBlind spots ({len(report.blind_spots)}):")
        for bs in report.blind_spots:
            parts.append(f"  - {bs.area}: {bs.why_it_matters}")

    # Bottom line
    if report.bottom_line:
        parts.append(f"\nBottom line: {report.bottom_line}")

    return "\n".join(parts)


async def evaluate_report(
    report: TechSensingReport,
    classified_articles: list,
    domain: str,
) -> dict:
    """
    Evaluate a completed report using LLM-as-judge scoring.

    Returns a dict with keys: scores, strengths, weaknesses, missed_topics, reflection.
    On any failure, returns neutral default scores (never raises).
    """
    eval_start = time.time()

    report_summary = _build_report_summary(report)
    article_count = len(classified_articles)
    covered_count = len(report.radar_items) + len(report.top_events) + len(report.key_trends)

    prompt = [
        {
            "role": "system",
            "parts": (
                "You are a quality evaluator for tech sensing reports. Your task is to "
                "score a completed report on 5 criteria and provide constructive feedback.\n\n"
                "SCORING CRITERIA (1-5 each):\n"
                "1. COVERAGE (1-5): Did the report cover all major developments? "
                "Are there obvious gaps? Consider the ratio of items in the report "
                "vs. total articles analyzed.\n"
                "2. SPECIFICITY (1-5): Are radar items specific technologies, tools, "
                "or frameworks? Or are they generic categories like 'AI Agents' or "
                "'Machine Learning'?\n"
                "3. NOVELTY ACCURACY (1-5): Are items marked as 'new' genuinely "
                "recent developments? Or are established/well-known technologies "
                "incorrectly flagged as new?\n"
                "4. ACTIONABILITY (1-5): Are recommendations concrete, specific, "
                "and actionable? Or are they vague platitudes?\n"
                "5. COHERENCE (1-5): Is the report well-structured? Are there "
                "duplicates or contradictions? Do events, trends, and radar items "
                "tell a consistent story?\n\n"
                "SCORING GUIDE:\n"
                "- 5 = Excellent, no issues\n"
                "- 4 = Good, minor issues\n"
                "- 3 = Acceptable, some issues\n"
                "- 2 = Below average, significant issues\n"
                "- 1 = Poor, major problems\n\n"
                "OUTPUT RULES:\n"
                "- overall_score = weighted average: "
                "0.25*coverage + 0.25*specificity + 0.2*novelty_accuracy + "
                "0.15*actionability + 0.15*coherence\n"
                "- strengths: exactly 2-3 specific observations\n"
                "- weaknesses: exactly 2-3 specific, actionable observations\n"
                "- missed_topics: 0-5 topics that should have been covered\n"
                "- reflection: Write as instructions to your future self. "
                "E.g., 'Next time, pay more attention to X. Avoid Y.'\n"
                "- Return ONLY valid JSON.\n"
                "- Do NOT include schema definitions, $defs, $ref, properties, "
                "or type metadata.\n"
            ),
        },
        {
            "role": "user",
            "parts": (
                f"DOMAIN: {domain}\n"
                f"TOTAL CLASSIFIED ARTICLES: {article_count}\n"
                f"ITEMS IN REPORT: {covered_count}\n\n"
                f"REPORT SUMMARY:\n{report_summary}\n\n"
                "Evaluate this report. Be honest and constructive."
            ),
        },
    ]

    try:
        logger.info(
            f"[SelfEval] Evaluating report quality for '{domain}'..."
        )

        result = await invoke_llm(
            gpu_model=GPU_SENSING_CLASSIFY_LLM.model,
            response_schema=SelfEvalOutput,
            contents=prompt,
            port=GPU_SENSING_CLASSIFY_LLM.port,
        )

        evaluation = SelfEvalOutput.model_validate(result)

        elapsed = time.time() - eval_start
        logger.info(
            f"[SelfEval] Complete in {elapsed:.1f}s — "
            f"coverage={evaluation.coverage_score}, "
            f"specificity={evaluation.specificity_score}, "
            f"novelty={evaluation.novelty_accuracy_score}, "
            f"actionability={evaluation.actionability_score}, "
            f"coherence={evaluation.coherence_score}, "
            f"overall={evaluation.overall_score:.1f}"
        )

        for w in evaluation.weaknesses:
            logger.info(f"[SelfEval] Weakness: {w}")
        if evaluation.missed_topics:
            logger.info(f"[SelfEval] Missed topics: {', '.join(evaluation.missed_topics)}")
        if evaluation.reflection:
            logger.info(f"[SelfEval] Reflection: {evaluation.reflection}")

        return {
            "scores": {
                "coverage": evaluation.coverage_score,
                "specificity": evaluation.specificity_score,
                "novelty_accuracy": evaluation.novelty_accuracy_score,
                "actionability": evaluation.actionability_score,
                "coherence": evaluation.coherence_score,
                "overall": evaluation.overall_score,
            },
            "strengths": evaluation.strengths,
            "weaknesses": evaluation.weaknesses,
            "missed_topics": evaluation.missed_topics,
            "reflection": evaluation.reflection,
        }

    except Exception as e:
        logger.warning(f"[SelfEval] Failed (using defaults): {e}")
        return _default_eval()
