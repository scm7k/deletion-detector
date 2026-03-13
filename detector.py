#!/usr/bin/env python3
"""
Deletion Detector — Corporate Activity Monitor

Monitors public data sources for coordinated LinkedIn profile scrubbing
patterns that precede major corporate announcements (M&A, layoffs, reorgs).

Academic basis: executives and key employees systematically update or
sanitize their LinkedIn profiles before material non-public events.
Coordinated profile changes across departments create statistical
anomalies in platform-level metrics 24-72 hours before announcements.

Usage:
    python detector.py --demo              # Run with simulated data
    python detector.py --monitor URL       # Monitor a real data source
    python detector.py --analyze FILE      # Analyze a saved dataset

Requires: Python 3.10+, requests (for live monitoring only)
"""

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────

@dataclass
class DeletionEvent:
    """A single observed deletion or profile change."""
    timestamp: str
    source: str
    event_type: str  # "account_deletion", "bio_scrub", "post_purge", "photo_removal"
    magnitude: int   # number of items affected (posts deleted, etc.)
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class DeletionIndex:
    """Composite score representing coordinated deletion activity."""
    timestamp: str
    score: float          # 0.0 to 1.0
    baseline: float       # rolling average
    deviation: float      # standard deviations from baseline
    event_count: int      # events in window
    window_hours: int     # observation window
    alert_level: str      # "normal", "elevated", "high", "critical"
    contributing_events: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        d["contributing_events"] = [e if isinstance(e, dict) else asdict(e)
                                    for e in self.contributing_events]
        return d


# ─────────────────────────────────────────────────────────────────────
# Deletion Index Calculator
# ─────────────────────────────────────────────────────────────────────

class DeletionIndexCalculator:
    """
    Computes a deletion index from a stream of deletion events.

    The index measures how far current deletion activity deviates from
    a rolling baseline. Coordinated pre-announcement scrubbing produces
    a characteristic signature: a sharp increase in profile changes
    across multiple employee categories within a compressed timeframe.
    """

    ALERT_THRESHOLDS = {
        "normal": 1.0,
        "elevated": 2.0,
        "high": 3.0,
        "critical": 4.0,
    }

    EVENT_WEIGHTS = {
        "account_deletion": 1.0,
        "bio_scrub": 0.4,
        "post_purge": 0.7,
        "photo_removal": 0.5,
    }

    def __init__(self, baseline_window_hours: int = 168, scoring_window_hours: int = 6):
        self.baseline_window = baseline_window_hours  # 7 days default
        self.scoring_window = scoring_window_hours
        self.events: list[DeletionEvent] = []
        self.history: list[DeletionIndex] = []

    def add_event(self, event: DeletionEvent):
        self.events.append(event)

    def add_events(self, events: list[DeletionEvent]):
        self.events.extend(events)

    def _parse_ts(self, ts: str) -> datetime.datetime:
        return datetime.datetime.fromisoformat(ts)

    def _events_in_window(self, center: datetime.datetime,
                          window_hours: int) -> list[DeletionEvent]:
        start = center - datetime.timedelta(hours=window_hours)
        return [e for e in self.events
                if start <= self._parse_ts(e.timestamp) <= center]

    def _weighted_count(self, events: list[DeletionEvent]) -> float:
        total = 0.0
        for e in events:
            weight = self.EVENT_WEIGHTS.get(e.event_type, 0.3)
            total += weight * math.log1p(e.magnitude)
        return total

    def compute(self, at_time: Optional[str] = None) -> DeletionIndex:
        if at_time:
            now = self._parse_ts(at_time)
        else:
            now = datetime.datetime.now(datetime.timezone.utc)

        # Current window
        current_events = self._events_in_window(now, self.scoring_window)
        current_score = self._weighted_count(current_events)

        # Baseline: compute hourly scores over the baseline window
        hourly_scores = []
        for h in range(self.baseline_window):
            t = now - datetime.timedelta(hours=h)
            window_events = self._events_in_window(t, self.scoring_window)
            hourly_scores.append(self._weighted_count(window_events))

        if len(hourly_scores) > 1:
            baseline = statistics.mean(hourly_scores)
            stdev = statistics.stdev(hourly_scores) if len(hourly_scores) > 2 else 1.0
        else:
            baseline = current_score
            stdev = 1.0

        if stdev == 0:
            stdev = 0.01

        deviation = (current_score - baseline) / stdev

        # Normalize score to 0-1
        score = min(1.0, max(0.0, 0.5 + (deviation / 10.0)))

        # Alert level
        alert = "normal"
        for level, threshold in sorted(self.ALERT_THRESHOLDS.items(),
                                        key=lambda x: x[1], reverse=True):
            if deviation >= threshold:
                alert = level
                break

        idx = DeletionIndex(
            timestamp=now.isoformat(),
            score=round(score, 4),
            baseline=round(baseline, 4),
            deviation=round(deviation, 2),
            event_count=len(current_events),
            window_hours=self.scoring_window,
            alert_level=alert,
            contributing_events=current_events[-10:],  # last 10
        )

        self.history.append(idx)
        return idx


