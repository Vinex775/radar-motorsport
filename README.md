# APEX Motorsport Radar

**An open-source discovery radar for motorsport events and places to watch them — from local karting and club racing to Formula 1, endurance, rally, drifting, drag racing, and motorcycle racing.**

APEX is a discovery aggregator. It points users to calendars, news, channels, and official watch pages. It does not host or rebroadcast video, bypass paywalls, or circumvent regional restrictions.

> **Important:** APEX separates **Live Now** results from **Discovery Leads**. A search result, news article, or scheduled session window is never proof that a video is live. Historical articles are retained as research clues, not displayed as current broadcasts.

## Features

- DTM schedule collector, isolated so a source failure does not stop the rest of the radar.
- Broad discovery searches across formula racing, karting, rally and rally raid, GT/endurance, touring cars, stock cars, motorcycles, motocross, drag racing, drifting, hillclimb, speedway, oval racing, and regional series.
- Custom search for any championship, country, circuit, or obscure series using Google News RSS, with regional editions selected where possible.
- Search shortcuts for 25+ motorsport families and regions.
- Dedicated **Live Now** scan across YouTube, Twitch, and Kick APIs; all configured providers are queried concurrently.
- Broad multilingual motorsport live-search terms covering major series and grassroots disciplines such as autosuunnistus, folkrace, rallisprint, autoslalom, tractor pulling, and short-track racing.
- Historical broadcast references are retained and labelled; old articles are never presented as proof of a current live stream.
- Reaction/watch-along results are filtered from race-feed candidates.
- Official watch-source directory.
- Access labels: **Free**, **Subscription**, **Pay-per-view**, and **Unknown**.
- Manual event entry for series without a collector.
- Browser notifications for upcoming events while the dashboard remains open.
- Local SQLite storage; no account or external database required.
- MIT-licensed code and GitHub Actions tests.

## Requirements

- Python 3.10 or newer
- Internet access for online discovery
- No required third-party Python packages

## Run locally

### Windows

1. Extract the repository.
2. Double-click `iniciar_radar.bat`. It checks for Python 3.10 or newer.
3. If Python is missing, the launcher asks for your permission (Y/N) before attempting to install Python 3.14 through WinGet. WinGet may display its own package/source agreement or Windows permission prompt. If WinGet is unavailable, the launcher opens the official Python downloads page. No installation is started without your confirmation.
4. You can also run the commands below in PowerShell from the project directory.

```powershell
py main.py
```

If `py` is unavailable, use `python main.py`.

Open <http://127.0.0.1:5000> in your browser. Press `Ctrl+C` in the terminal to stop the server.

### macOS / Linux

```bash
python3 main.py
```

Then open <http://127.0.0.1:5000>.

## Discover broadcasts

1. Open **Discover**.
2. Enter a category, championship, circuit, country, or regional series — for example `Swedish club karting`, `Finnish rallycross`, or `Brazil hillclimb`.
3. Optionally add a region to narrow the search.
4. Select **Search APEX** to find recent news and announcements.
5. Open the original source and confirm the event date, session, platform, territory, and access conditions.

APEX searches in multiple languages, but no search engine indexes every local club, federation, or broadcast. Some events will be missed; some results will require manual verification.

## Live platform connectors (optional)

The **Live Now** scanner queries platform APIs for broadcasts that are active at scan time. It does not use calendars, news articles, or future sessions as evidence that a stream is live.

APEX currently supports three API-backed connectors:

- **YouTube:** `search.list` with `eventType=live`, followed by `videos.list` to enrich results with start time and concurrent viewers when available.
- **Twitch:** category discovery plus Helix `Get Streams`, which returns active streams for those categories.
- **Kick:** the public API's active livestream endpoint, filtered to motorsport-related categories.

The connectors are independent. Configure one, two, or all three; an unavailable provider does not stop the others.

### Configure credentials

1. Copy `.env.example` to `.env` in the APEX root folder.
2. Add credentials for the providers you want to use.
3. Save the file and restart APEX.

**YouTube**

