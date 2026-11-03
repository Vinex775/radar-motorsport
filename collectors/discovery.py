"""Descobre pistas de transmissões via Google News RSS.

Os resultados são leads editoriais, nunca confirmação de uma live ativa.
A modalidade, plataforma e acesso são inferidos apenas quando o texto contém
indícios explícitos; dúvidas permanecem como "unknown".
"""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus
from xml.etree import ElementTree

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Buscas deliberadamente amplas e agrupadas por famílias. A busca personalizada
# da interface complementa esta varredura para séries locais/clubes muito pequenos.
QUERIES = [
    '("live stream" OR livestream OR "watch live") (Formula 1 OR Formula 2 OR Formula 3 OR Formula 4 OR "Formula Regional" OR "Formula E")',
    '("live stream" OR livestream OR "watch live") (karting OR kart OR "club karting" OR "national karting" OR "regional karting")',
    '("live stream" OR livestream OR "watch live") (WRC OR ERC OR rally OR "rally raid" OR Dakar OR rallycross OR "cross country rally")',
    '("live stream" OR livestream OR "watch live") (WEC OR ELMS OR IMSA OR endurance OR GT3 OR GT4 OR "GT World Challenge" OR Nürburgring)',
    '("live stream" OR livestream OR "watch live") (NASCAR OR IndyCar OR Supercars OR DTM OR TCR OR BTCC OR "stock car")',
    '("live stream" OR livestream OR "watch live") (drag racing OR NHRA OR dragster OR arrancada OR "time attack")',
    '("live stream" OR livestream OR "watch live") (drift OR "Formula Drift" OR "Drift Masters" OR hillclimb OR autocross)',
    '("live stream" OR livestream OR "watch live") (MotoGP OR Moto2 OR Moto3 OR WorldSBK OR superbike OR road racing motorcycle)',
    '("live stream" OR livestream OR "watch live") (motocross OR supercross OR enduro OR trials OR hard enduro OR MXGP)',
    '("live stream" OR livestream OR "watch live") (speedway OR "speedway grand prix" OR "ice speedway" OR "long track")',
    '("live stream" OR livestream OR "watch live") ("sprint car" OR midget OR "dirt late model" OR "short track racing" OR "oval racing")',
    '("live stream" OR livestream OR "watch live") ("club racing" OR "grassroots racing" OR "amateur racing" OR "local race series")',
    '(corrida ao vivo OR automobilismo ao vivo OR kart ao vivo OR rally ao vivo OR transmissão ao vivo) (corrida OR campeonato)',
    '(carreras en directo OR rally en directo OR karting en directo OR motocross en directo) campeonato',
    '(Rennsport live OR Rallye live OR Kart live OR Bergrennen live OR Motorsport livestream) Meisterschaft',
    '(motorsport live OR karting live OR rally live OR speedway live) Sweden OR Sverige',
    '(motorsport live OR karting live OR rally live OR speedway live) Norway OR Norge',
    '(motorsport live OR karting live OR rally live OR speedway live) Finland OR Suomi',
    '(motorsport live OR karting live OR rally live OR speedway live) Denmark OR Danmark',
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; APEX-Motorsport-Radar/1.1.1; +https://github.com/)"}
LIVE_TERMS = '("live stream" OR livestream OR "watch live" OR streaming OR "ao vivo" OR transmissão)'

# Google News interpreta "rally" também como comício. Os termos negativos
# ajudam na consulta, mas a validação local abaixo é a barreira definitiva.
EXCLUDED_NEWS_TERMS = (
    '-election -elections -candidate -candidates -senator -senate -governor '
    '-voter -voters -GOP -Democrat -Democratic -Republican -politics '
    '-political -campaign -ballot -parliament -congress -mayor -politician '
    '-politicians -electionday'
)

POLITICAL_CONTEXT_RE = re.compile(
    r"\b(?:elections?|election day|candidates?|senators?|senate|governors?|"
    r"presidents?|voters?|voting|gop|democrats?|republicans?|politics?|"
    r"political|campaigns?|ballots?|parliament|congress|mayors?|politicians?|"
    r"primary election|general election)\b",
    re.IGNORECASE,
)

# Sinais explícitos de esporte a motor, sem depender da palavra ambígua "race".
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
    r"autocross|off[- ]road racing)\b",
    re.IGNORECASE,
)