# ─────────────────────────────────────────────────────────────────────
# Demo Mode — Simulated Data
# ─────────────────────────────────────────────────────────────────────

class DemoSimulator:
    """
    Simulates coordinated LinkedIn profile scrubbing before a corporate
    announcement (M&A, layoffs, restructuring).

    The simulation generates two weeks of baseline profile change activity,
    then introduces a 48-hour pre-announcement window where scrubbing rates
    spike across employee categories — executives and HR first, then
    engineering and sales as word spreads internally.
    """

    ACCOUNT_CATEGORIES = [
        "executive",
        "engineering",
        "hr_recruiting",
        "sales",
        "general",
    ]

    # Baseline profile change rates per hour per category
    BASELINE_RATES = {
        "executive": 0.8,
        "engineering": 2.1,
        "hr_recruiting": 1.4,
        "sales": 1.6,
        "general": 45.0,
    }

    # Multiplier during pre-announcement scrubbing
    SPIKE_MULTIPLIERS = {
        "executive": 6.0,
        "hr_recruiting": 5.0,
        "engineering": 4.2,
        "sales": 2.8,
        "general": 1.0,  # no change
    }

    EVENT_TYPES = ["account_deletion", "bio_scrub", "post_purge", "photo_removal"]
    EVENT_TYPE_WEIGHTS = [0.10, 0.35, 0.30, 0.25]

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def generate(self, days: int = 14, spike_start_day: int = 12,
                 spike_duration_hours: int = 48) -> list[DeletionEvent]:
        """Generate simulated profile change events over a time period."""
        events = []
        start = datetime.datetime(2028, 3, 10, 0, 0, 0,
                                  tzinfo=datetime.timezone.utc)
        spike_begin = start + datetime.timedelta(days=spike_start_day)
        spike_end = spike_begin + datetime.timedelta(hours=spike_duration_hours)

        total_hours = days * 24
        for hour in range(total_hours):
            current_time = start + datetime.timedelta(hours=hour)

            for category in self.ACCOUNT_CATEGORIES:
                base_rate = self.BASELINE_RATES[category]

                # Business hours pattern (higher 9-6, lower nights/weekends)
                hour_of_day = current_time.hour
                day_of_week = current_time.weekday()
                is_weekend = day_of_week >= 5

                if is_weekend:
                    time_factor = 0.15
                elif 9 <= hour_of_day <= 18:
                    time_factor = 0.4 + 0.6 * math.sin(
                        math.pi * (hour_of_day - 9) / 9
                    )
                else:
                    time_factor = 0.2

                rate = base_rate * time_factor

                # Apply spike multiplier if in the pre-announcement window
                if spike_begin <= current_time < spike_end:
                    # Ramp up over first 6 hours, sustain, ramp down last 6
                    hours_in = (current_time - spike_begin).total_seconds() / 3600
                    hours_left = (spike_end - current_time).total_seconds() / 3600

                    if hours_in < 6:
                        ramp = hours_in / 6.0
                    elif hours_left < 6:
                        ramp = hours_left / 6.0
                    else:
                        ramp = 1.0

                    multiplier = 1.0 + (self.SPIKE_MULTIPLIERS[category] - 1.0) * ramp
                    rate *= multiplier

                # Generate events (Poisson process)
                n_events = self.rng.poisson(rate) if hasattr(self.rng, 'poisson') else max(0, int(self.rng.gauss(rate, math.sqrt(rate))))

                for _ in range(n_events):
                    # Random minute within the hour
                    minute = self.rng.randint(0, 59)
                    second = self.rng.randint(0, 59)
                    ts = current_time.replace(minute=minute, second=second)

                    event_type = self.rng.choices(
                        self.EVENT_TYPES, weights=self.EVENT_TYPE_WEIGHTS, k=1
                    )[0]

                    # Magnitude: how many items affected
                    if event_type == "account_deletion":
                        magnitude = 1
                    elif event_type == "post_purge":
                        magnitude = self.rng.randint(5, 200)
                    elif event_type == "photo_removal":
                        magnitude = self.rng.randint(1, 50)
                    else:
                        magnitude = 1

                    events.append(DeletionEvent(
                        timestamp=ts.isoformat(),
                        source="simulated",
                        event_type=event_type,
                        magnitude=magnitude,
                        metadata={"category": category},
                    ))

        events.sort(key=lambda e: e.timestamp)
        return events


