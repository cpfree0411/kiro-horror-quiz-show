#!/usr/bin/env python3
"""Summarize the public demo's owner-only JSONL visit log."""

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
VID = re.compile(r"[0-9a-f]{12}")
COUNTRY = re.compile(r"[A-Z]{2}|T1")
DEVICES = ("bot", "desktop", "mobile", "tablet", "other")
EVENT_FIELDS = {
    "stage_view": (), "ticket_view": (), "phone_view": (),
    "stage_open": ("role",), "stage_close": ("role", "secs"),
    "join": ("players", "via"), "start": ("players",), "act": ("act",), "end": ("players", "secs"),
    "restart": ("by", "phase", "players"), "auto_reset": ("reason", "phase", "players"), "new_show": (),
}


def read_events(log, since, excluded):
    for line in log:
        try:
            event = json.loads(line)
            vid, kind, dev, cc = (event[key] for key in ("vid", "ev", "dev", "cc"))
            if not VID.fullmatch(vid) or vid in excluded or kind not in EVENT_FIELDS or dev not in DEVICES:
                continue
            if cc is not None and not COUNTRY.fullmatch(cc):
                continue
            stamp = datetime.fromisoformat(event["t"])
            if stamp.tzinfo is None:
                continue
            stamp = stamp.astimezone(KST)
        except (ValueError, TypeError, KeyError, OverflowError):
            continue  # e.g. a truncated final line after a storage error
        if since is None or stamp.date() >= since:
            yield stamp, event


@dataclass
class Counts:
    visitors: set = field(default_factory=set)
    bots: set = field(default_factory=set)
    events: Counter = field(default_factory=Counter)
    bot_events: int = 0
    highest_act: int = 0

    def add(self, event):
        if event["dev"] == "bot":
            self.bots.add(event["vid"])
            self.bot_events += 1
            return
        self.visitors.add(event["vid"])
        kind = event["ev"]
        self.events[kind] += 1
        act = event.get("act")
        if kind == "act" and type(act) is int:
            self.highest_act = max(self.highest_act, act)

    def __str__(self):
        return (f"visitors={len(self.visitors)} stage_views={self.events['stage_view']} "
                f"ticket_views={self.events['ticket_view']} joins={self.events['join']} "
                f"started={self.events['start']} highest_act={self.highest_act} finished={self.events['end']} "
                f"restarts={self.events['restart']} auto_resets={self.events['auto_reset']} "
                f"bot_visitors={len(self.bots)} bot_events={self.bot_events}")


def summary(events):
    days = defaultdict(Counts)
    total = Counts()
    countries = defaultdict(set)
    for stamp, event in events:
        days[stamp.date()].add(event)
        total.add(event)
        if event["dev"] != "bot":
            countries[event["cc"] or "unknown"].add(event["vid"])
    print("Daily (KST)")
    for day, counts in sorted(days.items()):
        print(day, counts)
    print("Total", total)
    print("Countries (unique non-bot IDs)")
    for country, vids in sorted(countries.items()):
        print(country, len(vids))


def timeline(events):
    print("Timeline (KST)")
    for stamp, event in sorted(events, key=lambda row: (row[1]["vid"], row[0])):
        kind = event["ev"]
        fields = (f"{key}={json.dumps(event[key])}" for key in ("cc", "dev", *EVENT_FIELDS[kind]) if key in event)
        print(event["vid"], stamp.isoformat(timespec="seconds"), kind, *fields)


def kst_date(value):
    try:
        day = date.fromisoformat(value)
        if day.isoformat() == value:
            return day
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("use YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--since", type=kst_date, help="include this date and later (KST)")
    parser.add_argument("--exclude-vid", nargs="+", action="extend", default=[], metavar="VID")
    parser.add_argument("--timeline", action="store_true", help="show each visitor's events in chronological order")
    args = parser.parse_args()
    try:
        with args.log.open(encoding="utf-8", errors="replace") as log:
            events = read_events(log, args.since, {vid.lower() for vid in args.exclude_vid})
            (timeline if args.timeline else summary)(events)
    except OSError as error:
        parser.exit(1, f"{parser.prog}: cannot read visit log ({error.strerror})\n")


if __name__ == "__main__":
    main()