def is_motorsport_result(title: str, description: str = "") -> bool:
    """Rejeita comícios/notícias políticas e exige contexto explícito de corrida.

    "Rally" sozinho nunca é evidência suficiente: precisa vir acompanhado
    de termos típicos de rally automobilístico (WRC, etapa, piloto, carro etc.).
    """
    text = f"{title or ''} {description or ''}"
    if POLITICAL_CONTEXT_RE.search(text):
        return False
    return bool(MOTORSPORT_CONTEXT_RE.search(text))


def _plain_text(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def classify_access(text: str) -> str:
    """Classifica somente pistas explícitas; não confunde 'free practice' com grátis."""
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
        r"free[- ]to[- ](view|watch|air)|watch for free|free livestream|free live stream|"
        r"live and free|stream(?:ed|ing)? live and free|grátis|gratuito|gratuitamente|de graça|"
        r"transmissão gratuita|acesso gratuito|gratis en directo|kostenlos live",
        value,
    ):
        return "free"
    return "unknown"


def detect_platform(text: str) -> str:
    value = text.lower()
    patterns = [
        (r"youtube", "YouTube"), (r"twitch", "Twitch"),
        (r"fiawec\+", "FIAWEC+"), (r"rally\.tv", "Rally.TV"),
        (r"motogp videopass|videopass", "MotoGP VideoPass"),
        (r"worldsbk videopass", "WorldSBK VideoPass"),
        (r"f1 tv", "F1 TV"), (r"dazn", "DAZN"),
        (r"flo?racing", "FloRacing"), (r"peacock", "Peacock"),
        (r"nhra\.tv|nhra tv", "NHRA.tv"), (r"smx video ?pass|supermotocross video pass", "SMX Video Pass"),
        (r"joyn", "Joyn"), (r"servustv", "ServusTV On"),
        (r"band ?play", "BandPlay"), (r"bandsports", "BandSports"),
        (r"sportv", "SporTV"), (r"globoplay", "Globoplay"),
        (r"imsa\.com/tvlive|imsa tv", "IMSA TV"),
        (r"ind(y|i)car live", "INDYCAR LIVE"),
        (r"fim-moto\.tv", "FIM-MOTO.TV"),
        (r"superview", "SuperView"), (r"kayo sports", "Kayo Sports"),
    ]
    for pattern, name in patterns:
        if re.search(pattern, value):
            return name
    return "Não identificada"


