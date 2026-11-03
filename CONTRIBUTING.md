# Contributing to APEX

Thanks for helping people discover more motorsport around the world!

## What we need

- Official calendars and verifiable broadcast sources.
- Coverage of local karting, regional categories, national championships, and obscure disciplines.
- Corrections to dates, platforms, access labels, and territorial restrictions.
- Accessibility, usability, testing, and documentation improvements.

## Source and collector guidelines

1. Prefer official championship, federation, circuit, and platform pages.
2. Include the source URL and the date it was checked.
3. Record country/region and season whenever possible.
4. Use `unknown` when price or territorial rights are not confirmed.
5. Never label a race as live solely because its scheduled session window is active.
6. Distinguish the actual race feed from reaction/commentary, live blogs, and text updates.
7. Do not copy videos, logos, protected content, or login data.
8. Do not bypass paywalls, DRM, geoblocks, or access controls.
9. Use timeouts, an identifiable User-Agent, and explicit error handling.
10. Isolate collector failures so one source cannot take down the radar.
11. Never invent times. If the source publishes only the event date, leave the time unknown.
12. Filter stale event guides and political uses of ambiguous terms such as “rally.”

## Local development

```bash
python -m unittest discover -s tests -v
python main.py
```

The project uses the Python standard library. Do not include the local SQLite database in pull requests.

## Pull requests

- Explain the issue and the proposed change.
- Add tests for new or corrected logic.
- Keep all user-facing interface text and project documentation in English.
- Keep discovery multilingual; English UI does not mean English-only search.
- Update the README when adding features, environment variables, or sources.
- Never include API keys, tokens, cookies, local databases, or personal files.
