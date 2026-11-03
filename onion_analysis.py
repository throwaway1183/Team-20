"""Team 20: Wet rainfall versus onion-price spikes, all districts.

Wet week: rainfall > same ISO-week mean (other years) + 2 sample SD.
Price spike: >= threshold rise in any of the following 1..N price weeks.
Normal-group events are protected by a two-week wet-rainfall lookback.

NEW: report two-sided Wald confidence intervals for p_wet - p_normal.
This is a simple school project; the CI assumes independent observations,
which overlapping weekly windows and districts may violate.
"""

import argparse
from base64 import b64encode
from datetime import datetime
from html import escape
import os
import json
import math
import re
from pathlib import Path
from statistics import NormalDist
from urllib.request import urlopen

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
PRICE_FILE = ROOT / "data/prices/onion_prices.csv"
RAIN_FOLDER = ROOT / "data/rainfall/data"
LOCATION_URL = (
    "https://raw.githubusercontent.com/open-admin-data/"
    "india-administrative-divisions/master/data/all-district.json"
)
MIN_REFERENCE_YEARS = 4
WET_SD_MULTIPLIER = 2.0
MIN_DAILY_RAIN_OBSERVATIONS = 5


def clean_name(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def grid_key(latitude, longitude):
    """Round to the nearest 0.25-degree rainfall-grid cell."""
    return int(round(float(latitude) * 4)) * 1000 + int(round(float(longitude) * 4))


def read_prices(path):
    """Return all district names and district -> weekly median onion prices."""
    if not path.is_file():
        raise ValueError(f"Price CSV not found: {path}")
    columns = ["State/UT", "District", "Modal Price", "Price Date"]
    chunks = []
    places = set()
    for chunk in pd.read_csv(path, usecols=columns, dtype=str, chunksize=150_000):
        chunk = chunk.dropna(subset=["State/UT", "District"]).copy()
        chunk["State/UT"] = chunk["State/UT"].str.strip()
        chunk["District"] = chunk["District"].str.strip()
        chunk = chunk[(chunk["State/UT"] != "") & (chunk["District"] != "")]
        places.update(zip(chunk["State/UT"], chunk["District"]))
        # "1,537.00" -> 1537; date "31-12-2021" -> 2021-12-31.
        chunk["price"] = pd.to_numeric(
            chunk["Modal Price"].str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )
        chunk["date"] = pd.to_datetime(
            chunk["Price Date"].str.strip(), format="%d-%m-%Y", errors="coerce"
        )
        chunk = chunk.dropna(subset=["date", "price"])
        chunk = chunk[chunk["price"] > 0]
        chunks.append(chunk[["State/UT", "District", "date", "price"]])

    if not places or not chunks or not any(len(chunk) for chunk in chunks):
        raise ValueError("No valid district onion-price records in the CSV")
    data = pd.concat(chunks, ignore_index=True)
    daily = data.groupby(["State/UT", "District", "date"])["price"].median().reset_index()
    daily["week"] = daily["date"].dt.to_period("W-SUN")
    weekly = daily.groupby(["State/UT", "District", "week"])["price"].median()
    by_district = {
        (state, district): group.droplevel([0, 1]).sort_index()
        for (state, district), group in weekly.groupby(level=[0, 1])
    }
    return sorted(places), by_district


def read_locations(custom_path, cache_path):
    """Use a user-provided CSV, cached coordinates, or a one-time download."""
    lookup = {}
    if custom_path is not None:
        if not custom_path.is_file():
            raise ValueError(f"Location CSV not found: {custom_path}")
        custom = pd.read_csv(custom_path)
        state_col = "State/UT" if "State/UT" in custom.columns else "State"
        for column in [state_col, "District", "Latitude", "Longitude"]:
            if column not in custom.columns:
                raise ValueError(f"Location CSV needs column {column}")
        for row in custom.to_dict("records"):
            try:
                lat, lon = float(row["Latitude"]), float(row["Longitude"])
                if not (6 <= lat <= 38 and 67 <= lon <= 98):
                    continue
                lookup[(clean_name(row[state_col]), clean_name(row["District"]))] = (
                    lat, lon, "custom CSV"
                )
            except (ValueError, TypeError):
                continue

    # No internet is necessary when the user supplies all coordinates.
    if not cache_path.is_file() and custom_path is None:
        try:
            print("Downloading district coordinates (first run only)...", flush=True)
            with urlopen(LOCATION_URL, timeout=25) as response:
                raw = response.read()
            rows = json.loads(raw)
            if not isinstance(rows, list) or len(rows) < 100:
                raise ValueError("Reference location data is incomplete")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw)
        except (OSError, ValueError, TimeoutError) as error:
            print(f"Location download unavailable: {error}")
            print("Supply --locations district_locations.csv if districts do not match.")

    if cache_path.is_file():
        try:
            rows = json.loads(cache_path.read_text(encoding="utf-8"))
            for row in rows:
                try:
                    state = row["parent"]["name"]["en"]
                    district = row["name"]["en"]
                    lat, lon = float(row["geo"]["lat"]), float(row["geo"]["lon"])
                    if 6 <= lat <= 38 and 67 <= lon <= 98:
                        lookup.setdefault((clean_name(state), clean_name(district)),
                                          (lat, lon, "district reference"))
                except (KeyError, TypeError, ValueError):
                    continue
        except (OSError, ValueError, TypeError) as error:
            print(f"Warning: invalid district-coordinate cache: {error}")
    return lookup