Create an API key in the [Google Cloud Console](https://console.cloud.google.com/) and enable [YouTube Data API v3](https://developers.google.com/youtube/v3). Add it as `YOUTUBE_API_KEY`.

**Twitch**

Create an application in the [Twitch Developer Console](https://dev.twitch.tv/console/apps) and add its Client ID and Client Secret as `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET`. APEX uses the app access-token flow for public stream/category data.

**Kick**

Create an application in the [Kick Developer Portal](https://dev.kick.com) and add its Client ID and Client Secret as `KICK_CLIENT_ID` and `KICK_CLIENT_SECRET`. Kick requires an app access token for public API data.

Example `.env`:

```dotenv
YOUTUBE_API_KEY=your_youtube_key
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
KICK_CLIENT_ID=your_kick_client_id
KICK_CLIENT_SECRET=your_kick_client_secret
```

The `.env` file is ignored by Git. **Never commit real API keys, client secrets, access tokens, cookies, or local databases.**

### Scan frequency and API limits

- APEX checks Twitch and Kick every 5 minutes while the dashboard is open. The provider calls run concurrently, so one slow platform does not hold up the others.
- YouTube results are cached for 20 minutes. YouTube's `search.list` method has a default limit of 100 calls per day, so APEX uses one broad multilingual OR query per cache interval instead of spending quota on dozens of separate searches.
- A manual scan uses the same cache windows; it does not bypass provider limits.

YouTube documents `eventType=live` as returning active broadcasts only. Twitch documents `Get Streams` as returning channels that are currently broadcasting. Kick's v2 livestream endpoint is documented as returning active livestreams. These signals confirm that the platform reports a channel as live; they do **not** prove that the stream is the official race feed, nor do they establish price or regional rights.

Official API references:

- [YouTube Search: list](https://developers.google.com/youtube/data/reference/rest/v3/search/list)
- [YouTube quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- [Twitch API Reference — Get Streams / Search Categories](https://dev.twitch.tv/docs/api/reference)
- [Kick API — Livestreams](https://github.com/KickEngineering/KickDevDocs/blob/main/apis/livestreams.md)
- [Kick OAuth 2.1 — App Access Token](https://github.com/KickEngineering/KickDevDocs/blob/main/getting-started/generating-tokens-oauth2-flow.md)

Without API credentials, APEX can still open public platform searches, but those results are not independently verified by APEX and are not counted as Live Now.

## How access labels work

- **Free:** a source explicitly states that the relevant event or feed is free.
- **Subscription:** a source explicitly states that a subscription or paid pass is required.
- **Pay-per-view:** a source explicitly states that the individual event must be purchased.
- **Unknown:** price, region, session, or access conditions are unclear.

Access is specific to the **series + platform + region + season + session**. A feed can be free in one country and paid in another. APEX must not infer that a broadcast is free merely because it is on YouTube or because an article uses the word “free” in another context.

## Discovery quality and false positives

Search engines may confuse motorsport “rally” with political rallies, surface reaction streams as if they were race feeds, or return articles about events that have already ended. APEX rejects political noise and obvious reaction/watch-along pages. Old watch guides are retained as **Historical references** because they can reveal obscure series and local broadcasters. They are not treated as Live Now results. These filters reduce false positives but cannot eliminate them all.

Please report false positives with the source URL, result title, and why it is misleading. Do not report a result as verified merely because its title says “LIVE.”

## Project layout

- `main.py`: local application entry point
- `app.py`: HTTP server and API routes
- `radar.py`: collector orchestration and dashboard data
- `db.py`: local SQLite persistence
- `collectors/`: schedule/news discovery plus YouTube, Twitch, and Kick live connectors
- `data/search_presets.json`: discovery shortcuts
- `data/watch_sources.json`: official watch-source directory
- `templates/index.html`: dashboard markup
- `static/app.css`: styles
- `static/app.js`: dashboard behavior
- `tests/`: unit tests

## Contribute a source or collector

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Official championship, federation, circuit, and broadcaster pages are preferred. Include the source URL, region, season, date checked, and evidence for any access claim. Use `unknown` when price or territorial rights cannot be verified.

Do not invent session times. If a source publishes only an event date, keep the time unknown. New collectors should fail independently and include tests for parsing and date handling.

Run tests with:

```bash
python -m unittest discover -s tests -v
```

## Security and privacy

APEX is intended for local use at `127.0.0.1`. It has no multi-user authentication, authorization, CSRF protection, HTTPS, or rate limiting. Do not expose the development server directly to the public internet without adding appropriate security controls.

Do not commit API keys, tokens, cookies, personal data, or local database files. See [SECURITY.md](SECURITY.md).

## Current limitations

- There is no single public API containing every motorsport event and worldwide broadcast right.
- DTM is currently the only structured automatic schedule collector. Other series are discovered through live platform APIs, news, official directories, or manual entry.
- Google News RSS discovers articles and announcements; it does not inspect a video player or guarantee a current live feed.
- Only platform API results that explicitly identify a current broadcast are labelled Live Now. APEX still cannot guarantee that the video is the official race feed.
- A schedule window means only that the published session time overlaps the current time; it is not a live-video verification.
- A truly exhaustive worldwide scan across every streaming platform is not technically possible with the current public APIs. Twitch discovery depends on platform categories, Kick discovery is capped at ten API pages per scan, and YouTube search is constrained by its daily quota and indexing. Regional/community collectors and user-submitted sources are still needed for broader coverage.
- Broadcast rights change by country, season, event, and session. Official links can change without notice.
- The DTM collector uses an undocumented public endpoint and may need maintenance if the provider changes it.

## Disclaimer

APEX is an independent community project and is not affiliated with, sponsored by, or endorsed by the FIA, FIM, Formula 1, Dorna, NASCAR, IMSA, SRO, NHRA, or any listed championship or platform. Trademarks, broadcasts, videos, calendars, and third-party content remain the property of their respective owners. APEX links users to external sources and does not copy or distribute broadcasts.

## License

The source code is available under the MIT License. See [LICENSE](LICENSE). This does not grant rights to third-party trademarks, broadcasts, videos, calendars, or content.
