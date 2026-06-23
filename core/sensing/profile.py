"""
User Profile — the single source of truth for personalization.

Supersedes the older ``org_context`` and absorbs ``topic_preferences`` into one
structured, per-profile object. ``experience_memory`` (report-quality self-
learning) stays a separate subsystem.

For now there is no real login: a user can keep MULTIPLE profiles and select an
"active" one client-side; reports are tagged to a profile_id. Existing reports
(and a fresh install) fall under the "default" profile.

Storage: data/{user_id}/sensing/profiles/{profile_id}.json
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional

import aiofiles
from pydantic import BaseModel, Field

from core.sensing.org_context import RadarCustomization

logger = logging.getLogger("sensing.profile")

DEFAULT_PROFILE_ID = "default"

# Roles map to the existing ROLE_PROMPTS in report_generator.
VALID_ROLES = {"cto", "engineering_lead", "developer", "product_manager", "analyst", "exec", "general"}


class DomainPrefs(BaseModel):
    """Per-domain refinements layered on top of the global interests/avoid."""

    interested: List[str] = Field(default_factory=list)
    not_interested: List[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    id: str = Field(default=DEFAULT_PROFILE_ID, description="Stable profile id (slug).")
    name: str = Field(default="Default", description="Display name for the profile.")
    role: str = Field(default="general", description="Persona / stakeholder role.")

    tech_stack: List[str] = Field(default_factory=list)
    priorities: List[str] = Field(default_factory=list)
    competitors: List[str] = Field(default_factory=list, description="Companies to watch.")

    # Global interest model (applied across all domains).
    interests: List[str] = Field(default_factory=list, description="Topics/technologies to follow.")
    avoid: List[str] = Field(default_factory=list, description="Topics to de-prioritize.")

    # Per-domain overrides (decision ii: global + per-domain).
    domain_overrides: Dict[str, DomainPrefs] = Field(default_factory=dict)

    # Personalization intensity slider (0-100). Default 80.
    personalization: int = Field(default=80)

    radar_customization: Optional[RadarCustomization] = Field(default=None)
    updated_at: str = Field(default="")


# ── Paths ──────────────────────────────────────────────────────────────────

def _profiles_dir(user_id: str) -> str:
    return f"data/{user_id}/sensing/profiles"


def _profile_path(user_id: str, profile_id: str) -> str:
    return os.path.join(_profiles_dir(user_id), f"{profile_id}.json")


def slugify_profile_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "profile"


def _domain_slug(domain: str) -> str:
    return (domain or "").lower().replace(" ", "_").replace("/", "_")


# ── Migration from legacy org_context + topic_preferences ────────────────────

def _migrate_legacy_sync(user_id: str) -> Optional[UserProfile]:
    """Build a 'default' profile from legacy org_context.json + topic_prefs_*.json.

    Synchronous (small local files); called once when no profiles exist yet.
    """
    base = f"data/{user_id}/sensing"
    org_path = os.path.join(base, "org_context.json")
    profile = UserProfile(id=DEFAULT_PROFILE_ID, name="Default")

    if os.path.exists(org_path):
        try:
            with open(org_path, "r", encoding="utf-8") as f:
                org = json.loads(f.read())
            profile.tech_stack = org.get("tech_stack", []) or []
            profile.priorities = org.get("priorities", []) or []
            profile.role = org.get("stakeholder_role", "general") or "general"
            if org.get("radar_customization"):
                try:
                    profile.radar_customization = RadarCustomization(**org["radar_customization"])
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Legacy org_context migration failed for {user_id}: {e}")

    # Fold per-domain topic prefs into domain_overrides.
    try:
        for fname in os.listdir(base):
            if fname.startswith("topic_prefs_") and fname.endswith(".json"):
                slug = fname[len("topic_prefs_"):-len(".json")]
                try:
                    with open(os.path.join(base, fname), "r", encoding="utf-8") as f:
                        tp = json.loads(f.read())
                    profile.domain_overrides[slug] = DomainPrefs(
                        interested=tp.get("interested", []) or [],
                        not_interested=tp.get("not_interested", []) or [],
                    )
                except Exception:
                    continue
    except FileNotFoundError:
        pass

    return profile


# ── Load / save / list ───────────────────────────────────────────────────────

async def list_profiles(user_id: str) -> List[UserProfile]:
    """Return all profiles for the user, ensuring a 'default' exists (migrating
    legacy data on first run)."""
    pdir = _profiles_dir(user_id)
    if not os.path.isdir(pdir) or not any(f.endswith(".json") for f in os.listdir(pdir)):
        # First run for this user — create default (migrating legacy if present).
        default = _migrate_legacy_sync(user_id)
        if default is not None:
            await save_profile(user_id, default)

    profiles: List[UserProfile] = []
    if os.path.isdir(pdir):
        for fname in sorted(os.listdir(pdir)):
            if not fname.endswith(".json"):
                continue
            try:
                async with aiofiles.open(os.path.join(pdir, fname), "r", encoding="utf-8") as f:
                    profiles.append(UserProfile(**json.loads(await f.read())))
            except Exception as e:
                logger.warning(f"Failed to load profile {fname}: {e}")
    # Guarantee default first.
    profiles.sort(key=lambda p: (p.id != DEFAULT_PROFILE_ID, p.name.lower()))
    return profiles


async def load_profile(user_id: str, profile_id: Optional[str]) -> Optional[UserProfile]:
    """Load one profile by id (falling back to default). Returns None if the
    user has no profiles at all and migration produced nothing."""
    pid = profile_id or DEFAULT_PROFILE_ID
    fpath = _profile_path(user_id, pid)
    if not os.path.exists(fpath):
        # Ensure default/migration has run, then retry.
        await list_profiles(user_id)
        if not os.path.exists(fpath):
            fpath = _profile_path(user_id, DEFAULT_PROFILE_ID)
            if not os.path.exists(fpath):
                return None
    try:
        async with aiofiles.open(fpath, "r", encoding="utf-8") as f:
            return UserProfile(**json.loads(await f.read()))
    except Exception as e:
        logger.warning(f"Failed to load profile {pid} for {user_id}: {e}")
        return None


async def save_profile(user_id: str, profile: UserProfile) -> UserProfile:
    from datetime import datetime, timezone
    profile.updated_at = datetime.now(timezone.utc).isoformat()
    if not profile.id:
        profile.id = slugify_profile_name(profile.name)
    fpath = _profile_path(user_id, profile.id)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)
    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
        await f.write(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))
    logger.info(f"Profile saved for {user_id}: id={profile.id} name={profile.name!r}")
    return profile


async def delete_profile(user_id: str, profile_id: str) -> bool:
    if profile_id == DEFAULT_PROFILE_ID:
        return False
    fpath = _profile_path(user_id, profile_id)
    if os.path.exists(fpath):
        os.remove(fpath)
        return True
    return False


# ── Resolution helpers (used by the pipeline) ────────────────────────────────

def resolve_profile_prefs(profile: UserProfile, domain: str) -> dict:
    """Merge global interests/avoid with the active domain's overrides.

    Returns {"interests": [...], "avoid": [...]} — de-duplicated, order-preserved.
    """
    over = profile.domain_overrides.get(_domain_slug(domain)) if profile else None
    interests = list(profile.interests) if profile else []
    avoid = list(profile.avoid) if profile else []
    if over:
        interests += [t for t in over.interested if t not in interests]
        avoid += [t for t in over.not_interested if t not in avoid]
    # competitors are also interest signals for retrieval/classification
    if profile and profile.competitors:
        interests += [c for c in profile.competitors if c not in interests]
    return {
        "interests": list(dict.fromkeys(interests)),
        "avoid": list(dict.fromkeys(avoid)),
    }


def build_profile_prompt(profile: UserProfile) -> str:
    """Structured personalization block injected into report generation."""
    if not profile:
        return ""
    parts = []
    if profile.tech_stack:
        parts.append(f"Tech stack: {', '.join(profile.tech_stack)}")
    if profile.priorities:
        parts.append(f"Strategic priorities: {', '.join(profile.priorities)}")
    if profile.interests:
        parts.append(f"Interest areas: {', '.join(profile.interests)}")
    if profile.competitors:
        parts.append(f"Competitors/watchlist: {', '.join(profile.competitors)}")
    if profile.avoid:
        parts.append(f"De-prioritize: {', '.join(profile.avoid)}")
    if not parts:
        return ""
    return (
        "READER PROFILE — tailor the report to this reader. "
        + ". ".join(parts) + ". "
        "COVERAGE REQUIREMENTS: lead the executive summary with the developments most "
        "relevant to the reader's interest areas and stack; flag technologies that "
        "complement or threaten their stack. For EACH strategic priority listed above, "
        "surface the most relevant development this period, or explicitly state that "
        "there was no significant movement. Do NOT omit major developments just because "
        "they fall outside these interests."
    )


def build_profile_directives(profile: UserProfile) -> str:
    """Explicit alignment directives routed through ``custom_requirements``.

    Unlike :func:`build_profile_prompt` (which only reaches the core phase via
    ``org_context``), this string is folded into ``custom_requirements`` and so
    reaches BOTH classification (relevance weighting) and every report phase —
    including the insights phase where recommendations are written.
    """
    if not profile:
        return ""
    bits = []
    if profile.interests:
        bits.append(f"interest areas ({', '.join(profile.interests)})")
    if profile.priorities:
        bits.append(f"strategic priorities ({', '.join(profile.priorities)})")
    if profile.tech_stack:
        bits.append(f"tech stack ({', '.join(profile.tech_stack)})")
    if profile.competitors:
        bits.append(f"watchlist ({', '.join(profile.competitors)})")
    if not bits:
        return ""
    parts = [
        "READER ALIGNMENT — the reader's " + "; ".join(bits) + ".",
        "Score and prioritize developments that touch these notably higher "
        "(do not invent relevance for genuinely off-topic items).",
    ]
    if profile.priorities:
        parts.append(
            "Frame each recommendation as a concrete action tied to a specific "
            "strategic priority above, naming the priority it serves."
        )
    return " ".join(parts)


def profile_match_terms(profile: UserProfile, domain: str = "") -> List[str]:
    """Ordered, de-duplicated terms the report should align to: interests
    (incl. per-domain overrides + competitors), priorities, and tech stack."""
    if not profile:
        return []
    prefs = resolve_profile_prefs(profile, domain)
    terms = list(prefs.get("interests") or [])
    terms += list(profile.priorities or [])
    terms += list(profile.tech_stack or [])
    out: List[str] = []
    seen = set()
    for t in terms:
        t = (t or "").strip()
        key = t.lower()
        if len(t) >= 2 and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def profile_retrieval_terms(profile: UserProfile) -> List[str]:
    """Terms that should additionally widen RETRIEVAL queries (search): strategic
    priorities and tech stack.

    Interests + competitors already enter retrieval via ``resolve_profile_prefs``
    (folded into ``must_include``). Priorities/stack are kept OUT of
    ``must_include`` on purpose — that is a mandatory classification filter — and
    are used here only to fetch more candidate articles; classification and
    synthesis weight them softly via the profile directives.
    """
    if not profile:
        return []
    terms = list(profile.priorities or []) + list(profile.tech_stack or [])
    out: List[str] = []
    seen = set()
    for t in terms:
        t = (t or "").strip()
        key = t.lower()
        if len(t) >= 2 and key not in seen:
            seen.add(key)
            out.append(t)
    return out


_TERM_RE_CACHE: Dict[str, "re.Pattern"] = {}


def term_matches(term: str, text_lower: str) -> bool:
    """Word-boundary match of ``term`` within an already-lowercased ``text``.

    Word boundaries avoid the substring false-positives of naive matching
    (e.g. "Go" matching "Google", "AI" matching "rain") while still letting
    short, valid acronyms like "AI"/"ML" match the standalone word.
    """
    t = (term or "").strip().lower()
    if not t:
        return False
    rx = _TERM_RE_CACHE.get(t)
    if rx is None:
        rx = re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)")
        _TERM_RE_CACHE[t] = rx
    return rx.search(text_lower) is not None
