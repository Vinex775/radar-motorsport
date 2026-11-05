"""Heuristic filters for the APEX Live Now feed.

Platform APIs prove that a channel is broadcasting; they do not prove that
its content is a real-world motorsport session. This module removes obvious
replay/loop broadcasts, video-game streams, and non-racing support activity.
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

# These are video games/simulators, not broadcasts of physical racing.
# Keep the list conservative: generic words such as "racing" or "motorsport"
# must never be enough to classify a stream as a game.
VIDEO_GAME_TITLE_RE = re.compile(
    r"\b(?:forza(?:\s+(?:motorsport|horizon))?|sonic\s+racing(?:\s*:\s*crossworlds)?|"
    r"motorsport\s+manager|racing\s+master|gran\s+turismo(?:\s*\d+)?|assetto\s+corsa|"
    r"i[ -]?racing|automobilista(?:\s*2)?|rfactor(?:\s*2)?|race\s*room|raceroom|"
    r"project\s+cars|need\s+for\s+speed|wreckfest|beamng(?:\s+drive)?|"
    r"trackmania|the\s+crew(?:\s+motorfest)?|carx\s+drift|f1\s+\d{2}\s+game)\b",
    re.IGNORECASE,
)

GAMEPLAY_CUE_RE = re.compile(
    r"\b(?:gameplay|video\s+game|gaming|game\s+stream|playing\s+game|"
    r"career\s+mode|multiplayer|ranked\s+match|esports?|e[ -]?sports|"
    r"sim\s*racing|simracing|simulator\s+game)\b",
    re.IGNORECASE,
)

# A real-time channel can be live while showing work around an event rather
# than the competition. Keep these out of Live Now; they may be useful as
# Discovery Leads if found through news/search sources.
NON_RACE_SUPPORT_RE = re.compile(
    r"\b(?:track|circuit|course|raceway|speedway)\s+(?:construction|building|build|"
    r"maintenance|repair|preparation|prep|grading|grooming)\b|"
    r"\b(?:construction|maintenance|repair)\s+of\s+(?:the\s+)?"
    r"(?:track|circuit|course|raceway)\b|"
    r"\bbuilding\s+(?:the\s+)?(?:track|circuit|course|raceway)\b|"
    r"\b(?:track|circuit|course)\s+(?:work|works|project)\b",
    re.IGNORECASE,
)


def classify_live_candidate(item: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (keep_in_live_now, exclusion_reason) for a platform result."""
    title = str(item.get("title") or "")
    description = str(item.get("description") or "")
    category = str(item.get("category") or "")
    tags_value = item.get("tags") or []
    tags = tags_value if isinstance(tags_value, str) else " ".join(str(tag) for tag in tags_value)

    # Do not match the generic "24h" used by endurance races. Only explicit
    # loop/24-7 language and replay/archive/highlight wording is rejected.
    content = " ".join((title, description, category, tags))
    if REPLAY_LOOP_RE.search(content):
        return False, "replay_or_loop"

    # Twitch/Kick often expose the game's name as the stream category.
    if VIDEO_GAME_TITLE_RE.search(category) or VIDEO_GAME_TITLE_RE.search(title):
        return False, "video_game"
    if GAMEPLAY_CUE_RE.search(title):
        return False, "video_game"

    # Event infrastructure work is not a race session, even when the category
    # is a legitimate motorsport discipline (e.g. snowmobile racing).
    if NON_RACE_SUPPORT_RE.search(title):
        return False, "non_race_support_activity"

    return True, None
