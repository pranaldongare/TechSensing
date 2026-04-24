"""
Centralized LLM output sanitization and JSON repair pipeline.

Handles common LLM JSON output issues:
- Markdown code fences wrapping JSON
- Unicode whitespace characters (non-breaking spaces, thin spaces, etc.)
- Preamble/postamble text around JSON
- Malformed JSON (trailing commas, single quotes, unescaped chars)
"""

import json
import re
from typing import Type, TypeVar

from pydantic import BaseModel


try:
    import json_repair
except ImportError:
    json_repair = None

T = TypeVar("T", bound=BaseModel)

# Unicode whitespace characters that have no semantic meaning in JSON
# and can cause parsing failures
_UNICODE_WHITESPACE_RE = re.compile(
    r"[\u00a0\u2009\u200a\u202f\u00ad\u2002\u2003\u2004\u2005\u2006\u2007\u2008]"
)

# Zero-width characters that should be removed entirely
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060\u180e]")

# Markdown code fence patterns
_CODE_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

# Thinking / reasoning tags (some models emit these even when disabled)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_REASONING_TAG_RE = re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL)

# Unclosed thinking tags: <think> with content but no </think>
# Qwen3 sometimes outputs <think>...reasoning text without closing the tag.
# Strip from <think> up to (but not including) the first { or [ character.
_UNCLOSED_THINK_RE = re.compile(r"<think>(?:(?!</think>).)*?(?=[{\[])", re.DOTALL)


def _repair_merged_array_objects(text: str) -> str:
    """
    Fix JSON where objects in an array are merged into one with duplicate keys.

    LLMs sometimes output:
        [{"theme":"A","count":1,"examples":[...],"theme":"B","count":2,"examples":[...]}]
    instead of:
        [{"theme":"A","count":1,"examples":[...]},{"theme":"B","count":2,"examples":[...]}]

    Detects the first key after [{ and inserts },{ before each duplicate occurrence.
    Only triggers when the same key appears 3+ times (strong signal of merging).
    """
    match = re.search(r'\[\s*\{\s*"(\w+)"\s*:', text)
    if not match:
        return text

    first_key = match.group(1)
    escaped_key = re.escape(first_key)

    # Count occurrences of this key as a JSON key (not inside string values).
    # 3+ means at least 2 objects were merged — safe to repair.
    key_pattern = r'"' + escaped_key + r'"\s*:'
    if len(re.findall(key_pattern, text)) < 3:
        return text

    # The first occurrence is [{"key": (no leading comma).
    # Duplicates appear as ,"key": — insert },{ before each.
    repaired = re.sub(
        r',\s*"' + escaped_key + r'"\s*:',
        '},{"' + first_key + '":',
        text,
    )
    return repaired


def sanitize_llm_json(raw: str) -> str:
    """
    Pre-process raw LLM output to maximize JSON parsing success.

    Pipeline (each step is fast string/regex ops):
    1. Strip markdown code fences
    2. Replace unicode whitespace with regular spaces
    3. Remove zero-width characters
    4. Normalize newlines
    5. Extract JSON object/array from surrounding text

    Args:
        raw: Raw LLM output string

    Returns:
        Cleaned string ready for JSON parsing
    """
    if not raw or not raw.strip():
        return raw

    text = raw

    # 0. Strip thinking / reasoning tags (models may emit these before JSON)
    text = _THINK_TAG_RE.sub("", text)
    text = _REASONING_TAG_RE.sub("", text)

    # 0b. Strip unclosed <think> tags (Qwen3 sometimes opens <think> without closing)
    text = _UNCLOSED_THINK_RE.sub("", text)

    # 1. Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1)

    # 2. Replace unicode whitespace with regular spaces
    text = _UNICODE_WHITESPACE_RE.sub(" ", text)

    # 3. Remove zero-width characters
    text = _ZERO_WIDTH_RE.sub("", text)

    # 4. Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 5. Extract JSON object/array from surrounding text
    text = text.strip()
    text = _extract_json_block(text)

    # 6. Escape control characters within strings (e.g., literal newlines in JSON values)
    text = _escape_control_chars_in_strings(text)

    # 7. Repair merged array objects (LLM puts all items as duplicate keys in one object)
    text = _repair_merged_array_objects(text)

    return text