# ─────────────────────────────────────────────────────────────────────
# Live Monitor (placeholder for real data sources)
# ─────────────────────────────────────────────────────────────────────

class LiveMonitor:
    """
    Monitors a public data source for deletion events.

    Supported sources:
    - Wayback Machine CDX API (track page disappearances)
    - Custom webhook endpoint
    - CSV file (for replay)

    For ethical and legal reasons, this tool does not scrape individual
    profiles. It works with aggregate, publicly available metadata.
    """

    def __init__(self, source_url: str):
        self.source_url = source_url
        self.calculator = DeletionIndexCalculator()

    def poll_wayback(self) -> list[DeletionEvent]:
        """Query the Wayback Machine CDX API for URL disappearances."""
        try:
            import requests
        except ImportError:
            print("ERROR: requests library required for live monitoring.")
            print("Install with: pip install requests")
            sys.exit(1)

        # CDX API: check for URLs that were previously archived but now return 404
        cdx_url = f"https://web.archive.org/cdx/search/cdx?url={self.source_url}&output=json&limit=100&fl=timestamp,statuscode,original"

        try:
            resp = requests.get(cdx_url, timeout=30)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            print(f"WARNING: Could not reach Wayback CDX API: {e}")
            return []

        if len(rows) < 2:
            return []

        events = []
        headers = rows[0]
        for row in rows[1:]:
            record = dict(zip(headers, row))
            if record.get("statuscode") in ("404", "410"):
                events.append(DeletionEvent(
                    timestamp=datetime.datetime.strptime(
                        record["timestamp"], "%Y%m%d%H%M%S"
                    ).replace(tzinfo=datetime.timezone.utc).isoformat(),
                    source="wayback_cdx",
                    event_type="account_deletion",
                    magnitude=1,
                    metadata={"url": record.get("original", "")},
                ))

        return events

    def run(self, interval_seconds: int = 300, max_iterations: int = 0):
        """Poll the source at regular intervals and compute deletion index."""
        iteration = 0
        print(f"\n  DELETION DETECTOR — Live Monitor")
        print(f"  Source: {self.source_url}")
        print(f"  Polling interval: {interval_seconds}s")
        print(f"  {'─' * 50}\n")

        while True:
            events = self.poll_wayback()
            self.calculator.add_events(events)
            idx = self.calculator.compute()
            _print_index(idx)

            iteration += 1
            if max_iterations and iteration >= max_iterations:
                break

            time.sleep(interval_seconds)


