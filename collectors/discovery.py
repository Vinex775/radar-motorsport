"""Discover future-focused motorsport leads through Google News RSS.

Discovery Leads contains announcements, previews, calendars, entry lists and
other editorial clues about motorsport activity that has not happened yet.
It is not a live-stream feed; active streams belong in Live Now.
"""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus
from xml.etree import ElementTree

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Each search combines a motorsport family/region with future-focused terms.
FUTURE_NEWS_TERMS = (
    '("upcoming" OR "this weekend" OR "next weekend" OR "next round" OR '
    '"race calendar" OR "event calendar" OR "schedule announced" OR '
    '"dates announced" OR "entry list" OR "entries open" OR registration OR '
    'preview OR "season opener" OR "tickets on sale" OR "live stream" OR livestream)'
)

QUERIES = [
    f'(Formula 1 OR Formula 2 OR Formula 3 OR Formula 4 OR "Formula Regional" OR "Formula E") {FUTURE_NEWS_TERMS}',
    f'(karting OR kart OR "club karting" OR "national karting" OR "regional karting") {FUTURE_NEWS_TERMS}',
    f'(WRC OR ERC OR rally OR "rally raid" OR Dakar OR rallycross OR "cross country rally") {FUTURE_NEWS_TERMS}',
    f'(WEC OR ELMS OR IMSA OR endurance OR GT3 OR GT4 OR "GT World Challenge" OR Nürburgring) {FUTURE_NEWS_TERMS}',
    f'(NASCAR OR IndyCar OR Supercars OR DTM OR TCR OR BTCC OR "stock car") {FUTURE_NEWS_TERMS}',
    f'("drag racing" OR NHRA OR dragster OR arrancada OR "time attack") {FUTURE_NEWS_TERMS}',
    f'(drift OR "Formula Drift" OR "Drift Masters" OR hillclimb OR autocross) {FUTURE_NEWS_TERMS}',
    f'(MotoGP OR Moto2 OR Moto3 OR WorldSBK OR superbike OR "road racing motorcycle") {FUTURE_NEWS_TERMS}',
    f'(motocross OR supercross OR enduro OR trials OR "hard enduro" OR MXGP) {FUTURE_NEWS_TERMS}',
    f'(speedway OR "speedway grand prix" OR "ice speedway" OR "long track") {FUTURE_NEWS_TERMS}',
    f'("sprint car" OR midget OR "dirt late model" OR "short track racing" OR "oval racing") {FUTURE_NEWS_TERMS}',
    f'("club racing" OR "grassroots racing" OR "amateur racing" OR "local race series") {FUTURE_NEWS_TERMS}',
    f'(corrida OR automobilismo OR kart OR rally OR motocross) (calendário OR calendário OR "próxima etapa" OR "inscrições abertas" OR programação OR "ao vivo")',
    f'(carreras OR rally OR karting OR motocross) (próxima OR calendario OR "próxima ronda" OR inscripciones OR programación)',
    f'(Rennsport OR Rallye OR Kart OR Bergrennen OR Motorsport) (Vorschau OR Kalender OR Termine OR Nennung OR "nächstes Rennen")',
    f'(motorsport OR karting OR rally OR speedway) (upcoming OR calendar OR schedule OR entries) (Sweden OR Sverige)',
    f'(motorsport OR karting OR rally OR speedway) (upcoming OR calendar OR schedule OR entries) (Norway OR Norge)',
    f'(motorsport OR karting OR rally OR speedway OR autosuunnistus OR rallisprint) (upcoming OR calendar OR schedule OR entries) (Finland OR Suomi)',
    f'(motorsport OR karting OR rally OR speedway) (upcoming OR calendar OR schedule OR entries) (Denmark OR Danmark)',
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APEX-Motorsport-Radar/1.5.0; +https://github.com/)"}

EXCLUDED_NEWS_TERMS = (
    '-eleição -eleições -candidato -candidatos -senador -senado -governador -comício -comícios -política -político '
    '-election -elections -candidate -candidates -senator -senate -governor '
    '-voter -voters -GOP -Democrat -Democratic -Republican -politics '
    '-political -campaign -ballot -parliament -congress -mayor -politician '
    '-politicians -electionday'
)

NON_MOTORSPORT_RACING_RE = re.compile(
    r"\b(?:horse racing|horse race|thoroughbred|greyhound racing|dog racing|"
    r"harness racing|flat racing|steeplechase|road cycling|track cycling|"
    r"cycling race|marathon running|track and field|athletics championship)\b",
    re.IGNORECASE,
)

POLITICAL_CONTEXT_RE = re.compile(
    r"\b(?:elections?|election day|candidates?|senators?|senate|governors?|"
    r"presidents?|voters?|voting|gop|democrats?|republicans?|politics?|"
    r"political|campaigns?|ballots?|parliament|congress|mayors?|politicians?|"
    r"primary election|general election)\b",
    re.IGNORECASE,
)

MOTORSPORT_CONTEXT_RE = re.compile(
    r"\b(?:motorsports?|motor sports?|racing|race cars?|racecars?|racing cars?|"
    r"kart(?:ing)?|formula\s?[1-4e]|f[1-4]|fia|wrc|erc|wec|elms|imsa|nascar|"
    r"indycar|indy 500|motogp|moto2|moto3|worldsbk|wsbk|mxgp|supercross|"
    r"motocross|supermotocross|nhra|drag racing|dragster|speedway|hillclimb|"
    r"hill climb|drift masters|formula drift|gt3|gt4|gt world challenge|dtm|"
    r"btcc|tcr series|stock car|supercars championship|rallycross|rally raid|"
    r"rally championship|rally championships|rally series|rally driver|rally drivers|"
    r"rally car|rally cars|co[- ]drivers?|special stage|rally stage|rally stages|"
    r"parc ferme|paddock|pit lane|pit stop|race weekend|race circuit|race track|"
    r"endurance racing|sprint car|midget racing|dirt late model|time attack|"
    r"autocross|off[- ]road racing|autosuunnistus|rallisprint|rally sprint|"
    r"moottoriurheilu|kilpa-autoilu|rallye championship|sim racing|simracing|"
    r"iracing|assetto corsa|gran turismo|forza motorsport|automobilista|"
    r"rfactor|race room|raceroom|autocrossing|automobilismo|arrancada|"
    r"corrida de carros|automovilismo|autourheilu|rennen|bergrennen|"
    r"course auto|course de cote|folkrace|auto.?slalom|tractor pulling|"
    r"banger racing|short track racing)\b",
    re.IGNORECASE,
)


def is_motorsport_result(title: str, description: str = "") -> bool:
    """Reject political rallies/news and require explicit motorsport context."""
    text = f"{title or ''} {description or ''}"
    if POLITICAL_CONTEXT_RE.search(text) or NON_MOTORSPORT_RACING_RE.search(text):
        return False
    return bool(MOTORSPORT_CONTEXT_RE.search(text))


REACTION_ONLY_RE = re.compile(
    r"\b(?:react(?:ion)?|watchalong|watch along|second screen|live blog|live updates|"
    r"reaction stream|reação|reacao|react ao vivo|watch party|watch-party)\b",
    re.IGNORECASE,
)
WATCH_GUIDE_RE = re.compile(
    r"\b(?:live|where to watch|how to watch|watch live|watch online|live stream|livestream|live broadcast|live coverage|"
    r"ao vivo|assistir ao vivo|onde assistir|link para assistir|transmissão ao vivo|transmissao ao vivo|"
    r"streaming ao vivo|watch the race live)\b",
    re.IGNORECASE,
)
FUTURE_EVENT_RE = re.compile(
    r"\b(?:upcoming|this weekend|next weekend|next week|tomorrow|tonight|today|"
    r"next round|next season|season opener|season starts?|season preview|"
    r"calendar|schedule|entry list|entries open|registration open|"
    r"tickets on sale|dates announced|announces? (?:the )?calendar|"
    r"will host|will take place|scheduled for|set for|preview|pre[- ]event|"
    r"próximo|próxima|proxima etapa|próxima etapa|próximo fim de semana|"
    r"inscrições abertas|inscripcion(?:es)? abiertas|calendário|programação|"
    r"anuncia (?:o )?calendário|fechas confirmadas|termin(?:e|a) announced)\b",
    re.IGNORECASE,
)
POST_EVENT_RE = re.compile(
    r"\b(?:post[- ]session|post[- ]race|post[- ]event|after the race|after the event|"
    r"race recap|event recap|session recap|recap|review|results?|final standings|"
    r"winner|podium|highlights?|compilation|replay|full race archive|"
    r"pós[- ]sessão|pós[- ]corrida|pos[- ]sessao|pos[- ]corrida|"
    r"resultado(?:s)?|vencedor|campeão|campeonato decidido|resumo da corrida|"
    r"melhores momentos)\b",
    re.IGNORECASE,
)
FUTURE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def is_reaction_or_commentary(title: str, description: str = "") -> bool:
    """True when a result appears to be reaction/commentary rather than a race feed."""
    text = f"{title or ''} {description or ''}"
    if not REACTION_ONLY_RE.search(text):
        return False
    official_feed = re.search(
        r"\b(?:official race feed|full race broadcast|live race feed|official live broadcast)\b",
        text,
        re.IGNORECASE,
    )
    return not bool(official_feed)


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def is_upcoming_discovery(
    title: str,
    description: str = "",
    published: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Return True only for leads that point to future motorsport activity.

    A future year in the content is strong evidence. Otherwise, require an
    upcoming-event signal and a recent article date. Post-session recaps,
    results, replay pages and old "watch live" pages are not upcoming leads.
    """
    text = f"{title or ''} {description or ''}"
    if POST_EVENT_RE.search(text):
        return False

    current = now or datetime.now(timezone.utc)
    future_years = [int(value) for value in FUTURE_YEAR_RE.findall(text)]
    if any(year > current.year for year in future_years):
        return True

    if not FUTURE_EVENT_RE.search(text):
        return False

    stamp = _parse_published(published)
    if stamp is None:
        # A query may return a dated calendar/announcement with no RSS pubDate.
        return True
    age = current.astimezone(timezone.utc) - stamp
    return timedelta(0) <= age <= timedelta(days=45)


def is_stale_watch_guide(published: str | None, title: str, description: str = "", now=None) -> bool:
    """Compatibility helper for old database rows; these are hidden from Discovery Leads."""
    if not published or not WATCH_GUIDE_RE.search(f"{title or ''} {description or ''}"):
        return False
    current = now or datetime.now(timezone.utc)
    stamp = _parse_published(published)
    if stamp is None:
        return False
    return current.astimezone(timezone.utc) - stamp > timedelta(hours=36)


def is_valid_discovery(title: str, description: str = "", published: str | None = None, now=None) -> bool:
    """Validate motorsport relevance, independently from whether the lead is future-focused."""
    return (
        is_motorsport_result(title, description)
        and not is_reaction_or_commentary(title, description)
    )


def _plain_text(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def classify_access(text: str) -> str:
    """Classify only explicit access claims; do not confuse "free practice" with free access."""
    value = text.lower()
    if re.search(
        r"pay[- ]?per[- ]?view|\bppv\b|purchase (the )?(race|event|pass)|buy (the )?(race|event)|"
        r"pago por evento|compra avulsa|pagar por evento|pay-per-event",
        value,
    ):
        return "ppv"
    if re.search(
        r"subscription|subscriber only|monthly pass|season pass|paid stream|paywall|"
        r"assinatura|somente para assinantes|passe mensal|passe de temporada|suscripción|abonnement",
        value,
    ):
        return "subscription"
    if re.search(
        r"free[- ]to[- ](view|watch|air)|watch for free|free livestream|free live stream|free live broadcast|"
        r"live and free|stream(?:ed|ing)? live and free|grátis|gratuito|gratuitamente|de graça|"
        r"transmissão gratuita|acesso gratuito|gratis en directo|kostenlos live",
        value,
    ):
        return "free"
    return "unknown"


def detect_platform(text: str) -> str:
    """Detect all explicitly mentioned broadcast platforms, not just the first one."""
    value = text.lower()
    patterns = [
        (r"flyingfinn\.tv", "FlyingFinn.tv"),
        (r"moottoriurheilu\.tv", "Moottoriurheilu.tv"),
        (r"youtube", "YouTube"),
        (r"twitch", "Twitch"),
        (r"fiawec\+", "FIAWEC+"),
        (r"dirtvision", "DIRTVision"),
        (r"rally\.tv", "Rally.TV"),
        (r"motogp videopass|videopass", "MotoGP VideoPass"),
        (r"worldsbk videopass", "WorldSBK VideoPass"),
        (r"f1 tv", "F1 TV"),
        (r"dazn", "DAZN"),
        (r"flo?racing", "FloRacing"),
        (r"peacock", "Peacock"),
        (r"nhra\.tv|nhra tv", "NHRA.tv"),
        (r"smx video ?pass|supermotocross video pass", "SMX Video Pass"),
        (r"joyn", "Joyn"),
        (r"servustv", "ServusTV On"),
        (r"band ?play", "BandPlay"),
        (r"bandsports", "BandSports"),
        (r"sportv", "SporTV"),
        (r"globoplay", "Globoplay"),
        (r"imsa\.com/tvlive|imsa tv", "IMSA TV"),
        (r"ind(y|i)car live", "INDYCAR LIVE"),
        (r"fim-moto\.tv", "FIM-MOTO.TV"),
        (r"superview", "SuperView"),
        (r"kayo sports", "Kayo Sports"),
    ]
    found = [name for pattern, name in patterns if re.search(pattern, value)]
    return ", ".join(found[:4]) if found else "Unidentified"


def detect_series(text: str) -> str:
    value = text.lower()
    mapping = [
        (r"formula ?1|\bf1\b", "Formula 1"),
        (r"formula ?2|\bf2\b", "Formula 2"),
        (r"formula ?3|\bf3\b", "Formula 3"),
        (r"formula ?e", "Formula E"),
        (r"formula ?4|\bf4\b|formula regional|regional formula", "Junior formulas"),
        (r"formula student|formula sae", "Formula Student / SAE"),
        (r"fia world endurance championship|\bfia wec\b|\bwec\b", "FIA WEC"),
        (r"motogp|moto gp|moto2|moto3", "MotoGP / Moto2 / Moto3"),
        (r"worldsbk|world superbike|\bwsbk\b", "WorldSBK"),
        (r"mxgp|motocross|supercross|supermotocross|\bsmx\b", "Motocross / Supercross"),
        (r"hard enduro|enduro motorcycle|enduro world", "Enduro / Hard Enduro"),
        (r"speedway|long track|ice speedway", "Speedway"),
        (r"wec|world endurance|elms|imsa|24 hours of le mans|24h le mans", "Endurance / Prototypes"),
        (r"gt world|gt3|gt4|gt world challenge|british gt|gt open", "GT / GT3 / GT4"),
        (r"dtm|tcr|btcc|touring car|touring cars", "Touring Cars / TCR"),
        (r"nascar|stock car|supercars championship|v8 supercars", "Stock Cars / NASCAR"),
        (r"indycar|indy 500|indy nxt", "IndyCar"),
        (r"autosuunnistus", "Autosuunnistus / precision navigation motorsport"),
        (r"kart|karting|kartódromo|kartodromo", "Karting"),
        (r"rallycross|world rx|world rallycross|rally cross", "Rallycross"),
        (r"rally raid|dakar|baja|cross.country rally", "Rally Raid / Baja"),
        (r"rally|wrc|erc|rallye", "Rally"),
        (r"drag racing|dragster|nhra|arrancada|drag strip", "Drag racing"),
        (r"hill ?climb|hillclimb|bergrennen|subida de montanha", "Hillclimb"),
        (r"drift|formula drift", "Drift"),
        (r"autocross|autocrossing|autoslalom|auto slalom", "Autocross / Autoslalom"),
        (r"folkrace", "Folkrace"),
        (r"rallysprint|rally sprint", "Rallysprint"),
        (r"tractor pulling|tractor pull", "Tractor pulling"),
        (r"banger racing|short track racing", "Stock car / Short track"),
        (r"sprint car|midget|dirt late model|short.track racing|oval racing", "Oval / Sprint Cars / Midgets"),
        (r"time attack|time trial", "Time Attack"),
        (r"ice racing|ice racing car|snowmobile racing", "Ice / Snow racing"),
        (r"off.road|cross.country|trial(s)?", "Off-road / Trials"),
        (r"club racing|grassroots racing|amateur racing", "Club / Regional"),
    ]
    for pattern, name in mapping:
        if re.search(pattern, value):
            return name
    return "Motorsport — category to identify"


def _parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def locale_for_query(query: str) -> tuple[str, str, str]:
    """Choose a Google News edition based on country/language in the query."""
    value = (query or "").lower()
    regional = [
        (r"suecia|suécia|sverige|sweden|swedish", ("sv-SE", "SE", "SE:sv")),
        (r"noruega|norge|norway|norwegian|norsk", ("no-NO", "NO", "NO:no")),
        (r"dinamarca|danmark|denmark|danish|dansk", ("da-DK", "DK", "DK:da")),
        (r"finl[aâ]ndia|finland|suomi|finnish", ("fi-FI", "FI", "FI:fi")),
        (r"brasil|brazil|brasileir", ("pt-BR", "BR", "BR:pt")),
        (r"español|spanish|españa|espanha|spain|argentina|chile|méxico|mexico|colombia", ("es-ES", "ES", "ES:es")),
        (r"alemanha|deutschland|germany|german|österreich|austria|schweiz", ("de-DE", "DE", "DE:de")),
        (r"frança|french|france|français|belgique|belgium", ("fr-FR", "FR", "FR:fr")),
        (r"it[aá]lia|italia|italy|italiano", ("it-IT", "IT", "IT:it")),
        (r"pol[oô]nia|polska|poland|polish|polski", ("pl-PL", "PL", "PL:pl")),
        (r"jap[aã]o|日本|japan|japanese", ("ja-JP", "JP", "JP:ja")),
        (r"portugu|ao vivo|transmissão", ("pt-BR", "BR", "BR:pt")),
    ]
    for pattern, locale in regional:
        if re.search(pattern, value):
            return locale
    return ("en-US", "US", "US:en")


def _fetch_query(query: str) -> bytes:
    hl, gl, ceid = locale_for_query(query)
    safe_query = f"({query}) {EXCLUDED_NEWS_TERMS}"
    url = "https://news.google.com/rss/search?q=" + quote_plus(safe_query) + f"&hl={hl}&gl={gl}&ceid={ceid}"
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=10) as response:
        return response.read()


def _parse_feed(payload: bytes, limit: int = 30) -> list[dict]:
    root = ElementTree.fromstring(payload)
    results: dict[str, dict] = {}
    for item in root.findall(".//item"):
        title = _plain_text(item.findtext("title", ""))
        link = (item.findtext("link", "") or "").strip()
        description = _plain_text(item.findtext("description", ""))
        published = _parse_date(item.findtext("pubDate", ""))
        source_node = item.find("source")
        source_name = _plain_text(source_node.text if source_node is not None else "Google News")
        if not title or not link or not link.startswith(("http://", "https://")):
            continue
        if not is_valid_discovery(title, description, published):
            continue
        key = hashlib.sha256(link.encode("utf-8")).hexdigest()[:18]
        full_text = f"{title} {description}"
        upcoming = is_upcoming_discovery(title, description, published)
        historical = (
            is_stale_watch_guide(published, title, description)
            or bool(POST_EVENT_RE.search(full_text))
            or (
                _parse_published(published) is not None
                and datetime.now(timezone.utc) - _parse_published(published) > timedelta(days=45)
                and not any(year > datetime.now(timezone.utc).year for year in map(int, FUTURE_YEAR_RE.findall(full_text)))
            )
        )
        lead_status = "upcoming_lead" if upcoming else "historical_reference" if historical else "unverified_lead"
        results[key] = {
            "id": key,
            "title": title,
            "summary": description[:500],
            "url": link,
            "published": published,
            "source_name": source_name,
            "series": detect_series(full_text),
            "platform": detect_platform(full_text),
            "access": classify_access(full_text),
            "lead_status": lead_status,
            "is_verified_live": False,
            "note": (
                "Future motorsport lead. It points to an upcoming event, calendar, entry list, "
                "preview or broadcast announcement; it is not proof that a stream is live now."
                if upcoming else
                "Historical reference. Kept in local storage for research, but hidden from the future Discovery Leads view."
                if historical else
                "Unverified editorial lead. It may be relevant, but APEX has not established that the event is still upcoming."
            ),
        }
    ordered = sorted(results.values(), key=lambda item: item.get("published") or "", reverse=True)
    return ordered[:limit]


def discover_broadcast_leads(limit: int = 60) -> list[dict]:
    """Run broad future-focused searches while isolating failures by motorsport family."""
    fetched: list[bytes] = []
    with ThreadPoolExecutor(max_workers=min(8, len(QUERIES))) as pool:
        futures = [pool.submit(_fetch_query, query) for query in QUERIES]
        for future in as_completed(futures):
            try:
                fetched.append(future.result())
            except (HTTPError, URLError, TimeoutError, OSError):
                continue

    if not fetched:
        raise OSError("Could not query the news RSS feed. Check your internet connection.")

    merged: dict[str, dict] = {}
    for payload in fetched:
        try:
            for item in _parse_feed(payload, limit=limit):
                merged[item["id"]] = item
        except ElementTree.ParseError:
            continue
    ordered = sorted(merged.values(), key=lambda item: item.get("published") or "", reverse=True)
    return ordered[:limit]


def search_custom_discovery_leads(query: str, limit: int = 25) -> list[dict]:
    """Search for future motorsport activity in a user-entered discipline or region."""
    clean = re.sub(r"\s+", " ", (query or "")).strip()[:180]
    if len(clean) < 2:
        raise ValueError("Enter at least 2 characters to search.")
    payload = _fetch_query(f'({clean}) {FUTURE_NEWS_TERMS}')
    try:
        results = _parse_feed(payload, limit=max(1, min(limit, 40)))
    except ElementTree.ParseError as exc:
        raise OSError("The news source returned an invalid feed.") from exc
    for item in results:
        if item.get("lead_status") == "upcoming_lead":
            item["note"] = (
                "Future custom-search lead. Check the organizer's original page for the event date, "
                "session, platform, territory and access conditions."
            )
        elif item.get("lead_status") == "historical_reference":
            item["note"] = "Historical custom-search editorial lead. Kept for research, not shown as a future lead."
        else:
            item["note"] = "Custom Google News editorial lead. It is not yet confirmed as a future event; verify dates with the organizer."
    return results
