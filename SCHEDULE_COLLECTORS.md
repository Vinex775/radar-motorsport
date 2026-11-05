# APEX schedule collector registry

APEX now has two independent schedule ingestion sources:

- `collectors/calendario_dtm.py`: the existing DTM page/API collector.
- `collectors/official_schedule.py`: imports checked event records from `data/official_schedule.json`.

The registry is a **curated official-source feed**, not a universal scraper. Championship websites publish calendars in different formats and some use dynamic pages or undocumented APIs. APEX records event dates only when an official championship, venue, or organizer page supports them. This approach makes the first expanded Schedule useful immediately while dedicated page/API collectors are added and tested series by series.

## Adding an event

Add an object to the `events` array in `data/official_schedule.json`. Required fields:

- `external_id`: stable unique ID; do not reuse it for a different session.
- `name`, `series`, `category`, and `kind`.
- `start`: ISO-8601 timestamp with an explicit timezone offset, such as `2026-11-06T12:30:00-03:00`.
- `source_url`: official event, championship, venue, or organizer page.
- `confidence`: `official` or `regional`.

Recommended fields are `end`, `region`, `platform`, `access`, `watch_url`, and `source_name`. Use `access: "unknown"` unless the rights-holder explicitly documents the access terms.

If the organizer has announced the dates but has not published session times, use a multi-day date range and set `kind` to `Race weekend — session times TBC`. Store a neutral midday timestamp solely to preserve the local calendar dates; the dashboard recognizes the TBC marker, displays only the date range, keeps the event visible through its final date, and does not create a start-time notification. Never invent a session start time.

## Current registry coverage

The initial registry contains the 2026 São Paulo GP support-series and F1 timetable, the 2026 Bahrain WEC round, the Qatar MotoGP weekend, the Sandown 500 Supercars sessions, the NASCAR Craftsman Truck event at Homestead, the World of Outlaws World Finals program, remaining 2026 F1 weekends, and all nine announced 2027 WEC rounds.

These are event-schedule records, not confirmation that a video stream is active. The Live Now tab remains independent and uses only YouTube, Twitch, and Kick platform APIs.

## Future collector contributions

Prefer official JSON/ICS/API data when available. For HTML pages, write a series-specific parser instead of a brittle global scraper. Each collector must:

1. Fail independently so a source outage cannot stop other collectors.
2. Preserve source URLs and explicit timezone offsets.
3. Avoid placeholder session times.
4. Use stable external IDs and support updates to existing events.
5. Include parser and date-boundary tests.
