# Deletion Detector

A tool for monitoring coordinated LinkedIn profile scrubbing patterns that precede major corporate announcements.

## The Concept

When companies prepare for major announcements — acquisitions, layoffs, restructuring — insiders clean up their digital footprints. Executives update LinkedIn headlines. HR recruiters remove job postings. Engineers scrub project descriptions. Individually, one person updating their bio is invisible. In aggregate, across hundreds of employees, the scrubbing rate creates a statistical anomaly that precedes public announcements by 24-72 hours.

This tool monitors public data sources for these coordinated scrubbing signatures and computes a "deletion index" that quantifies the deviation from baseline activity.

### How It Works

The same principle applies wherever coordinated behavioral changes precede an event: employees know before the market does, and their LinkedIn activity reflects it. The categories that move first (executives, HR) and last (general staff) create a characteristic cascade.

- Executive profile updates (title changes, bio rewrites) spike 6x baseline
- HR/recruiting activity spikes 5x (job posting removals, description changes)
- Engineering profiles follow at 4x (project descriptions, skill endorsements)
- Sales accounts show moderate increase at 2.8x
- General employee population shows no change (they don't know yet)

## Usage

### Demo Mode

Run with simulated data showing the pre-announcement scrubbing pattern:

```bash
python detector.py demo
python detector.py --demo
```

The demo generates 14 days of baseline LinkedIn profile change activity across five employee categories (executive, engineering, HR/recruiting, sales, general), then introduces a 48-hour pre-announcement window where insider scrubbing rates spike.

### Analyze Saved Data

```bash
python detector.py demo --output events.json
python detector.py analyze events.json --output report.json
```

### Live Monitoring

Monitor a URL via the Wayback Machine CDX API for page disappearances:

```bash
python detector.py monitor "example.com/profiles/*" --interval 300
```

## How the Index Works

The deletion index is computed as follows:

1. **Event collection**: Profile change events are categorized by type (account deletion, bio scrub, post purge, photo removal) and weighted by significance.
2. **Baseline**: A 7-day rolling average establishes normal change rates.
3. **Scoring window**: The current 6-hour window is compared against the baseline.
4. **Deviation**: Standard deviations from baseline determine the alert level.

| Alert Level | Deviation | Meaning |
|-------------|-----------|---------|
| NORMAL | < 1.0 sigma | Within expected variation |
| ELEVATED | 1.0 - 2.0 sigma | Mild increase, possibly organic |
| HIGH | 2.0 - 3.0 sigma | Significant increase, warrants attention |
| CRITICAL | > 3.0 sigma | Coordinated pattern detected |

## Output

```
2028-03-22T06:00:00+00:00
DELETION INDEX: 0.7842  [████████████████████████████████░░░░░░░░]
Alert: HIGH  |  Deviation: +3.14σ  |  Events: 847 (6h window)
Baseline: 312.4100
```

## Interactive Version

Open `index.html` in a browser for an animated visualization of the detection algorithm. The HTML version simulates the same statistical model with a real-time timeline, alert panel, and per-category breakdown.

## Requirements

- Python 3.10+
- `requests` (only for live monitoring mode)
- No other dependencies

## Ethics

This tool works with aggregate, publicly available metadata. It does not scrape individual profiles. The demonstrated patterns are statistical, not personal. The tool is designed for researchers studying publicly observable behavioral signals in corporate activity.

## Origin

This concept is explored in the novel [PARALLAX](https://scm7k.com) by scm7k, where characters describe how coordinated deletion patterns in social media accounts created detectable signals preceding major events. The deletion detector is one component of a broader system for reading the gap between what exists and what has been removed.

- [Read Chapter 1](https://scm7k.com/read)
- [The Deletion Signal (essay)](https://scm7k.com/essay_deletion)
- [GitHub](https://github.com/scm7k/parallax)

## License

MIT