# ─────────────────────────────────────────────────────────────────────
# Output formatting
# ─────────────────────────────────────────────────────────────────────

ALERT_COLORS = {
    "normal": "\033[32m",    # green
    "elevated": "\033[33m",  # yellow
    "high": "\033[91m",      # light red
    "critical": "\033[31m",  # red
}
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"


def _bar(value: float, width: int = 40) -> str:
    filled = int(value * width)
    return "█" * filled + "░" * (width - filled)


def _print_index(idx: DeletionIndex, use_color: bool = True):
    c = ALERT_COLORS.get(idx.alert_level, "") if use_color else ""
    r = RESET if use_color else ""
    d = DIM if use_color else ""
    b = BOLD if use_color else ""
    cy = CYAN if use_color else ""

    print(f"  {d}{idx.timestamp}{r}")
    print(f"  {b}DELETION INDEX: {c}{idx.score:.4f}{r}  [{_bar(idx.score)}]")
    print(f"  Alert: {c}{idx.alert_level.upper()}{r}  |  "
          f"Deviation: {idx.deviation:+.2f}σ  |  "
          f"Events: {idx.event_count} ({idx.window_hours}h window)")
    print(f"  {d}Baseline: {idx.baseline:.4f}{r}")
    print()


def _print_timeline(history: list[DeletionIndex], use_color: bool = True):
    """Print a compact timeline of deletion index values."""
    b = BOLD if use_color else ""
    r = RESET if use_color else ""
    d = DIM if use_color else ""
    cy = CYAN if use_color else ""

    print(f"\n  {b}{'─' * 60}")
    print(f"  DELETION INDEX TIMELINE")
    print(f"  {'─' * 60}{r}\n")

    max_score = max(h.score for h in history) if history else 1.0

    for h in history:
        ts = h.timestamp[:16]  # truncate to minutes
        bar_width = int((h.score / max(max_score, 0.01)) * 40)
        c = ALERT_COLORS.get(h.alert_level, "") if use_color else ""

        level_marker = {
            "normal": " ",
            "elevated": "▪",
            "high": "▪▪",
            "critical": "▪▪▪",
        }.get(h.alert_level, " ")

        print(f"  {d}{ts}{r}  {c}{'█' * bar_width}{r:<40s}  "
              f"{h.score:.3f}  {c}{level_marker}{r}")

    print()


def _print_category_breakdown(events: list[DeletionEvent],
                               use_color: bool = True):
    """Show deletion counts by employee category."""
    b = BOLD if use_color else ""
    r = RESET if use_color else ""
    d = DIM if use_color else ""

    categories = {}
    for e in events:
        cat = e.metadata.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"count": 0, "magnitude": 0}
        categories[cat]["count"] += 1
        categories[cat]["magnitude"] += e.magnitude

    print(f"\n  {b}{'─' * 60}")
    print(f"  CATEGORY BREAKDOWN")
    print(f"  {'─' * 60}{r}\n")

    total_count = sum(c["count"] for c in categories.values())
    for cat, data in sorted(categories.items(),
                            key=lambda x: x[1]["count"], reverse=True):
        pct = data["count"] / total_count * 100 if total_count else 0
        bar_width = int(pct / 2.5)
        print(f"  {cat:<25s}  {data['count']:>5d} events  "
              f"{'█' * bar_width} {pct:.1f}%")

    print()


# ─────────────────────────────────────────────────────────────────────
# File I/O
# ─────────────────────────────────────────────────────────────────────