def read_rainfall(folder, keys):
    """Aggregate daily grid rainfall into Monday-Sunday weekly totals in chunks."""
    files = [folder] if folder.is_file() else sorted(folder.glob("RF25_ind*_rfp25.csv"))
    if not files:
        raise ValueError(f"No matching rainfall CSV files in {folder}")
    if not keys:
        return {}
    totals = []
    for file in files:
        print(f"Reading rainfall: {file.name}", flush=True)
        for chunk in pd.read_csv(
            file,
            usecols=["LONGITUDE", "LATITUDE", "TIME", "RAINFALL"],
            dtype={"LONGITUDE": "float32", "LATITUDE": "float32", "RAINFALL": "float32"},
            chunksize=250_000, na_values=["NA", ""],
        ):
            computed = (chunk["LATITUDE"] * 4).round() * 1000 + (
                chunk["LONGITUDE"] * 4
            ).round()
            selected = chunk.loc[
                computed.isin(keys) & (chunk["RAINFALL"] >= 0), ["TIME", "RAINFALL"]
            ].copy()
            if selected.empty:
                continue
            selected["grid"] = computed.loc[selected.index].astype(int).values
            selected["week"] = pd.to_datetime(
                selected["TIME"], format="%Y-%m-%d", errors="coerce"
            ).dt.to_period("W-SUN")
            selected = selected.dropna(subset=["week"])
            if not selected.empty:
                totals.append(selected.groupby(["grid", "week"])["RAINFALL"].agg(["sum", "count"]))
    if not totals:
        return {}
    weekly = pd.concat(totals).groupby(level=[0, 1]).sum()
    weekly.loc[weekly["count"] < MIN_DAILY_RAIN_OBSERVATIONS, "sum"] = float("nan")
    return {
        int(key): group.droplevel(0).sort_index()
        for key, group in weekly["sum"].groupby(level=0)
    }


def classify_rainfall(weekly_rain):
    """Wet if weekly rainfall > mean + 2 sample SD of same ISO week in other years."""
    weather = pd.Series("unclassified", index=weekly_rain.index, dtype="object")
    means = pd.Series(float("nan"), index=weekly_rain.index, dtype="float64")
    deviations = pd.Series(float("nan"), index=weekly_rain.index, dtype="float64")
    counts = pd.Series(0, index=weekly_rain.index, dtype="int64")
    iso_weeks = pd.Series(
        [week.start_time.isocalendar().week for week in weekly_rain.index],
        index=weekly_rain.index,
    )
    for week, rainfall in weekly_rain.dropna().items():
        other_years = weekly_rain[
            (weekly_rain.index != week) & (iso_weeks == iso_weeks.loc[week])
        ].dropna()
        if len(other_years) < MIN_REFERENCE_YEARS:
            continue
        mean = float(other_years.mean())
        sd = float(other_years.std(ddof=1))
        means.loc[week], deviations.loc[week], counts.loc[week] = mean, sd, len(other_years)
        weather.loc[week] = "wet" if rainfall > mean + WET_SD_MULTIPLIER * sd else "normal"
    return weather, means, deviations, counts


def recent_rainfall(weather, week, lookback):
    """Are all previous lookback weeks known non-wet?"""
    conditions = [weather.get(week - n, "unclassified") for n in range(1, lookback + 1)]
    if "wet" in conditions:
        return "wet"
    if any(condition != "normal" for condition in conditions):
        return "unknown"
    return "clear"