def detect_series(text: str) -> str:
    value = text.lower()
    mapping = [
        (r"formula ?1|\bf1\b", "Fórmula 1"),
        (r"formula ?2|\bf2\b", "Fórmula 2"),
        (r"formula ?3|\bf3\b", "Fórmula 3"),
        (r"formula ?e", "Fórmula E"),
        (r"formula ?4|\bf4\b|formula regional|regional formula", "Fórmulas de base"),
        (r"formula student|formula sae", "Formula Student / SAE"),
        (r"fia world endurance championship|\bfia wec\b|\bwec\b", "FIA WEC"),
        (r"motogp|moto gp|moto2|moto3", "MotoGP / Moto2 / Moto3"),
        (r"worldsbk|world superbike|\bwsbk\b", "WorldSBK"),
        (r"mxgp|motocross|supercross|supermotocross|\bsmx\b", "Motocross / Supercross"),
        (r"hard enduro|enduro motorcycle|enduro world", "Enduro / Hard Enduro"),
        (r"speedway|long track|ice speedway", "Speedway"),
        (r"wec|world endurance|elms|imsa|24 hours of le mans|24h le mans", "Endurance / Protótipos"),
        (r"gt world|gt3|gt4|gt world challenge|british gt|gt open", "GT / GT3 / GT4"),
        (r"dtm|tcr|btcc|touring car|touring cars", "Turismo / TCR"),
        (r"nascar|stock car|supercars championship|v8 supercars", "Stock Car / NASCAR"),
        (r"indycar|indy 500|indy nxt", "IndyCar"),
        (r"kart|karting|kartódromo|kartodromo", "Karting"),
        (r"rallycross|world rx|world rallycross|rally cross", "Rallycross"),
        (r"rally raid|dakar|baja|cross.country rally", "Rally Raid / Baja"),
        (r"rally|wrc|erc|rallye", "Rally"),
        (r"drag racing|dragster|nhra|arrancada|drag strip", "Arrancada / Drag"),
        (r"hill ?climb|hillclimb|bergrennen|subida de montanha", "Hillclimb / Subida de montanha"),
        (r"drift|formula drift", "Drift"),
        (r"autocross|autocrossing", "Autocross"),
        (r"sprint car|midget|dirt late model|short.track racing|oval racing", "Ovais / Sprint Cars / Midgets"),
        (r"time attack|time trial", "Time Attack"),
        (r"ice racing|ice racing car|snowmobile racing", "Gelo / Neve"),
        (r"off.road|cross.country|trial(s)?", "Off-road / Trials"),
        (r"club racing|grassroots racing|amateur racing", "Club / Regional"),
    ]
    for pattern, name in mapping:
        if re.search(pattern, value):
            return name
    return "Motorsport — categoria a identificar"


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
    """Escolhe a edição do Google News a partir de país/idioma mencionado."""
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
        # Não basta a notícia ter sido retornada por uma busca com "rally":
        # validamos título e resumo para evitar comícios e política.
        if not is_motorsport_result(title, description):
            continue
        key = hashlib.sha256(link.encode("utf-8")).hexdigest()[:18]
        full_text = f"{title} {description}"
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
            "is_verified_stream": False,
            "note": "Pista encontrada em notícia. Abra a fonte para confirmar data, região, plataforma e acesso.",
        }
    ordered = sorted(results.values(), key=lambda item: item.get("published") or "", reverse=True)
    return ordered[:limit]


def buscar_pistas(limit: int = 60) -> list[dict]:
    """Faz uma varredura ampla, isolando falhas de cada família de modalidade."""
    fetched: list[bytes] = []
    with ThreadPoolExecutor(max_workers=min(8, len(QUERIES))) as pool:
        futures = [pool.submit(_fetch_query, query) for query in QUERIES]
        for future in as_completed(futures):
            try:
                fetched.append(future.result())
            except (HTTPError, URLError, TimeoutError, OSError):
                continue

    if not fetched:
        raise OSError("Não foi possível consultar o RSS de notícias. Verifique a conexão com a internet.")

    merged: dict[str, dict] = {}
    for payload in fetched:
        try:
            for item in _parse_feed(payload, limit=limit):
                merged[item["id"]] = item
        except ElementTree.ParseError:
            continue
    ordered = sorted(merged.values(), key=lambda item: item.get("published") or "", reverse=True)
    return ordered[:limit]


def buscar_pistas_personalizadas(query: str, limit: int = 25) -> list[dict]:
    """Busca uma categoria/campeonato/região digitado pelo usuário no RSS."""
    clean = re.sub(r"\s+", " ", (query or "")).strip()[:180]
    if len(clean) < 2:
        raise ValueError("Digite pelo menos 2 caracteres para pesquisar.")
    payload = _fetch_query(f'({clean}) {LIVE_TERMS}')
    try:
        results = _parse_feed(payload, limit=max(1, min(limit, 40)))
    except ElementTree.ParseError as exc:
        raise OSError("A fonte de notícias retornou um feed inválido.") from exc
    # Marca a busca customizada na explicação sem sugerir validação oficial.
    for item in results:
        item["note"] = "Resultado de busca personalizada no Google News. É uma pista editorial, não uma live verificada. Confirme a fonte original."
    return results