def save_events(events: list[DeletionEvent], path: str):
    with open(path, "w") as f:
        json.dump([e.to_dict() for e in events], f, indent=2)
    print(f"  Saved {len(events)} events to {path}")


def load_events(path: str) -> list[DeletionEvent]:
    with open(path) as f:
        data = json.load(f)
    return [DeletionEvent(**d) for d in data]


def save_report(history: list[DeletionIndex], path: str):
    with open(path, "w") as f:
        json.dump([h.to_dict() for h in history], f, indent=2)
    print(f"  Saved {len(history)} index readings to {path}")


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def run_demo(args):
    print(f"\n  {BOLD}{'═' * 60}")
    print(f"  DELETION DETECTOR — Demo Mode")
    print(f"  {'═' * 60}{RESET}\n")
    print(f"  Simulating 14 days of LinkedIn profile change activity.")
    print(f"  Pre-announcement scrubbing begins day 12, lasting 48 hours.\n")
    print(f"  {DIM}This demonstrates the pattern described in PARALLAX:")
    print(f"  employees scrubbing LinkedIn profiles before major corporate")
    print(f"  announcements creates a detectable signal in aggregate data.{RESET}\n")

    sim = DemoSimulator(seed=args.seed if hasattr(args, "seed") else 42)
    events = sim.generate(
        days=14,
        spike_start_day=12,
        spike_duration_hours=48,
    )

    print(f"  Generated {len(events)} simulated profile change events.\n")

    # Filter to employee-category events only (this is what an analyst would do)
    employee_categories = {"executive", "engineering", "hr_recruiting", "sales"}
    emp_events = [e for e in events if e.metadata.get("category") in employee_categories]

    print(f"  Filtering to employee accounts ({len(emp_events)} of {len(events)} events).\n")

    calc = DeletionIndexCalculator(
        baseline_window_hours=168,
        scoring_window_hours=6,
    )
    calc.add_events(emp_events)

    start = datetime.datetime(2028, 3, 10, 0, 0, 0,
                              tzinfo=datetime.timezone.utc)

    # Sample every 6 hours (start at day 7 so baseline is established)
    for hour in range(7 * 24, 14 * 24, 6):
        t = start + datetime.timedelta(hours=hour)
        calc.compute(at_time=t.isoformat())

    # Print timeline
    _print_timeline(calc.history)

    # Print the peak readings
    print(f"  {BOLD}Peak Readings:{RESET}\n")
    peak_readings = sorted(calc.history, key=lambda h: h.score, reverse=True)[:5]
    for idx in peak_readings:
        _print_index(idx)

    # Category breakdown during spike window
    spike_start = start + datetime.timedelta(days=12)
    spike_end = spike_start + datetime.timedelta(hours=48)
    spike_events = [e for e in events
                    if spike_start.isoformat() <= e.timestamp <= spike_end.isoformat()]
    _print_category_breakdown(spike_events)

    # Per-category comparison: baseline vs pre-announcement window
    baseline_end = spike_start
    baseline_start = baseline_end - datetime.timedelta(days=2)
    baseline_events = [e for e in events
                       if baseline_start.isoformat() <= e.timestamp <= baseline_end.isoformat()]

    baseline_cats = {}
    spike_cats = {}
    for e in baseline_events:
        cat = e.metadata.get("category", "unknown")
        baseline_cats[cat] = baseline_cats.get(cat, 0) + 1
    for e in spike_events:
        cat = e.metadata.get("category", "unknown")
        spike_cats[cat] = spike_cats.get(cat, 0) + 1

    print(f"\n  {BOLD}{'─' * 60}")
    print(f"  PRE-ANNOUNCEMENT SIGNAL: BASELINE vs SCRUBBING WINDOW")
    print(f"  {'─' * 60}{RESET}\n")
    print(f"  {'Category':<25s}  {'Baseline':>8s}  {'Spike':>8s}  {'Change':>8s}")
    print(f"  {'─' * 55}")
    for cat in ["executive", "hr_recruiting", "engineering", "sales", "general"]:
        b = baseline_cats.get(cat, 0)
        o = spike_cats.get(cat, 0)
        if b > 0:
            change = (o - b) / b * 100
            c = ALERT_COLORS["critical"] if change > 100 else ALERT_COLORS["high"] if change > 50 else ""
            print(f"  {cat:<25s}  {b:>8d}  {o:>8d}  {c}{change:>+7.0f}%{RESET}")
        else:
            print(f"  {cat:<25s}  {b:>8d}  {o:>8d}       N/A")
    print()

    # Save data if requested
    if hasattr(args, "output") and args.output:
        save_events(events, args.output)

    print(f"  {DIM}The deletion index is a fictional concept from PARALLAX by scm7k.")
    print(f"  The underlying principle is real: coordinated behavioral changes")
    print(f"  in aggregate data can signal impending corporate events.{RESET}\n")