def compare(prices, rain, threshold=20, weeks=4, lookback=2):
    """Make one observed success or failure per rainfall week, if eligible."""
    weather, means, stds, counts = classify_rainfall(rain)
    rows = []
    for week, rain_mm in rain.sort_index().items():
        condition = weather.get(week, "unclassified")
        baseline = prices.get(week, float("nan"))
        next_prices = [prices.get(week + lag, float("nan")) for lag in range(1, weeks + 1)]
        complete = bool(
            pd.notna(baseline) and baseline > 0
            and all(pd.notna(price) and price > 0 for price in next_prices)
        )
        increases = [
            100 * (float(price) / float(baseline) - 1)
            if pd.notna(price) and price > 0 and pd.notna(baseline) and baseline > 0
            else float("nan")
            for price in next_prices
        ]
        candidates = [
            lag for lag, change in enumerate(increases, 1)
            if pd.notna(change) and change >= threshold - 1e-9
        ]
        previous = recent_rainfall(weather, week, lookback)
        candidate_history = {
            lag: recent_rainfall(weather, week + lag, lookback) for lag in candidates
        }
        status, success, first_lag = "eligible", pd.NA, pd.NA
        if condition == "unclassified":
            status = "unclassified_rainfall"
        elif not complete:
            status = "incomplete_price_window"
        elif condition == "wet":
            success = bool(candidates)
            if success:
                first_lag = candidates[0]
        elif previous == "wet":
            status = "excluded_recent_wet_before_normal_week"
        elif previous == "unknown":
            status = "excluded_missing_lookback_rainfall"
        elif not candidates:
            success = False
        else:
            clean = [lag for lag in candidates if candidate_history[lag] == "clear"]
            if clean:
                success, first_lag = True, clean[0]
            elif "wet" in candidate_history.values():
                status = "excluded_wet_before_price_spike"
            else:
                status = "excluded_missing_lookback_rainfall"
        row = {
            "rain_week_start": week.start_time.strftime("%Y-%m-%d"),
            "rain_week_end": week.end_time.normalize().strftime("%Y-%m-%d"),
            "rain_condition": condition,
            "rainfall_mm": rain_mm,
            "reference_mean_mm": means.get(week),
            "reference_std_mm": stds.get(week),
            "wet_cutoff_mm": means.get(week) + 2 * stds.get(week),
            "reference_years": counts.get(week),
            "baseline_price": baseline,
            "price_window_weeks": weeks,
            "complete_price_window": complete,
            "normal_reference_previous_weeks": previous,
            "price_spike_candidates": ",".join(map(str, candidates)),
            "normal_candidate_previous_weeks": ",".join(
                f"{lag}:{candidate_history[lag]}" for lag in candidates
            ),
            "eligibility": status,
            "spike_found": success,
            "first_spike_lag_weeks": first_lag,
            "max_price_rise_pct": max(increases) if complete else float("nan"),
        }
        for lag, (price, change) in enumerate(zip(next_prices, increases), 1):
            row[f"week_{lag}_price"] = price
            row[f"week_{lag}_rise_pct"] = change
        rows.append(row)
    events = pd.DataFrame(rows)
    if events.empty:
        return events, events
    return events, events[events["eligibility"] == "eligible"].copy()


def confidence_interval(wet_n, wet_success, normal_n, normal_success, confidence=95.0):
    """Two-sided Wald CI for p_wet - p_normal, as specified in the project."""
    result = {
        "wet_rate_pct": float("nan"),
        "normal_rate_pct": float("nan"),
        "difference_pct_points": float("nan"),
        "standard_error": float("nan"),
        "z_critical": NormalDist().inv_cdf(0.5 + (confidence / 100) / 2),
        "ci_lower_pct_points": float("nan"),
        "ci_upper_pct_points": float("nan"),
        "confidence_pct": float(confidence),
        "conclusion": "Insufficient data (one rainfall group is empty)",
        "ci_warning": "",
    }
    if wet_n <= 0 or normal_n <= 0:
        return result
    p_wet, p_normal = wet_success / wet_n, normal_success / normal_n
    difference = p_wet - p_normal
    se = math.sqrt(p_wet * (1 - p_wet) / wet_n + p_normal * (1 - p_normal) / normal_n)
    z = NormalDist().inv_cdf(0.5 + (confidence / 100) / 2)
    low, high = difference - z * se, difference + z * se

    if low > 0:
        conclusion = "Reject H0; observed CI supports H1 (wet > normal)"
    elif high < 0:
        conclusion = "Reject equality in opposite direction; H1 not supported"
    else:
        conclusion = "Fail to reject H0; H1 not supported (CI includes 0)"

    if min(wet_success, wet_n - wet_success, normal_success, normal_n - normal_success) < 5:
        warning = "Wald interval may be unreliable: fewer than 5 successes or failures in a group."
    else:
        warning = ""
    result.update({
        "wet_rate_pct": p_wet * 100,
        "normal_rate_pct": p_normal * 100,
        "difference_pct_points": difference * 100,
        "standard_error": se,
        "ci_lower_pct_points": low * 100,
        "ci_upper_pct_points": high * 100,
        "conclusion": conclusion,
        "ci_warning": warning,
    })
    return result


