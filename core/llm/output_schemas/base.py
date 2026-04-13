"""
Base class for LLM output schemas with common sanitization validators.

Provides automatic Unicode whitespace normalization for all string fields
as a safety net after JSON parsing.
"""

import re

from pydantic import BaseModel, field_validator, model_validator

from core.utils.llm_output_sanitizer import normalize_answer_content


# Unicode whitespace → regular space
_UNICODE_WS_RE = re.compile(
    r"[\u00a0\u2009\u200a\u202f\u00ad\u2002\u2003\u2004\u2005\u2006\u2007\u2008]"
)

# Zero-width characters → remove
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060\u180e]")


def _clean_str(v: str) -> str:
    """Normalize unicode whitespace and remove zero-width chars from a string."""
    v = _UNICODE_WS_RE.sub(" ", v)
    v = _ZERO_WIDTH_RE.sub("", v)
    return v


class LLMOutputBase(BaseModel):
    """
    Base class for all LLM output schemas.

    Applies Unicode whitespace normalization to all string fields
    via a 'before' validator, so even if the JSON parsed correctly
    but string VALUES contain non-breaking spaces or zero-width chars,
    they get cleaned during Pydantic validation.
    """

    @field_validator("*", mode="before")
    @classmethod
    def normalize_unicode_whitespace(cls, v):
        if isinstance(v, str):
            return _clean_str(v)
        if isinstance(v, list):
            return [_clean_str(item) if isinstance(item, str) else item for item in v]
        return v

    @model_validator(mode="after")
    def normalize_string_fields(self):
        """
        Post-construction normalization for ALL string fields.
        Fixes formatting artifacts from json_repair (double-escaped
        newlines, quotes, etc.) that would break markdown rendering
        in summary, answer, description, and other text fields.

        Recurses into nested BaseModel instances and lists so that
        nested schemas (e.g., ReportSection.content, RadarItemDetail.what_it_is)
        also get normalized.
        """
        _normalize_model_strings(self)
        return self


def _normalize_model_strings(model: BaseModel) -> None:
    """Recursively normalize all string fields in a Pydantic model."""
    for field_name in model.__class__.model_fields:
        value = getattr(model, field_name, None)
        if isinstance(value, str):
            setattr(model, field_name, normalize_answer_content(value))
        elif isinstance(value, list):
            normalized = []
            for item in value:
                if isinstance(item, str):
                    normalized.append(normalize_answer_content(item))
                elif isinstance(item, BaseModel):
                    _normalize_model_strings(item)
                    normalized.append(item)
                else:
                    normalized.append(item)
            setattr(model, field_name, normalized)
        elif isinstance(value, BaseModel):
            _normalize_model_strings(value)