def run_analyze(args):
    print(f"\n  {BOLD}DELETION DETECTOR — Analysis Mode{RESET}\n")

    events = load_events(args.file)
    print(f"  Loaded {len(events)} events from {args.file}\n")

    calc = DeletionIndexCalculator(
        baseline_window_hours=168,
        scoring_window_hours=6,
    )
    calc.add_events(events)

    # Find time range
    timestamps = [e.timestamp for e in events]
    start = min(timestamps)
    end = max(timestamps)
    start_dt = datetime.datetime.fromisoformat(start)
    end_dt = datetime.datetime.fromisoformat(end)

    # Compute at 6-hour intervals
    t = start_dt
    while t <= end_dt:
        calc.compute(at_time=t.isoformat())
        t += datetime.timedelta(hours=6)

    _print_timeline(calc.history)

    # Category breakdown
    _print_category_breakdown(events)

    if hasattr(args, "output") and args.output:
        save_report(calc.history, args.output)


def run_monitor(args):
    monitor = LiveMonitor(args.url)
    monitor.run(
        interval_seconds=args.interval if hasattr(args, "interval") else 300,
        max_iterations=args.max_polls if hasattr(args, "max_polls") else 0,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Deletion Detector: Corporate Activity Monitor",
        epilog="Inspired by a concept in PARALLAX by scm7k. "
               "https://github.com/scm7k/parallax",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Demo
    demo_parser = subparsers.add_parser("demo", help="Run with simulated data")
    demo_parser.add_argument("--seed", type=int, default=42,
                             help="Random seed for reproducibility")
    demo_parser.add_argument("--output", "-o", type=str,
                             help="Save events to JSON file")

    # Analyze
    analyze_parser = subparsers.add_parser("analyze",
                                           help="Analyze a saved dataset")
    analyze_parser.add_argument("file", type=str, help="JSON file of events")
    analyze_parser.add_argument("--output", "-o", type=str,
                                help="Save report to JSON file")

    # Monitor
    monitor_parser = subparsers.add_parser("monitor",
                                           help="Monitor a live data source")
    monitor_parser.add_argument("url", type=str, help="URL to monitor")
    monitor_parser.add_argument("--interval", type=int, default=300,
                                help="Polling interval in seconds")
    monitor_parser.add_argument("--max-polls", type=int, default=0,
                                help="Max polling iterations (0 = infinite)")

    # Also support --demo flag at top level for convenience
    parser.add_argument("--demo", action="store_true",
                        help="Run demo mode (shortcut)")

    args = parser.parse_args()

    if args.demo or args.command == "demo":
        run_demo(args)
    elif args.command == "analyze":
        run_analyze(args)
    elif args.command == "monitor":
        run_monitor(args)
    else:
        parser.print_help()
        print(f"\n  Try: python {sys.argv[0]} demo")
        print(f"       python {sys.argv[0]} --demo\n")


if __name__ == "__main__":
    main()
