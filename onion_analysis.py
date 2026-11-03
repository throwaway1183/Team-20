"""Team 20: do onion prices rise more often after unusually wet months?

Uses the real file columns shown by the team:
  prices: State/UT, District, Modal Price, Price Date
  rainfall: LONGITUDE, LATITUDE, TIME, RAINFALL

This is a simple observational comparison, NOT a claim of causation.
The script runs on its own: it does not depend on rainfall.py.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# This script is self-contained: it does not import rainfall.py.
# That way an older rainfall.py in the project will not interfere.
ROOT = Path(__file__).resolve().parent
DEFAULT_RAIN = ROOT / "data" / "rainfall" / "data"


def load_location_rainfall(folder, latitude, longitude):
    """Read nearby daily rainfall without loading the nationwide grid into memory."""
    folder = Path(folder)
    if folder.is_file() and folder.suffix.lower() == ".csv":
        files = [folder]
    else:
        files = sorted(folder.glob("RF25_ind*_rfp25.csv")) if folder.is_dir() else []
    if not files:
        raise ValueError(f"No rainfall CSV files found in {folder}")

    # Your rainfall is on a quarter-degree grid (0.25 degrees).
    lat = round(latitude * 4) / 4
    lon = round(longitude * 4) / 4
    pieces = []

    for file in files:
        print(f"Reading {file.name} at ({lat:.2f}, {lon:.2f})...", flush=True)
        for chunk in pd.read_csv(
            file,
            usecols=["LONGITUDE", "LATITUDE", "TIME", "RAINFALL"],
            dtype={"LONGITUDE": "float32", "LATITUDE": "float32", "RAINFALL": "float32"},
            na_values=["NA", ""],
            chunksize=300_000,
        ):
            found = chunk.loc[
                (chunk["LATITUDE"].sub(lat).abs() < 0.001)
                & (chunk["LONGITUDE"].sub(lon).abs() < 0.001),
                ["TIME", "RAINFALL"],
            ].copy()
            if not found.empty:
                pieces.append(found)

    if not pieces:
        raise ValueError(f"No rainfall records found at grid ({lat:.2f}, {lon:.2f}).")

    data = pd.concat(pieces, ignore_index=True)
    data["date"] = pd.to_datetime(data["TIME"], format="%Y-%m-%d", errors="coerce")
    data["rainfall"] = pd.to_numeric(data["RAINFALL"], errors="coerce")
    data = data.dropna(subset=["date", "rainfall"])
    data = data.loc[data["rainfall"] >= 0].drop_duplicates("date")
    if data.empty:
        raise ValueError(f"Only missing/invalid rainfall at grid ({lat:.2f}, {lon:.2f}).")
    daily = data.sort_values("date").set_index("date")["rainfall"].astype(float)
    return daily, (lat, lon)


def monthly_rainfall(daily):
    """Sum daily rainfall in a month, requiring at least 20 observed days."""
    by_month = daily.groupby(daily.index.to_period("M"))
    totals = by_month.sum()
    totals[by_month.count() < 20] = float("nan")
    totals.name = "rainfall_mm"
    return totals.sort_index()

DEFAULT_PRICES = ROOT / "data" / "prices" / "onion_prices.csv"
PRICE_COLUMNS = ["State/UT", "District", "Modal Price", "Price Date"]


def load_monthly_prices(file, state, district):
    """Find one district in a large price file, clean and compute monthly prices."""
    file = Path(file)
    if not file.is_file():
        raise ValueError(f"Onion price CSV not found: {file}")

    selected = []
    for chunk in pd.read_csv(file, usecols=PRICE_COLUMNS, dtype=str, chunksize=100_000):
        # Ignore leading/trailing spaces and capitalization differences.
        matches = (
            chunk["State/UT"].str.strip().str.casefold().eq(state.casefold())
            & chunk["District"].str.strip().str.casefold().eq(district.casefold())
        )
        if matches.any():
            selected.append(chunk.loc[matches, ["Price Date", "Modal Price"]].copy())

    if not selected:
        raise ValueError(
            f"No price rows for {district}, {state}. "
            "Check spelling against the State/UT and District columns."
        )
    data = pd.concat(selected, ignore_index=True)

    # '31-12-2021' is day-month-year. '1,537.00' has a thousands separator.
    data["date"] = pd.to_datetime(data["Price Date"].str.strip(),
                                   format="%d-%m-%Y", errors="coerce")
    clean_price = data["Modal Price"].str.replace(",", "", regex=False).str.strip()
    data["price"] = pd.to_numeric(clean_price, errors="coerce")
    data = data.dropna(subset=["date", "price"])
    data = data[data["price"] > 0]
    if data.empty:
        raise ValueError(f"No valid prices remained for {district}, {state}.")

    # First take the median across multiple mandi records on a day, then
    # the median daily price in each month. We don't need market coordinates.
    daily = data.groupby("date")["price"].median()
    monthly = daily.groupby(daily.index.to_period("M")).median().sort_index()
    monthly.name = "onion_price"
    print(f"Selected {len(data)} price rows, covering {len(monthly)} months.")
    return monthly


def compare(prices, rainfall, lag=1, spike_threshold=20):
    """Compare price spikes with rain in the same/earlier month.

    Wet: >= 120% of that calendar month's average rainfall in available years.
    Normal: 80%-119.9%. Dry months are left out of the two-group comparison.
    """
    first = min(prices.index.min(), rainfall.index.min())
    last = max(prices.index.max(), rainfall.index.max())
    months = pd.period_range(first, last, freq="M")
    result = pd.DataFrame(index=months)
    result.index.name = "month"
    result["onion_price"] = prices.reindex(months)
    result["rainfall_mm"] = rainfall.reindex(months)
    result["price_change_pct"] = result["onion_price"].pct_change(fill_method=None) * 100

    # Calculate an average separately for January, February, ..., December.
    # This keeps the monsoon season from automatically counting as 'unusually wet'.
    result["typical_rainfall_mm"] = result["rainfall_mm"].groupby(result.index.month).transform("mean")
    result["rainfall_pct_of_typical"] = (
        100 * result["rainfall_mm"] / result["typical_rainfall_mm"]
    )
    # Very dry calendar months (typical <10 mm) are too unstable for % comparisons.
    ratio = result["rainfall_pct_of_typical"]
    good = result["rainfall_mm"].notna() & (result["typical_rainfall_mm"] >= 10)
    weather = pd.Series(pd.NA, index=months, dtype="object")
    weather.loc[good & (ratio < 80)] = "dry"
    weather.loc[good & (ratio >= 80) & (ratio < 120)] = "normal"
    weather.loc[good & (ratio >= 120)] = "wet"
    result["rain_condition_this_month"] = weather

    # Example: for a November price change and lag=1, compare October rainfall.
    result["rainfall_used_mm"] = result["rainfall_mm"].shift(lag)
    result["rainfall_used_pct_of_typical"] = ratio.shift(lag)
    result["rain_condition"] = weather.shift(lag)
    result["price_spike"] = (result["price_change_pct"] >= spike_threshold).astype("boolean")
    result.loc[result["price_change_pct"].isna(), "price_spike"] = pd.NA

    valid = result.loc[
        result["price_change_pct"].notna()
        & result["rain_condition"].isin(["wet", "normal"])
    ].copy()
    if result["price_change_pct"].notna().sum() == 0:
        raise ValueError("Not enough consecutive months of prices to compute a price change.")
    return result, valid


def make_results(result, valid, args, grid):
    args.output.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output / "monthly_results.csv", index_label="month", float_format="%.2f")

    summary = []
    for condition in ("normal", "wet"):
        group = valid[valid["rain_condition"] == condition]
        n = len(group)
        spikes = int(group["price_spike"].sum())
        rate = 100 * spikes / n if n else float("nan")
        summary.append({"rain_condition": condition, "months": n,
                        "price_spikes": spikes, "spike_rate_pct": rate})
    rates = pd.DataFrame(summary)
    rates.to_csv(args.output / "spike_rates.csv", index=False, float_format="%.2f")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(result.index.to_timestamp(), result["onion_price"], marker=".")
    ax.set(title=f"Monthly onion prices - {args.district}, {args.state}",
           xlabel="Month", ylabel="Median modal price (units in original CSV)")
    fig.tight_layout()
    fig.savefig(args.output / "onion_prices.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(result.index.to_timestamp(), result["rainfall_mm"], marker=".")
    ax.set(title=f"Monthly rainfall near {args.district}",
           xlabel="Month", ylabel="Rainfall (mm)")
    fig.tight_layout()
    fig.savefig(args.output / "monthly_rainfall.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(["Normal", "Unusually wet"],
                  rates["spike_rate_pct"].fillna(0), color=["slategray", "steelblue"])
    for bar, row in zip(bars, rates.to_dict("records")):
        label = f"{row['spike_rate_pct']:.1f}% ({row['price_spikes']}/{row['months']})" if row["months"] else "No months"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                label, ha="center", va="bottom")
    ax.set(title="Onion price spikes after rainfall conditions",
           ylabel="Months with price spike (%)", ylim=(0, 115))
    fig.tight_layout()
    fig.savefig(args.output / "spike_comparison.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    for name, color in [("normal", "slategray"), ("wet", "steelblue")]:
        chosen = valid[valid["rain_condition"] == name]
        ax.scatter(chosen["rainfall_used_pct_of_typical"], chosen["price_change_pct"],
                   label=name.capitalize(), color=color)
    ax.axhline(args.spike_threshold, linestyle="--", color="darkred", label="Price spike")
    ax.set(title="Rainfall vs next/same-month onion price change",
           xlabel="Rainfall (% of typical calendar-month rain)",
           ylabel="Monthly price change (%)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(args.output / "rainfall_vs_price.png", dpi=140)
    plt.close(fig)

    def describe(condition):
        row = rates.loc[rates["rain_condition"] == condition].iloc[0]
        if row["months"] == 0:
            return "not available (0 months)"
        return f"{row['spike_rate_pct']:.1f}% ({int(row['price_spikes'])}/{int(row['months'])} months)"

    lines = [
        "TEAM 20 - DOES RAIN MAKE ONIONS CRY?",
        f"District: {args.district}, {args.state}",
        f"Rainfall grid point used: {grid[0]:.2f}, {grid[1]:.2f}",
        f"Rainfall: {args.lag} month(s) before the price change (0 = same month)",
        f"Price spike: >= {args.spike_threshold:g}% increase over previous month",
        "Wet: >= 120% of the same calendar month's mean rainfall (in available years)",
        "Normal: 80% to below 120%. Dry/very-low-rain months excluded.",
        f"Months available for wet/normal comparison: {len(valid)}",
        f"Spike rate after wet rainfall: {describe('wet')}",
        f"Spike rate after normal rainfall: {describe('normal')}",
        "",
        "Note: 'typical' is the average of the available CSV years, NOT official IMD normals.",
        "A grid cell near the district is a rainfall proxy, not exact district-wide rainfall.",
        "This is an association only; rainfall alone cannot explain onion prices.",
    ]
    report = "\n".join(lines) + "\n"
    (args.output / "summary.txt").write_text(report, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Elementary district rainfall and onion price comparison")
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    parser.add_argument("--rainfall", type=Path, default=DEFAULT_RAIN)
    parser.add_argument("--state", default="Andhra Pradesh", help="Exact State/UT from price CSV")
    parser.add_argument("--district", default="Kurnool", help="Exact District from price CSV")
    parser.add_argument("--latitude", type=float, default=15.83, help="District approximate latitude")
    parser.add_argument("--longitude", type=float, default=78.05, help="District approximate longitude")
    parser.add_argument("--lag", type=int, choices=[0, 1, 2], default=1,
                        help="Use rainfall from 0, 1 (default), or 2 months before")
    parser.add_argument("--spike-threshold", type=float, default=20)
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    try:
        prices = load_monthly_prices(args.prices, args.state, args.district)
        daily, point = load_location_rainfall(args.rainfall, args.latitude, args.longitude)
        rain = monthly_rainfall(daily)
        table, valid = compare(prices, rain, args.lag, args.spike_threshold)
        report = make_results(table, valid, args, point)
    except (ValueError, OSError, KeyError, pd.errors.ParserError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(report)
    print(f"Results saved in: {args.output}")


if __name__ == "__main__":
    main()