def save_plots(districts, output, threshold, weeks, confidence):
    available = districts.dropna(subset=["ci_lower_pct_points", "ci_upper_pct_points"]).copy()
    available["total"] = available["wet_weeks"] + available["normal_weeks"]
    available = available.sort_values("total", ascending=False).head(20)
    fig, ax = plt.subplots(figsize=(11, max(5, 0.38 * len(available) + 1)))
    if available.empty:
        ax.text(0.5, 0.5, "No districts with both eligible groups", ha="center", va="center")
        ax.axis("off")
    else:
        y = list(range(len(available)))
        names = [f"{row['District']} ({row['State/UT']})" for _, row in available.iterrows()]
        ax.barh([n - 0.19 for n in y], available["normal_rate_pct"], 0.37, label="Normal")
        ax.barh([n + 0.19 for n in y], available["wet_rate_pct"], 0.37, label="Wet")
        ax.set_yticks(y, names)
        ax.invert_yaxis()
        ax.set_xlabel(f"Proportion with ≥{threshold:g}% price spike in next {weeks} weeks (%)")
        ax.legend()
        ax.grid(axis="x", alpha=0.2)
    ax.set_title("Observed spike rates: wet vs normal rainfall")
    fig.tight_layout()
    fig.savefig(output / "district_comparison.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, max(5, 0.38 * len(available) + 1)))
    if available.empty:
        ax.text(0.5, 0.5, "No confidence intervals available", ha="center", va="center")
        ax.axis("off")
    else:
        y = list(range(len(available)))
        centers = available["difference_pct_points"].to_numpy()
        lower = available["ci_lower_pct_points"].to_numpy()
        upper = available["ci_upper_pct_points"].to_numpy()
        err = [centers - lower, upper - centers]
        names = [f"{row['District']} ({row['State/UT']})" for _, row in available.iterrows()]
        ax.errorbar(centers, y, xerr=err, fmt="o", capsize=3)
        ax.set_yticks(y, names)
        ax.invert_yaxis()
        ax.axvline(0, color="darkred", linestyle="--", linewidth=1)
        ax.set_xlabel("Wet minus normal proportion (percentage points)")
        ax.grid(axis="x", alpha=0.2)
    ax.set_title(f"{confidence:g}% confidence intervals for spike-rate differences")
    fig.tight_layout()
    fig.savefig(output / "district_confidence_intervals.png", dpi=140)
    plt.close(fig)


def save_html_report(districts, overall, wet_n, wet_success, normal_n, normal_success,
                     args, matched_count):
    """Generate a readable, self-contained district_report.html in results/.

    This is called whenever the analysis runs, so the confidence level,
    hypothesis decision and district rows match its CSV and summary.txt.
    No browser/CDN/network access or extra Python dependencies are needed.
    """
    def h(value):
        return escape(str(value), quote=True)

    def numeric(value, digits=2, signed=False, suffix=""):
        try:
            n = float(value)
            if not math.isfinite(n):
                return "—"
            return f"{n:{'+' if signed else ''}.{digits}f}{suffix}"
        except (TypeError, ValueError):
            return "—"

    def decision_kind(item):
        try:
            lower = float(item["ci_lower_pct_points"])
            upper = float(item["ci_upper_pct_points"])
        except (KeyError, ValueError, TypeError):
            return "nodata"
        if not math.isfinite(lower) or not math.isfinite(upper):
            return "nodata"
        if lower > 0:
            return "supports"
        if upper < 0:
            return "opposite"
        return "inconclusive"

    labels = {
        "supports": "Supports H1",
        "inconclusive": "Fail to reject H0",
        "opposite": "Opposite direction",
        "nodata": "Insufficient data",
    }
    kind = decision_kind(overall)
    def value_with_count(item, key_rate, key_success, key_total):
        total = int(item[key_total])
        if not total:
            return "—"
        return f"{numeric(item[key_rate])}% <small>({int(item[key_success])}/{total})</small>"

    def rate(rate, successes, n):
        return f"{numeric(rate)}% <small>({successes}/{n} weeks)</small>" if n else "Unavailable"

    rows = []
    for _, item in districts.sort_values(["State/UT", "District"]).iterrows():
        state = h(item["State/UT"])
        name = h(item["District"])
        row_kind = decision_kind(item)
        wet = value_with_count(item, "wet_rate_pct", "wet_spikes", "wet_weeks")
        normal = value_with_count(item, "normal_rate_pct", "normal_spikes", "normal_weeks")
        low, high = item["ci_lower_pct_points"], item["ci_upper_pct_points"]
        bounds = (
            f"[{numeric(low, signed=True)}, {numeric(high, signed=True)}] pp"
            if row_kind != "nodata" else "—"
        )
        diff = numeric(item["difference_pct_points"], signed=True, suffix=" pp")
        status = h(item["status"])
        warning = str(item.get("ci_warning", "") or "")
        if warning:
            status += f"<br><span class='dim'>{h(warning)}</span>"
        rows.append(
            "<tr data-kind='" + row_kind + "'>"
            f"<td><strong>{name}</strong><br><span class='dim'>{state}</span></td>"
            f"<td>{wet}</td><td>{normal}</td>"
            f"<td>{diff}</td><td>{bounds}</td>"
            f"<td><span class='badge {row_kind}'>{h(labels[row_kind])}</span></td>"
            f"<td class='status'>{status}</td></tr>"
        )

    available = int((districts["wet_weeks"].gt(0) & districts["normal_weeks"].gt(0)).sum())
    no_coords = int((districts["status"] == "district coordinates not found").sum())
    summary_ci = (
        f"[{numeric(overall['ci_lower_pct_points'], signed=True)}, "
        f"{numeric(overall['ci_upper_pct_points'], signed=True)}] percentage points"
        if kind != "nodata" else "Cannot calculate (one group has no observations)"
    )
    warning = (
        f"<div class='warning'><strong>Small-sample warning:</strong> {h(overall['ci_warning'])}</div>"
        if overall.get("ci_warning") else ""
    )
    charts = "".join(
        f"<figure><img src='data:image/png;base64,{b64encode((args.output / name).read_bytes()).decode()}' "
        f"alt='{h(label)}' loading='lazy'><figcaption>{h(label)}</figcaption></figure>"
        for name, label in (
            ("district_comparison.png", "District spike rates: wet versus non-wet"),
            ("district_confidence_intervals.png", f"{args.confidence:g}% confidence intervals by district"),
        )
        if (args.output / name).exists()
    )

    template = """<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta http-equiv='Cache-Control' content='no-store'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Team 20 | District rainfall &amp; onion-price report</title>
<style>
:root {color-scheme:light;--ink:#17253e;--muted:#607086;--line:#dce4ed;--bg:#f4f7fa;--blue:#136b78;--card:#fff;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink)}
.wrap{max-width:1250px;margin:auto;padding:34px 20px 65px}header{background:#122d42;color:white;border-radius:18px;padding:28px 34px}
.kicker{text-transform:uppercase;letter-spacing:.14em;font-weight:800;font-size:11px;color:#90d7e0}
h1{font-size:clamp(26px,4vw,40px);line-height:1.13;margin:9px 0 12px}h2{font-size:22px;margin:0 0 16px}p{margin:8px 0}header p{color:#d7e3ec}
.pills{display:flex;gap:9px;flex-wrap:wrap;margin-top:18px}.pill{border:1px solid #577080;border-radius:100px;padding:5px 11px;font-size:12px;color:#e0f6f5}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}.card{border:1px solid var(--line);border-radius:14px;padding:19px;background:var(--card);min-width:0}
.card .label{color:var(--muted);font-size:12px;letter-spacing:.02em;font-weight:700}.card .number{font-size:27px;font-weight:750;line-height:1.35;margin-top:5px;overflow-wrap:anywhere}.card small,small{font-size:12px;color:var(--muted)}
section{margin-top:22px}.section{border:1px solid var(--line);border-radius:14px;background:white;padding:24px}.decision{border-left:5px solid #64748b}.decision.supports{border-color:#138566}.decision.opposite{border-color:#b33c48}.decision.inconclusive{border-color:#cc8e22}.decision.nodata{border-color:#7c8792}
.badge{display:inline-block;padding:4px 9px;border-radius:30px;font-size:12px;font-weight:700;white-space:nowrap;background:#edf1f5;color:#334155}.badge.supports{background:#dff8ed;color:#176444}.badge.inconclusive{background:#fff4d9;color:#815c12}.badge.opposite{background:#ffe5e8;color:#943a48}.badge.nodata{background:#eff2f5;color:#52606c}
.warning{border:1px solid #e7c581;background:#fff8e5;border-radius:10px;padding:12px 15px;margin-top:13px;color:#704b11}
.dim{color:var(--muted);font-size:12px}.note{color:var(--muted);font-size:13px;margin-top:12px}
.actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin-bottom:16px}.filters{display:flex;flex-wrap:wrap;gap:9px;flex:1}
input,select{font:inherit;min-width:180px;max-width:100%;padding:9px 12px;border:1px solid #c9d4df;border-radius:9px;background:white;color:var(--ink)}input{flex:1}
button,.link{border:1px solid #c9d4df;border-radius:9px;background:white;padding:8px 12px;color:var(--ink);font:inherit;text-decoration:none;cursor:pointer}
.table-scroll{width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;min-width:840px}th{text-align:left;background:#f2f6f9;color:#41536b;position:sticky;top:0}td,th{padding:12px 10px;border-bottom:1px solid #e8edf2;vertical-align:top}tbody tr:hover{background:#f8fbfc}
figcaption{text-align:center;color:var(--muted);font-size:12px;padding:8px}figure{margin:12px 0 20px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:white}figure img{max-width:100%;width:100%;height:auto;display:block}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.formula{font:14px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere;background:#f4f7fa;border-radius:9px;padding:14px}
footer{color:#677589;font-size:12px;margin-top:25px}
@media(max-width:950px){.grid{grid-template-columns:repeat(2,1fr)}.chart-grid{grid-template-columns:1fr}}@media(max-width:580px){.grid{grid-template-columns:1fr}.wrap{padding:12px 12px 40px}header,.section{padding:20px}}
@media print{body{background:white}.wrap{padding:0}.filters,button,.link{display:none!important}.section{page-break-inside:avoid}th{position:static}}
</style>
</head>
<body><main class='wrap'>
<header><div class='kicker'>CS215 · Team 20 · Exploratory analysis</div>
<h1>Does Rain Make Onions Cry?</h1><p>All-district weekly rainfall and onion-price spike report · two-sided Wald confidence intervals</p>
<div class='pills'><span class='pill'>Confidence: {{CONFIDENCE}}%</span>
<span class='pill'>Spike: ≥{{THRESHOLD}}%</span><span class='pill'>Response: weeks 1–{{WEEKS}}</span>
<span class='pill'>Normal-group lookback: {{LOOKBACK}} weeks</span></div></header>
<div class='grid'>
<div class='card'><div class='label'>Wet spike proportion (p₁)</div><div class='number'>{{WET_RATE}}</div></div>
<div class='card'><div class='label'>Normal spike proportion (p₀)</div><div class='number'>{{NORMAL_RATE}}</div></div>
<div class='card'><div class='label'>Difference p₁ − p₀</div><div class='number'>{{DIFFERENCE}}</div><small>Percentage points</small></div>
<div class='card'><div class='label'>District coverage</div><div class='number'>{{COVERAGE}}</div><small>{{MATCHED}} matched locations · {{MISSING}} unmatched</small></div>
</div>
<section class='section decision {{KIND}}'><div class='kicker' style='color:#367385'>Overall hypothesis decision</div>
<h2><span class='badge {{KIND}}'>{{SHORT_DECISION}}</span> · {{CONFIDENCE}}% confidence interval</h2>
<p><strong>{{CONCLUSION}}</strong></p>
<p>CI for p₁ − p₀: <strong>{{OVERALL_CI}}</strong></p>
<p>SE (proportion scale): <strong>{{SE}}</strong> · z critical: <strong>{{Z}}</strong></p>
{{WARNING}}
<p class='note'>H₀: p₁ = p₀ · H₁: p₁ &gt; p₀. A wholly positive interval supports H₁; an interval including zero fails to reject H₀; a wholly negative interval points in the opposite direction.</p>
</section>
<section class='section'><div class='actions'><h2>District-by-district results</h2><a class='link' href='district_results.csv' download>Download district CSV</a></div>
<div class='actions'><div class='filters'><input id='search' type='search' placeholder='Search district or state' aria-label='Search district or state'>
<select id='outcome' aria-label='Filter decisions'><option value='all'>All decisions</option><option value='supports'>Supports H₁</option><option value='inconclusive'>Inconclusive</option><option value='opposite'>Opposite direction</option><option value='nodata'>Insufficient data</option></select></div>
<button onclick='window.print()' type='button'>Print report</button></div>
<p class='dim' id='visibleCount' aria-live='polite'>Showing {{ROWS}} districts</p>
<div class='table-scroll'><table id='districts'><thead><tr><th>District / State</th><th>Wet spikes / weeks</th><th>Normal spikes / weeks</th><th>Difference</th><th>{{CONFIDENCE}}% CI</th><th>Decision</th><th>Data status / note</th></tr></thead>
<tbody>{{DISTRICT_ROWS}}</tbody></table></div>
<p class='note'>The intervals and decisions come from the current analysis run. “Insufficient data” means at least one group has no eligible weeks. Status and warnings are included for every district.</p></section>
<section><h2>Charts</h2><div class='chart-grid'>{{CHARTS}}</div></section>
<section class='section'><h2>How to read this report</h2>
<p>Each rainfall week is <strong>wet</strong> if its rainfall exceeds the mean for the same ISO week in other available years + 2 sample SD. Otherwise it is <strong>normal/non-wet</strong>, including dry weeks. At least four reference years are required.</p>
<p>A price spike is a ≥{{THRESHOLD}}% increase from the reference week's median price in any of the next {{WEEKS}} weeks. Each eligible rainfall reference week counts at most once. For a normal reference week and candidate price spike, the previous {{LOOKBACK}} rainfall weeks must all be non-wet; missing or recently wet histories are excluded.</p>
<div class='formula'>d = p₁ − p₀<br>SE = sqrt(p₁(1−p₁)/n₁ + p₀(1−p₀)/n₀)<br>CI = [d − z·SE, d + z·SE]</div>
<p class='note'><strong>Important limitations:</strong> These are approximate large-sample Wald intervals. The calculation assumes independent observations, but price windows overlap, observations are clustered by district, and some districts share rainfall grid cells. Few successes/failures can make the interval unreliable. This study identifies associations, not causation.</p>
</section><footer>Generated automatically by <code>onion_analysis.py</code>. Source data: existing onion-price and rainfall CSVs. Last generated: <strong>{{GENERATED_AT}}</strong>.</footer>
</main><script>
(function(){const search=document.getElementById('search');const filter=document.getElementById('outcome');const rows=Array.from(document.querySelectorAll('#districts tbody tr'));const label=document.getElementById('visibleCount');
function update(){const query=search.value.trim().toLowerCase();const wanted=filter.value;let shown=0;for(const row of rows){const match=(!query||row.textContent.toLowerCase().includes(query))&&(wanted==='all'||row.dataset.kind===wanted);row.hidden=!match;if(match)shown++;}label.textContent='Showing '+shown+' of '+rows.length+' districts';}
search.addEventListener('input',update);filter.addEventListener('change',update);update();})();
</script></body></html>"""
    substitutes = {
        "CONFIDENCE": numeric(args.confidence, digits=0),
        "THRESHOLD": numeric(args.spike_threshold, digits=1),
        "WEEKS": str(args.weeks), "LOOKBACK": str(args.lookback_weeks),
        "WET_RATE": rate(overall["wet_rate_pct"], wet_success, wet_n),
        "NORMAL_RATE": rate(overall["normal_rate_pct"], normal_success, normal_n),
        "DIFFERENCE": numeric(overall["difference_pct_points"], signed=True, suffix=" pp"),
        "COVERAGE": f"{available} / {len(districts)}",
        "MATCHED": str(matched_count), "MISSING": str(no_coords),
        "KIND": kind, "SHORT_DECISION": h(labels[kind]),
        "CONCLUSION": h(overall["conclusion"]),
        "OVERALL_CI": summary_ci, "SE": numeric(overall["standard_error"], 6),
        "Z": numeric(overall["z_critical"], 4),
        "WARNING": warning, "ROWS": str(len(districts)),
        "DISTRICT_ROWS": "\n".join(rows), "CHARTS": charts or "<p>Charts unavailable.</p>",
        "GENERATED_AT": h(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")),
    }
    for key, value in substitutes.items():
        template = template.replace("{{" + key + "}}", value)
    (args.output / "district_report.html").write_text(template, encoding="utf-8")
    csv_link = os.path.relpath(args.output / "district_results.csv", ROOT).replace(os.sep, "/")
    (ROOT / "district_report.html").write_text(
        template.replace("href='district_results.csv'", f"href='{h(csv_link)}'"),
        encoding="utf-8",
    )


def positive_int(value):
    try:
        number = int(value)
        if number >= 1:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("must be a positive whole number")


def parse_confidence(value):
    """Accept --confidence 95, 99, 90, or 0.95."""
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("confidence must be a number, e.g. 95") from error
    if 0 < number < 1:
        number *= 100
    if not math.isfinite(number) or not (0 < number < 100):
        raise argparse.ArgumentTypeError("confidence must be between 0 and 100 (exclusive)")
    return number


def main():
    parser = argparse.ArgumentParser(description="All districts: wet rainfall, weekly spikes, confidence intervals")
    parser.add_argument("--prices", type=Path, default=PRICE_FILE)
    parser.add_argument("--rainfall", type=Path, default=RAIN_FOLDER)
    parser.add_argument("--locations", type=Path,
                        help="Optional CSV: State/UT,District,Latitude,Longitude")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    parser.add_argument("--weeks", type=positive_int, default=4, help="Check weeks 1..N (default 4)")
    parser.add_argument("--lookback-weeks", type=positive_int, default=2,
                        help="Normal-group preceding nonwet weeks (default 2)")
    parser.add_argument("--spike-threshold", type=float, default=10.0,
                        help="Price rise threshold percentage (default 10)")
    parser.add_argument("--confidence", type=parse_confidence, default=95.0,
                        help="Two-sided confidence level: 95 (default), 90 or 99")
    args = parser.parse_args()
    if not math.isfinite(args.spike_threshold) or not (0 < args.spike_threshold < 10000):
        parser.error("--spike-threshold must be a positive finite percentage")
    args.output.mkdir(parents=True, exist_ok=True)

    try:
        places, price_data = read_prices(args.prices)
        print(f"Found {len(places)} State/UT and district pairs")
        locs = read_locations(args.locations, args.output / "district_coordinates_cache.json")
        matched, missing = {}, []
        for state, district in places:
            loc = locs.get((clean_name(state), clean_name(district)))
            if loc is None:
                missing.append({"State/UT": state, "District": district, "reason": "district coordinates not found"})
            else:
                lat, lon, origin = loc
                matched[(state, district)] = (lat, lon, grid_key(lat, lon), origin)
        if not matched:
            raise ValueError("No districts matched; provide --locations district_locations.csv")
        print(f"Matched locations: {len(matched)}; unmatched: {len(missing)}")
        rainfall_data = read_rainfall(args.rainfall, {entry[2] for entry in matched.values()})
        event_tables, district_rows = [], []
        exclude_names = [
            "excluded_recent_wet_before_normal_week",
            "excluded_wet_before_price_spike",
            "excluded_missing_lookback_rainfall",
            "incomplete_price_window",
            "unclassified_rainfall",
        ]
        for state, district in places:
            record = {
                "State/UT": state, "District": district,
                "Latitude": float("nan"), "Longitude": float("nan"),
                "grid_latitude": float("nan"), "grid_longitude": float("nan"),
                "location_source": "", "wet_weeks": 0, "wet_spikes": 0,
                "normal_weeks": 0, "normal_spikes": 0, "status": "ok",
            }
            record.update({name + "_count": 0 for name in exclude_names})
            loc = matched.get((state, district))
            if loc is None:
                record["status"] = "district coordinates not found"
            else:
                lat, lon, key, origin = loc
                record.update({"Latitude": lat, "Longitude": lon,
                               "grid_latitude": (key // 1000) / 4,
                               "grid_longitude": (key % 1000) / 4,
                               "location_source": origin})
                prices = price_data.get((state, district))
                if prices is None or len(prices) < args.weeks + 1:
                    record["status"] = "not enough price weeks"
                elif key not in rainfall_data or rainfall_data[key].notna().sum() == 0:
                    record["status"] = "no usable rainfall for grid"
                else:
                    events, eligible = compare(prices, rainfall_data[key],
                                               args.spike_threshold, args.weeks,
                                               args.lookback_weeks)
                    for condition in ("wet", "normal"):
                        subset = eligible[eligible["rain_condition"] == condition]
                        record[f"{condition}_weeks"] = len(subset)
                        record[f"{condition}_spikes"] = int(subset["spike_found"].sum())
                    for name in exclude_names:
                        record[name + "_count"] = int((events["eligibility"] == name).sum())
                    if not record["wet_weeks"] or not record["normal_weeks"]:
                        record["status"] = "missing wet or normal eligible weeks"
                    events.insert(0, "District", district)
                    events.insert(0, "State/UT", state)
                    event_tables.append(events)
            record.update(confidence_interval(record["wet_weeks"], record["wet_spikes"],
                                              record["normal_weeks"], record["normal_spikes"],
                                              args.confidence))
            district_rows.append(record)

        district_results = pd.DataFrame(district_rows)
        district_results.to_csv(args.output / "district_results.csv", index=False, float_format="%.4f")
        pd.DataFrame(missing, columns=["State/UT", "District", "reason"]).to_csv(
            args.output / "unmatched_districts.csv", index=False
        )
        pd.DataFrame(
            [{"State/UT": row["State/UT"], "District": row["District"],
              "Latitude": "", "Longitude": ""} for row in missing],
            columns=["State/UT", "District", "Latitude", "Longitude"],
        ).to_csv(args.output / "missing_locations_template.csv", index=False)
        if event_tables:
            pd.concat(event_tables, ignore_index=True).to_csv(
                args.output / "all_weekly_events.csv", index=False, float_format="%.4f"
            )
        else:
            (args.output / "all_weekly_events.csv").write_text(
                "State/UT,District,rain_week_start,rain_week_end\n", encoding="utf-8"
            )

        save_plots(district_results, args.output, args.spike_threshold, args.weeks, args.confidence)
        comparable = district_results[
            (district_results["wet_weeks"] > 0) & (district_results["normal_weeks"] > 0)
        ]
        wet_n, wet_success = int(comparable["wet_weeks"].sum()), int(comparable["wet_spikes"].sum())
        normal_n, normal_success = int(comparable["normal_weeks"].sum()), int(comparable["normal_spikes"].sum())
        overall = confidence_interval(wet_n, wet_success, normal_n, normal_success, args.confidence)
        def format_rate(rate, successes, n):
            return f"{rate:.2f}% ({successes}/{n} weeks)" if n else "Unavailable (0 weeks)"

        lines = [
            "TEAM 20 — WEEKLY RAINFALL AND ONION PRICE SPIKES",
            f"Districts in prices: {len(places)} | matched coordinates: {len(matched)}",
            f"Districts with both eligible rainfall groups: {len(comparable)}",
            f"Price spike: >= {args.spike_threshold:g}% within 1..{args.weeks} weeks",
            "Wet: rainfall > mean of other years' same ISO week + 2 sample SD",
            "Normal: rainfall <= threshold, including dry weeks",
            f"Normal lookback: previous {args.lookback_weeks} weeks must be non-wet; candidate spike weeks also checked",
            "Missing price windows, unknown lookbacks and contaminated normal spikes are excluded.",
            "One eligible reference week counts as at most one success.",
            "",
            "H0: p_wet = p_normal",
            "H1: p_wet > p_normal",
            f"Confidence: {args.confidence:g}% (two-sided Wald interval)",
            f"Wet spike rate:    {format_rate(overall['wet_rate_pct'], wet_success, wet_n)}",
            f"Normal spike rate: {format_rate(overall['normal_rate_pct'], normal_success, normal_n)}",
        ]
        if wet_n and normal_n:
            lines += [
                f"Difference (wet - normal): {overall['difference_pct_points']:+.2f} percentage points",
                f"Standard error (proportion scale): {overall['standard_error']:.6f}",
                f"Critical z: {overall['z_critical']:.4f}",
                f"{args.confidence:g}% CI for p_wet-p_normal: "
                f"[{overall['ci_lower_pct_points']:+.2f}, {overall['ci_upper_pct_points']:+.2f}] percentage points",
            ]
        lines += [
            f"Conclusion: {overall['conclusion']}",
        ]
        if overall["ci_warning"]:
            lines.append("WARNING: " + overall["ci_warning"])
        lines += [
            "",
            "Decision: positive CI -> reject H0 in favor of H1; CI containing 0 -> fail to reject H0;",
            "negative CI -> evidence in opposite direction, not support for H1.",
            "These intervals assume independent district-week observations, which is doubtful because",
            "price windows overlap and locations may share rainfall grid cells.",
            "Use results as exploratory approximate uncertainty, not proof of causation.",
            "See district_results.csv for confidence intervals in each district.",
        ]
        report = "\n".join(lines) + "\n"
        (args.output / "summary.txt").write_text(report, encoding="utf-8")
        save_html_report(district_results, overall, wet_n, wet_success,
                         normal_n, normal_success, args, len(matched))
        print("\n" + report)
        print(f"Updated HTML report: {args.output / 'district_report.html'}")
        print(f"Also updated: {ROOT / 'district_report.html'}")
        print(f"Results saved to: {args.output}")
    except (ValueError, OSError, KeyError, pd.errors.ParserError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
