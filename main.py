#!/usr/bin/env python3
"""gta6-twitch-ccu-forecast-01 entry: forecast GTA VI's launch-day Twitch
viewers, hour by hour, as five quantiles per hour.

Method (chosen by leave-one-out backtest on the 37 comparable launches in
the practice data, scored with the contest's own mean log pinball loss):

  * Every past launch in the case's `comparables` gives a release-day
    shape: the log-ratio r_c(h) = log viewers(h) - log viewers(1) of its
    UTC release day, hours 2..24 against its own hour 1.
  * Launches do not transfer equally: a launch's shape predicts best the
    launches of similar scale. Each comparable is weighted by a Laplace
    kernel on its hour-1 size, w = exp(-|log v1_c - log v1| / 0.9).
  * The forecast for hour h is the case's hour-1 print times exp of the
    weighted empirical quantiles of {r_c(h)} at the five scored levels.

Backtest (leave-one-out, 37 launches): this scores 0.206 mean log pinball
against 0.465 for the house persistence baseline shipped as the starter -
the shape of a launch day, borrowed from launches of the same size, beats
"tomorrow looks like hour 1" by more than a factor of two. Variants tried
and rejected on the same backtest: unweighted ratios (0.357), shrinkage
toward persistence, spread rescaling, platform/unlock-similarity weights,
a channels kernel, interpolated weighted quantiles.

Any hour with no usable comparable falls back to the house baseline's
persistence spread, so the output is always complete and valid.

Runs in the grader as `python3 -P -s /bot/main.py` (Python 3.13, standard
library only, no network), one case file at a time in the input dir.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
BANDWIDTH = 0.9  # Laplace kernel width on log hour-1 size (backtest-tuned)
BASELINE_SIGMA = 0.15  # house baseline spread, used only as a fallback


def parse_ts(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    ).timestamp()


def day_curve(comparable):
    """Release-day hourly viewers of one comparable: {hour 1..24: viewers}."""
    start = parse_ts(comparable["day_start"])
    curve = {}
    for point in comparable["hourly"]:
        offset = parse_ts(point["from"]) - start
        if 0 <= offset < 24 * 3600:
            curve[int(offset // 3600) + 1] = point["viewers"]
    return curve


def weighted_quantile(pairs, tau):
    """Smallest value whose cumulative weight reaches tau of the total."""
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    acc = 0.0
    for value, weight in sorted(pairs):
        acc += weight
        if acc / total >= tau:
            return value
    return pairs[-1][0]


def round2(x):
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    log_p1 = math.log(p1)

    # Weighted log-ratio samples per forecast hour, from every comparable
    # whose own release day has an hour-1 print.
    per_hour = {row["hour"]: [] for row in case["forecast"]}
    for comparable in case["comparables"]:
        curve = day_curve(comparable)
        c1 = curve.get(1)
        if not c1 or c1 <= 0:
            continue
        weight = math.exp(-abs(math.log(c1) - log_p1) / BANDWIDTH)
        if weight <= 1e-6:
            continue
        log_c1 = math.log(c1)
        for hour, samples in per_hour.items():
            vh = curve.get(hour)
            if vh and vh > 0:
                samples.append((math.log(vh) - log_c1, weight))

    rows = []
    for row in case["forecast"]:
        hour = row["hour"]
        samples = per_hour[hour]
        quantiles = []
        for tau, z in zip(LEVELS, Z):
            ratio = weighted_quantile(samples, tau) if samples else None
            if ratio is None:
                ratio = z * BASELINE_SIGMA * math.sqrt(hour - 1)
            quantiles.append(p1 * math.exp(ratio))
        # Order, clamp to the contest's bounds, and round like the starter.
        quantiles = [min(max(q, 1e-6), 1e9) for q in sorted(quantiles)]
        rounded = []
        for q in quantiles:
            v = round2(q)
            if rounded and v < rounded[-1]:
                v = rounded[-1]
            rounded.append(v)
        rows.append({"hour": hour, "q": rounded})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
