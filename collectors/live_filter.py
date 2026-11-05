"""Heuristic filters for the APEX Live Now feed.

A platform API confirms that a channel is broadcasting, not that it is showing
physical motorsport. Generic game/category labels therefore require evidence
in the stream title or description before they are admitted to Live Now.
"""
from __future__ import annotations

import re
from typing import Any

REPLAY_LOOP_RE = re.compile(
    r"\b(?:24\s*/\s*7|24x7|non[ -]?stop|loop(?:ed|ing)?|replays?|"
    r"full[ -]?race[ -]?replay|race[ -]?archive|best[ -]?of|highlights?|"
    r"compilation|throwback|past[ -]event|previous[ -]race|from\s+(?:19|20)\d{2})\b",
    re.IGNORECASE,
)

# Explicit game names that frequently appear as Twitch/Kick categories or titles.
VIDEO_GAME_TITLE_RE = re.compile(
    r"\b(?:forza(?:\s+(?:motorsport|horizon))?|sonic\s+racing(?:\s*:\s*crossworlds)?|"
    r"motorsport\s+manager|racing\s+master|racing\s+lagoon|descent|"
    r"gran\s+turismo(?:\s*\d+)?|assetto\s+corsa|i[ -]?racing|"
    r"automobilista(?:\s*2)?|rfactor(?:\s*2)?|race\s*room|raceroom|"
    r"project\s+cars|need\s+for\s+speed|wreckfest|beamng(?:\s+drive)?|"
    r"trackmania|the\s+crew(?:\s+motorfest)?|carx\s+drift|f1\s+\d{2}\s+game)\b",
    re.IGNORECASE,
)

# Broader wording catches streams whose category is a game title not yet listed
# above, e.g. "PS1 Racing Games!" in the category "Racing Lagoon".
GAMEPLAY_CUE_RE = re.compile(
    r"\b(?:gameplay|video\s+games?|gaming|game\s+stream|playing\s+games?|"
    r"racing\s+games?|race\s+games?|career\s+mode|multiplayer|ranked\s+match|"
    r"esports?|e[ -]?sports|sim\s*racing|simracing|simulator\s+game|"
    r"speedrun|gameplay\s+live|ps[1-5]|playstation(?:\s*[1-5])?|"
    r"retro\s+gaming|retro\s+games?|console\s+gaming)\b",
    re.IGNORECASE,
)

NON_RACE_SUPPORT_RE = re.compile(
    r"\b(?:track|circuit|course|raceway|speedway)\s+(?:construction|building|build|"
    r"maintenance|repair|preparation|prep|grading|grooming)\b|"
    r"\b(?:construction|maintenance|repair)\s+of\s+(?:the\s+)?"
    r"(?:track|circuit|course|raceway)\b|"
    r"\bbuilding\s+(?:the\s+)?(?:track|circuit|course|raceway)\b|"
    r"\b(?:track|circuit|course)\s+(?:work|works|project)\b",
    re.IGNORECASE,
)

GENERIC_RACING_CATEGORY_RE = re.compile(
    r"^(?:racing|auto racing|car racing|motorsport|motorsports|motor sport|motor sports)$",
    re.IGNORECASE,
)

# These cues describe an identifiable real-world race, championship, session,
# venue or event. Generic words such as "live" or "racing" are insufficient.
PHYSICAL_RACE_EVIDENCE_RE = re.compile(
    r"\b(?:championship|championships|series|grand prix|gp|formula\s?[1-4e]|f[1-4]|"
    r"formula regional|dakar|wrc|erc|wec|imsa|nascar|indycar|motogp|moto2|moto3|"
    r"worldsbk|mxgp|supercross|nhra|dtm|btcc|tcr|gt3|gt4|world challenge|"
    r"world of outlaws|sprint cars?|late models?|midgets?|karting|kart race|"
    r"rally|rallycross|rally raid|drift masters|formula drift|hillclimb|"
    r"qualifying|practice|free practice|hyperpole|special stage|stage\s*\d+|"
    r"time attack|race weekend|dirt track|cup|trophy)\b",
    re.IGNORECASE,
)


def classify_live_candidate(item: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (keep_in_live_now, exclusion_reason) for a platform result."""
    title = str(item.get("title") or "")
    description = str(item.get("description") or "")
    category = str(item.get("category") or "")
    tags_value = item.get("tags") or []
    tags = tags_value if isinstance(tags_value, str) else " ".join(str(tag) for tag in tags_value)
    content = " ".join((title, description, category, tags))

    if REPLAY_LOOP_RE.search(content):
        return False, "replay_or_loop"
    if VIDEO_GAME_TITLE_RE.search(content) or GAMEPLAY_CUE_RE.search(content):
        return False, "video_game"
    if NON_RACE_SUPPORT_RE.search(title):
        return False, "non_race_support_activity"

    # Generic Racing categories and ambiguous category names containing
    # "racing" need explicit real-world event evidence in title/description/tags.
    # Known game names were rejected above before reaching this check.
    if GENERIC_RACING_CATEGORY_RE.fullmatch(category.strip()):
        evidence = " ".join((title, description, tags))
        if not PHYSICAL_RACE_EVIDENCE_RE.search(evidence):
            return False, "insufficient_motorsport_evidence"

    return True, None
