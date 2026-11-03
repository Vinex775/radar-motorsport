# APEX Motorsport Radar

**An open-source discovery radar for motorsport events and places to watch them — from local karting and club racing to Formula 1, endurance, rally, drifting, drag racing, and motorcycle racing.**

APEX is a discovery aggregator. It points users to calendars, news, channels, and official watch pages. It does not host or rebroadcast video, bypass paywalls, or circumvent regional restrictions.

> **Important:** APEX separates **Live Now** results from **Discovery Leads**. A search result, news article, or scheduled session window is never proof that a video is live. Historical articles are retained as research clues, not displayed as current broadcasts.

## Features

- DTM schedule collector, isolated so a source failure does not stop the rest of the radar.
- Broad discovery searches across formula racing, karting, rally and rally raid, GT/endurance, touring cars, stock cars, motorcycles, motocross, drag racing, drifting, hillclimb, speedway, oval racing, and regional series.
- Custom search for any championship, country, circuit, or obscure series using Google News RSS, with regional editions selected where possible.
- Search shortcuts for 25+ motorsport families and regions.
- Dedicated **Live Now** scan using the YouTube Data API `eventType=live` filter when configured.
- Broad motorsport live-search terms covering racing, karting, rally, endurance, GT, touring cars, drift, drag racing, hillclimb, speedway, motocross, and motorcycle racing.
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

## YouTube Live API (optional)

To list videos that YouTube currently marks as live, create an API key in the [Google Cloud Console](https://console.cloud.google.com/) and enable the YouTube Data API v3. Set the `YOUTUBE_API_KEY` environment variable before starting APEX.

PowerShell example:

```powershell
$env:YOUTUBE_API_KEY = "YOUR_API_KEY"
py main.py
```

The key is read from the environment and is not stored in source code or SQLite. **Never commit API keys, tokens, cookies, or `.env` files.** Without a key, the Live Now button opens YouTube's public Live-filtered search instead. Those public results are not API-verified inside APEX.

YouTube's `eventType=live` is evidence that YouTube classifies a video as live; it does not prove that the channel is official, that the video contains the race feed rather than reaction/commentary, or that access is unrestricted in every country.

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
- `collectors/`: schedule, news discovery, and YouTube collectors
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
- DTM is the only structured automatic schedule collector in this release. Other series are discovered through news, YouTube, official directories, or manual entry.
- Google News RSS discovers articles and announcements; it does not inspect a video player or guarantee a current live feed.
- Only videos returned by YouTube with `eventType=live` are labelled as currently live by the YouTube API collector. APEX still cannot guarantee that the video is the official race feed.
- A schedule window means only that the published session time overlaps the current time; it is not a live-video verification.
- A truly exhaustive worldwide scan across every streaming platform is not technically possible with one public API. Additional platform integrations and regional/community collectors are needed for broader coverage.
- Broadcast rights change by country, season, event, and session. Official links can change without notice.
- The DTM collector uses an undocumented public endpoint and may need maintenance if the provider changes it.

## Disclaimer

APEX is an independent community project and is not affiliated with, sponsored by, or endorsed by the FIA, FIM, Formula 1, Dorna, NASCAR, IMSA, SRO, NHRA, or any listed championship or platform. Trademarks, broadcasts, videos, calendars, and third-party content remain the property of their respective owners. APEX links users to external sources and does not copy or distribute broadcasts.

## License

The source code is available under the MIT License. See [LICENSE](LICENSE). This does not grant rights to third-party trademarks, broadcasts, videos, calendars, or content.
