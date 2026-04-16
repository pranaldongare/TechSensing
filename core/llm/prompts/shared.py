"""
Shared prompt helpers plugged into multiple report-writing prompts.

``tense_rules_block`` standardizes how the LLM phrases events whose
release dates are still in the future (announced but not yet shipped).
Without this block the LLM tends to describe a model that was merely
ANNOUNCED this week as if it had already been RELEASED.
"""

from datetime import datetime, timezone


def tense_rules_block(today_override: str = "") -> str:
    """Return a CRITICAL tense/status block to include in report prompts.

    The block instructs the LLM to:
    - Keep announced-but-upcoming information in the output, but
    - Use future/progressive wording ("plans to release", "is expected to
      ship", "announced it will launch") rather than past-tense wording
      ("released", "shipped", "launched") when the event is still in the
      future relative to ``today_override`` (defaults to today UTC).

    Applies uniformly to product launches, model releases, funding
    rounds, acquisitions, partnerships, hires, and regulatory actions.
    """
    today = today_override or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        "TENSE & STATUS RULES (CRITICAL):\n"
        f"- TODAY IS {today}. For every event you describe, first decide "
        f"whether it has already occurred on or before {today}, or is "
        f"scheduled/expected for a date AFTER {today}.\n"
        "- For events that have already happened (release, launch, closing, "
        "GA date on or before today): past or present-perfect tense is "
        "correct — \"released\", \"launched\", \"announced\", \"shipped\", "
        "\"raised $X\", \"acquired\".\n"
        "- For events SCHEDULED FOR THE FUTURE, or where only an "
        "ANNOUNCEMENT exists without a completed launch, use "
        "future/progressive wording instead:\n"
        "    * \"plans to release\" / \"is planning to launch\"\n"
        "    * \"announced it will release\" / \"is expected to ship\"\n"
        "    * \"is scheduled to launch on <date>\" / \"will debut in <month>\"\n"
        "- Do NOT write \"released\", \"shipped\", \"launched\", or "
        "\"available\" for a product/model/feature that has only been "
        "ANNOUNCED but is not yet publicly available.\n"
        "- If an article explicitly says the product is AVAILABLE, "
        "GENERALLY AVAILABLE (GA), ON SALE, or SHIPPED as of a date on or "
        "before today, past tense is correct.\n"
        "- If the timing is genuinely ambiguous, use the neutral verb "
        "\"announced\" (e.g., \"Anthropic announced Claude 4.7\").\n"
        "- DO NOT drop information just because the event is upcoming — "
        "include it and simply phrase the tense correctly.\n"
        "- Apply these rules uniformly to product launches, model "
        "releases, funding rounds, acquisitions, partnerships, "
        "personnel moves, and regulatory actions.\n\n"
    )