def _sanitize_fallback_text(raw: str) -> str:
    """Clean plain-text fallback output without forcing JSON extraction."""
    if not raw:
        return raw

    text = raw
    text = _THINK_TAG_RE.sub("", text)
    text = _REASONING_TAG_RE.sub("", text)

    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1)

    text = _UNICODE_WHITESPACE_RE.sub(" ", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _escape_control_chars_in_strings(text: str) -> str:
    """
    Escapes control characters (newlines, tabs) only when they appear
    inside double-quoted strings, to ensure valid JSON.
    """
    result = []
    in_string = False
    i = 0
    n = len(text)

    while i < n:
        char = text[i]

        if char == '"':
            # Toggle string state, handling escaped quotes
            if i > 0 and text[i - 1] == "\\":
                # Check for double backslash (escaped backslash) before quote
                # If odd number of backslashes, the quote is escaped
                bs_count = 0
                j = i - 1
                while j >= 0 and text[j] == "\\":
                    bs_count += 1
                    j -= 1
                if bs_count % 2 == 0:
                    in_string = not in_string
            else:
                in_string = not in_string

        if in_string:
            if char == "\n":
                result.append("\\n")
            elif char == "\t":
                result.append("\\t")
            elif char == "\r":
                pass  # Skip carriage returns in strings
            else:
                result.append(char)
        else:
            result.append(char)

        i += 1

    return "".join(result)


# Known schema field names — used to find the "right" JSON object when
# multiple `{` characters appear in LLM output (e.g., markdown with code blocks).
_SCHEMA_FIELD_RE = re.compile(
    r'\{\s*"(?:answer|action|sql_query|excel_request|summary|outline|sections|content'
    r'|description|reasoning|result|data|items|categories|findings|recommendations'
    r'|stop_words|nodes|edges|milestones|phases|insights|review'
    r'|articles|report_title|executive_summary|key_trends|radar_items|market_signals'
    r'|radar_item_details|report_sections'
    # Roadmap schemas
    r'|roadmap_title|overall_vision|current_state_analysis|technology_domains'
    r'|key_technology_enablers|risks_and_mitigations|innovation_opportunities'
    r'|tabular_summary|llm_inferred_additions|phased_roadmap'
    r'|vision_and_end_goal|current_baseline|strategic_pillars'
    r'|enablers_and_dependencies|risks_and_mitigation|key_metrics_and_milestones'
    r'|future_opportunities'
    # Agent, analysis, document creator, and other schemas
    r'|requires_decomposition|hypothetical_document|verdict|themes'
    r'|file_name|values|document_title|heading|overall_score'
    r'|analysis_title|mind_map|document_summary|title'
    r'|technology_name|stopwords)"'
)


def _extract_json_block(text: str) -> str:
    """
    Extract the outermost JSON object or array from text that may contain
    preamble or postamble content.

    Strategy:
    1. If the text starts with { or [, use it directly — the first bracket
       IS the root JSON object.  Skip the schema-field regex which can
       accidentally match a nested sub-object.
    2. Otherwise there is preamble text: use the schema-field regex to find
       the correct JSON object (skipping stray braces in prose).
    3. Fall back to the first { or [ if no regex match.

    Uses bracket counting to find the correct closing bracket,
    properly handling strings (including escaped quotes).
    """
    # Strategy 1: Text starts with JSON — use the first bracket directly.
    # This avoids the schema-field regex matching a nested sub-object
    # (e.g. {"summary":...} inside {"roadmap_title":...,"current_state_analysis":{"summary":...}}).
    if text.startswith("{"):
        start = 0
        open_char = "{"
        close_char = "}"
    elif text.startswith("["):
        start = 0
        open_char = "["
        close_char = "]"
    else:
        # There is preamble text before the JSON — use schema-field regex
        # to skip stray braces in prose and find the real JSON object.
        schema_match = _SCHEMA_FIELD_RE.search(text)
        if schema_match:
            start = schema_match.start()
            open_char = "{"
            close_char = "}"
        else:
            # Fall back to first { or [
            start = -1
            open_char = None
            close_char = None
            for i, ch in enumerate(text):
                if ch == "{":
                    start = i
                    open_char = "{"
                    close_char = "}"
                    break
                elif ch == "[":
                    start = i
                    open_char = "["
                    close_char = "]"
                    break

    if start == -1:
        return text  # No JSON structure found, return as-is

    # Walk through to find matching close bracket, respecting strings
    depth = 0
    in_string = False
    escape_next = False
    end = len(text)

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\":
            if in_string:
                escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    return text[start:end]


# Keys that belong to a JSON Schema definition, not to actual data.
_SCHEMA_META_KEYS = frozenset({
    "$defs", "$ref", "$schema", "$id",
    "definitions", "properties", "required",
    "title", "type", "description", "additionalProperties",
    "allOf", "anyOf", "oneOf", "not", "enum", "const",
    "default", "examples",
})


def _strip_schema_metadata(parsed: dict, schema: type) -> dict:
    """
    Remove JSON-Schema metadata keys that the LLM erroneously echoed,
    keeping only data keys that the Pydantic model actually expects.

    Handles Pattern 1 (schema + data mixed) and Pattern 5 (schema only).
    Also resolves Pattern 4 ($ref values in data).
    """
    model_fields = set(getattr(schema, "model_fields", {}).keys())
    if not model_fields:
        return parsed

    # Separate data keys from schema-meta keys
    data_keys = {k for k in parsed if k in model_fields}
    meta_keys = {k for k in parsed if k in _SCHEMA_META_KEYS and k not in model_fields}

    if not meta_keys:
        return parsed  # No schema leakage detected

    # If we have data keys alongside meta keys, keep only the data
    if data_keys:
        return {k: v for k, v in parsed.items() if k in model_fields}

    # Pattern 6: LLM wrapped actual data inside "properties" (schema echo)
    if "properties" in parsed and isinstance(parsed["properties"], dict):
        inner = parsed["properties"]
        inner_data_keys = {k for k in inner if k in model_fields}
        if inner_data_keys:
            # Check if values are schema definitions (dicts with "type"/"title")
            # vs actual data.  Pure schema echo has ALL values as dicts with "type".
            schema_like = sum(
                1 for k in inner_data_keys
                if isinstance(inner[k], dict) and "type" in inner[k]
            )
            if schema_like < len(inner_data_keys):
                # Some values are real data — extract them
                return {k: v for k, v in inner.items() if k in model_fields}

    # Schema-only output (Pattern 5): nothing usable
    return parsed


import logging as _logging

_sanitizer_logger = _logging.getLogger("llm.sanitizer")


def _repair_truncated_json(text: str) -> str | None:
    """
    Attempt to repair JSON that was truncated mid-output (e.g., by num_predict limit).

    Strategy:
    1. Detect truncation: walk the text and check if brackets are unbalanced.
    2. Find the last complete array element (last '},') before truncation.
    3. Truncate to that point and close all remaining open brackets.

    Returns repaired JSON string, or None if repair is not possible.
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Quick check: if the text ends with a proper closing bracket, it's not truncated
    if text.endswith("}") or text.endswith("]"):
        # Verify balance by counting
        depth_obj = 0
        depth_arr = 0
        in_string = False
        escape_next = False
        for ch in text:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth_obj += 1
            elif ch == "}":
                depth_obj -= 1
            elif ch == "[":
                depth_arr += 1
            elif ch == "]":
                depth_arr -= 1
        if depth_obj == 0 and depth_arr == 0:
            return None  # Already balanced, not truncated

    # Find the last complete array/object element.
    # Walk backwards to find a position where we can cleanly close the JSON.
    # Look for patterns like '},', '}]', or a standalone '}' that ends an element.

    # First, find the last '}' that could end a complete object in an array.
    last_complete = -1
    depth_obj = 0
    depth_arr = 0
    in_string = False
    escape_next = False
    bracket_stack = []  # Track what brackets are open at each position

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            bracket_stack.append("{")
        elif ch == "[":
            bracket_stack.append("[")
        elif ch == "}":
            if bracket_stack and bracket_stack[-1] == "{":
                bracket_stack.pop()
                # If we're now inside an array (top of stack is '['),
                # this '}' closes a complete object element
                if bracket_stack and bracket_stack[-1] == "[":
                    last_complete = i
        elif ch == "]":
            if bracket_stack and bracket_stack[-1] == "[":
                bracket_stack.pop()

    if last_complete == -1:
        return None  # No complete array element found

    # Truncate to just after the last complete element
    truncated = text[: last_complete + 1]

    # Remove any trailing comma
    truncated = truncated.rstrip()
    if truncated.endswith(","):
        truncated = truncated[:-1]

    # Count remaining open brackets that need closing
    open_brackets = []
    in_string = False
    escape_next = False
    for ch in truncated:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            open_brackets.append("}")
        elif ch == "[":
            open_brackets.append("]")
        elif ch == "}" and open_brackets and open_brackets[-1] == "}":
            open_brackets.pop()
        elif ch == "]" and open_brackets and open_brackets[-1] == "]":
            open_brackets.pop()

    # Close remaining brackets in reverse order
    closing = "".join(reversed(open_brackets))
    repaired = truncated + closing

    _sanitizer_logger.warning(
        f"Truncated JSON repaired: kept {last_complete + 1} of {len(text)} chars, "
        f"closed {len(open_brackets)} bracket(s)"
    )

    return repaired


def parse_llm_json(raw: str, schema: Type[T]) -> T:
    """
    Parse and validate LLM output against a Pydantic schema with
    multiple fallback strategies.

    Strategies (in order):
    1. Sanitize + json.loads + strip schema metadata + model_validate
    2. json_repair.loads + strip schema metadata + model_validate
    3. Raise with clear error

    Args:
        raw: Raw LLM output string
        schema: Pydantic model class to validate against

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If all parsing strategies fail
    """
    cleaned = sanitize_llm_json(raw)

    # Strategy 1: Standard json.loads after sanitization
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            parsed = _strip_schema_metadata(parsed, schema)
        return schema.model_validate(parsed)
    except (json.JSONDecodeError, Exception):
        pass

    # Strategy 2: json_repair (handles structural issues)
    if json_repair is not None:
        try:
            repaired = json_repair.loads(cleaned)
            if isinstance(repaired, dict):
                repaired = _strip_schema_metadata(repaired, schema)
            if isinstance(repaired, (dict, list)):
                return schema.model_validate(repaired)
        except Exception:
            pass

        # Try repair on the original raw input as well (in case our
        # extraction mangled something)
        try:
            repaired = json_repair.loads(sanitize_llm_json(raw))
            if isinstance(repaired, dict):
                repaired = _strip_schema_metadata(repaired, schema)
            if isinstance(repaired, (dict, list)):
                return schema.model_validate(repaired)
        except Exception:
            pass

    # Strategy 3: Truncated JSON repair — recover partial data from
    # outputs that were cut off by num_predict/max_tokens limits.
    repaired_text = _repair_truncated_json(cleaned)
    if repaired_text:
        try:
            parsed = json.loads(repaired_text)
            if isinstance(parsed, dict):
                parsed = _strip_schema_metadata(parsed, schema)
            return schema.model_validate(parsed)
        except Exception:
            pass

        # Also try json_repair on the repaired text
        if json_repair is not None:
            try:
                repaired_parsed = json_repair.loads(repaired_text)
                if isinstance(repaired_parsed, dict):
                    repaired_parsed = _strip_schema_metadata(repaired_parsed, schema)
                if isinstance(repaired_parsed, (dict, list)):
                    return schema.model_validate(repaired_parsed)
            except Exception:
                pass

    # Strategy 4: Emergency fallback for answer-only schemas.
    # Do not fabricate tool-routing fields such as `action`, `sql_query`, etc.
    model_fields = getattr(schema, "model_fields", {})
    if "answer" in model_fields and "action" not in model_fields:
        try:
            fallback_data = {"answer": _sanitize_fallback_text(raw)[:8000]}
            return schema.model_validate(fallback_data)
        except Exception:
            pass

    raise ValueError(
        f"Failed to parse LLM output as {schema.__name__}. "
        f"Cleaned output: {cleaned[:500]}"
    )


# Regex to collapse 3+ consecutive newlines to 2
_EXCESSIVE_NEWLINES_RE = re.compile(r"\n{3,}")


def normalize_answer_content(text: str) -> str:
    """
    Post-process answer content after JSON parsing to fix common
    formatting artifacts from json_repair and LLM output.

    Handles:
    - Double-escaped newlines (literal \\n -> actual newline)
    - Double-escaped quotes (literal \\" -> actual ")
    - Double-escaped backslashes (literal \\\\ -> single \\)
    - Escaped forward slashes (\\/ -> /)
    - Literal \\t -> actual tab
    - Multiple consecutive blank lines -> max 2 newlines

    This function is idempotent: running it on already-clean text
    produces the same output (it matches literal 2-char escape
    sequences, not actual control characters).
    """
    if not text:
        return text

    result = text

    # Protect genuine escaped backslashes first (\\\\  -> placeholder)
    result = result.replace("\\\\", "\x00BSLASH\x00")

    # Double-escaped newlines -> actual newlines
    result = result.replace("\\n", "\n")

    # Double-escaped tabs -> actual tabs
    result = result.replace("\\t", "\t")

    # Double-escaped quotes -> actual quotes
    result = result.replace('\\"', '"')

    # Escaped forward slashes (common json_repair artifact)
    result = result.replace("\\/", "/")

    # Restore escaped backslashes
    result = result.replace("\x00BSLASH\x00", "\\")

    # Collapse excessive blank lines (3+ consecutive newlines -> 2)
    result = _EXCESSIVE_NEWLINES_RE.sub("\n\n", result)

    return result
