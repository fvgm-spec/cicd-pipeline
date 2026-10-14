#!/usr/bin/env python3
import argparse
import json
import re
import unicodedata
import sys
from datetime import datetime, timezone
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE_URL = "https://www.espn.com.uy/futbol/resultados/_/fecha/{date}"
STATE_MARKER = "window['__espnfitt__']="
DISPLAY_TIMEZONE = ZoneInfo("Europe/Madrid")


def normalize_date(value):
    if value is None:
        return datetime.now().strftime("%Y%m%d")

    value = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            pass

    raise argparse.ArgumentTypeError("date must be YYYYMMDD or YYYY-MM-DD")


def fetch_html(date):
    url = BASE_URL.format(date=date)
    request = Request(
        url,
        headers={
            "User-Agent": "espn-results-cli/0.1 (+local personal script)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8"), url
    except HTTPError as exc:
        raise RuntimeError(f"ESPN returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not fetch {url}: {exc.reason}") from exc


def extract_state(html):
    start = html.find(STATE_MARKER)
    if start == -1:
        raise RuntimeError("Could not find ESPN app state in the page HTML")

    start += len(STATE_MARKER)
    end = html.find(";</script>", start)
    if end == -1:
        raise RuntimeError("Could not find the end of ESPN app state")

    raw = unescape(html[start:end])
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse ESPN app state as JSON: {exc}") from exc


def get_scoreboard(state):
    try:
        return state["page"]["content"]["scoreboard"]
    except KeyError as exc:
        raise RuntimeError("Could not find scoreboard data in ESPN app state") from exc


def parse_score(value):
    if value is None:
        return ""
    return str(value)


def normalize_text(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def league_title(league):
    return league.get("moduleHeader") or (league.get("league") or {}).get("name") or "Unknown league"


def league_matches(league, query):
    if not query:
        return True

    league_data = league.get("league") or {}
    haystack = " ".join(
        normalize_text(str(value))
        for value in [
            league_title(league),
            league_data.get("name"),
            league_data.get("abbrev"),
            league_data.get("slug"),
        ]
        if value
    )
    words = normalize_text(query).split()
    return all(word in haystack for word in words)


def format_kickoff_time(event):
    raw_date = event.get("date")
    if not raw_date:
        return event.get("time") or "Time TBD"

    try:
        kickoff = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except ValueError:
        return event.get("time") or raw_date

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    local = kickoff.astimezone(DISPLAY_TIMEZONE)
    return f"{local.strftime('%I:%M %p').lstrip('0')} {local.tzname()}"


def venue_line(event):
    venue = event.get("vnue") or event.get("venue") or {}
    address = venue.get("address") or {}
    parts = [venue.get("fullName"), address.get("city"), address.get("country")]
    parts = [part for part in parts if part]
    return " | ".join(parts) if parts else "Venue TBD"


def event_line(event):
    teams = event.get("competitors") or event.get("teams") or []
    away = next((team for team in teams if not team.get("isHome")), teams[0] if teams else {})
    home = next((team for team in teams if team.get("isHome")), teams[1] if len(teams) > 1 else {})

    away_name = away.get("displayName") or away.get("shortDisplayName") or "TBD"
    home_name = home.get("displayName") or home.get("shortDisplayName") or "TBD"
    away_score = parse_score(away.get("score"))
    home_score = parse_score(home.get("score"))

    status = event.get("status") or {}
    description = status.get("description") or status.get("detail") or ""
    time = format_kickoff_time(event)
    note = event.get("note")

    if away_score or home_score:
        matchup = f"{away_name} {away_score} - {home_score} {home_name}"
    else:
        matchup = f"{away_name} @ {home_name}"

    details = [venue_line(event)]
    if description:
        details.append(description)
    if note:
        details.append(note)

    detail_text = " | ".join(details)
    return f"{time:>8}  {matchup}  [{detail_text}]"


def print_scoreboard(scoreboard, date, source_url, league_filter=None):
    all_leagues = scoreboard.get("gmsByLeague") or []
    if not all_leagues:
        print(f"No soccer games found for {date}.")
        return

    leagues = [league for league in all_leagues if league_matches(league, league_filter)]
    if not leagues:
        print(f"No leagues matched {league_filter!r} for {date}.")
        print()
        print("Available leagues:")
        for league in all_leagues:
            print(f"- {league_title(league)}")
        print()
        print(f"Want to browse the full board? ESPN has it here: {source_url}")
        return

    heading = f"ESPN Uruguay soccer results for {date}"
    if league_filter:
        heading += f" - filtered by league: {league_filter}"
    print(heading)
    print(source_url)
    print()

    total_events = 0
    for league in leagues:
        events = league.get("evts") or []
        if not events:
            continue

        total_events += len(events)
        title = league.get("moduleHeader") or (league.get("league") or {}).get("name") or "Unknown league"
        print(title)
        print("-" * len(title))
        for event in events:
            print(event_line(event))
        print()

    print(f"{len(leagues)} leagues, {total_events} events")
    if not league_filter:
        print()
        print("League filters you can use with -l:")
        for league in leagues:
            print(f"- {league_title(league)}")
    print()
    print(f"Want the full match center view? Review the day on ESPN: {source_url}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Show ESPN Uruguay soccer results/fixtures for a given day."
    )
    parser.add_argument(
        "date",
        nargs="?",
        type=normalize_date,
        default=normalize_date(None),
        help="Date to fetch, as YYYYMMDD or YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "-l",
        "--league",
        help="Only show leagues matching this text, for example: premier league, carabao cup, liga europa uefa.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        html, source_url = fetch_html(args.date)
        state = extract_state(html)
        scoreboard = get_scoreboard(state)
        print_scoreboard(scoreboard, args.date, source_url, args.league)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
