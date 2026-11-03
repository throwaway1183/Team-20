"""Team 20: read large rainfall CSVs without loading the whole India grid into RAM.

Expected columns: LONGITUDE, LATITUDE, TIME, RAINFALL.
CSV files are already extracted, so R is NOT needed to run this script.
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Work in a terminal without opening graph windows.
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_RAIN = ROOT / "data" / "rainfall" / "data"
COLUMNS = ["LONGITUDE", "LATITUDE", "TIME", "RAINFALL"]
CHUNK_SIZE = 300_000


def rainfall_files(folder=DEFAULT_RAIN, year=None):
    """Return the five (or fewer) RF25_indYYYY_rfp25.csv files in order."""
    folder = Path(folder)
    if folder.is_file() and folder.suffix.lower() == ".csv":
        files = [folder]
    else:
        files = sorted(folder.glob("RF25_ind*_rfp25.csv")) if folder.is_dir() else []
    if year is not None:
        files = [file for file in files if f"ind{year}_" in file.name]
    if not files:
        raise ValueError(f"No matching rainfall CSV files in {folder}. Check the filename/path.")
    return files


def grid_point(latitude, longitude):
    """The rainfall data uses a 0.25-degree grid. Pick the closest grid cell."""
    return round(latitude * 4) / 4, round(longitude * 4) / 4


def rainfall_chunks(file):
    """Read only the four columns needed, a little at a time."""
    return pd.read_csv(
        file, usecols=COLUMNS,
        dtype={"LONGITUDE": "float32", "LATITUDE": "float32", "RAINFALL": "float32"},
        chunksize=CHUNK_SIZE, na_values=["NA", ""],
    )


def load_location_rainfall(folder=DEFAULT_RAIN, latitude=15.83, longitude=78.05, year=None):
    """Read rainfall for one grid point; return a daily Series indexed by date.

    This keeps only ~365 days/year instead of millions of nationwide grid rows.
    """
    lat, lon = grid_point(latitude, longitude)
    pieces = []
    files = rainfall_files(folder, year)
    for file in files:
        print(f"Reading {file.name} for grid ({lat:.2f}, {lon:.2f}) ...", flush=True)
        for chunk in rainfall_chunks(file):
            chosen = chunk.loc[
                ((chunk["LATITUDE"] - lat).abs() < 0.001)
                & ((chunk["LONGITUDE"] - lon).abs() < 0.001)
            ]
            if chosen.empty:
                continue
            dates = pd.to_datetime(chosen["TIME"], format="%Y-%m-%d", errors="coerce")
            values = pd.to_numeric(chosen["RAINFALL"], errors="coerce")
            small = pd.DataFrame({"date": dates, "rainfall": values})
            pieces.append(small)

    if not pieces:
        raise ValueError(
            f"No rows for grid ({lat:.2f}, {lon:.2f}). "
            "Choose coordinates inside the India rainfall grid."
        )
    data = pd.concat(pieces, ignore_index=True).dropna(subset=["date", "rainfall"])
    data = data[data["rainfall"] >= 0]
    data = data.drop_duplicates(subset="date").sort_values("date")
    if data.empty:
        raise ValueError(f"No valid rainfall values at ({lat:.2f}, {lon:.2f}); only NA values.")
    daily = data.set_index("date")["rainfall"].astype(float)
    daily.name = "rainfall_mm"
    return daily, (lat, lon)


def monthly_rainfall(daily, min_days=20):
    """Add observed daily rain within each month; ignore incomplete months."""
    groups = daily.groupby(daily.index.to_period("M"))
    monthly = groups.sum()
    counts = groups.count()
    monthly[counts < min_days] = float("nan")
    monthly.name = "rainfall_mm"
    return monthly.sort_index()


def make_rainfall_map(folder, year, output, point):
    """Optional one-year India map, calculated in small chunks."""
    totals = None
    counts = None
    heavy = None
    for file in rainfall_files(folder, year):
        print(f"Building map from {file.name} ...", flush=True)
        for chunk in rainfall_chunks(file):
            chunk = chunk.dropna(subset=["LATITUDE", "LONGITUDE", "RAINFALL"])
            chunk = chunk[chunk["RAINFALL"] >= 0]
            if chunk.empty:
                continue
            cells = chunk.groupby(["LATITUDE", "LONGITUDE"])["RAINFALL"]
            sums = cells.sum().astype(float)
            cnts = cells.size().astype(float)
            counts = cnts if counts is None else counts.add(cnts, fill_value=0)
            totals = sums if totals is None else totals.add(sums, fill_value=0)
            chunk["HEAVY"] = chunk["RAINFALL"] >= 50  # 50 mm/day: simple rule
            hv = chunk.groupby(["LATITUDE", "LONGITUDE"])["HEAVY"].sum().astype(float)
            heavy = hv if heavy is None else heavy.add(hv, fill_value=0)

    if counts is None or counts.empty:
        raise ValueError("No valid rainfall grid values to plot.")

    for values, title, filename, legend in [
        (totals / counts, "Average daily rainfall in India", "rainfall_map.png", "Average rainfall (mm/day)"),
        (heavy, "Days with >= 50 mm rainfall", "heavy_rain_days.png", "Heavy rain days"),
    ]:
        fig, ax = plt.subplots(figsize=(10, 6))
        image = ax.scatter(values.index.get_level_values(1),
                           values.index.get_level_values(0),
                           c=values.to_numpy(), s=8, marker="s", cmap="YlGnBu")
        ax.plot(point[1], point[0], "r+", markersize=9, markeredgewidth=2)
        fig.colorbar(image, ax=ax, label=legend)
        ax.set(title=f"{title} ({year})", xlabel="Longitude", ylabel="Latitude")
        fig.tight_layout()
        fig.savefig(output / filename, dpi=130)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Rainfall plots using your RF25 CSV files")
    parser.add_argument("--rainfall", "--data", type=Path, default=DEFAULT_RAIN)
    parser.add_argument("--year", type=int, default=2025, help="Year for rainfall plots (default: 2025)")
    parser.add_argument("--latitude", type=float, default=15.83, help="District latitude (default: Kurnool)")
    parser.add_argument("--longitude", type=float, default=78.05, help="District longitude (default: Kurnool)")
    parser.add_argument("--map", action="store_true", help="Also make India-wide maps (reads every grid row)")
    parser.add_argument("--output", type=Path, default=ROOT / "plots")
    args = parser.parse_args()
    try:
        daily, point = load_location_rainfall(args.rainfall, args.latitude, args.longitude, args.year)
        monthly = monthly_rainfall(daily)
        args.output.mkdir(parents=True, exist_ok=True)
        monthly.to_csv(args.output / "monthly_rainfall.csv", index_label="month")

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(daily.index, daily, linewidth=1)
        ax.set(title=f"Daily rainfall at grid ({point[0]}, {point[1]}) - {args.year}",
               xlabel="Date", ylabel="Rainfall (mm)")
        fig.tight_layout()
        fig.savefig(args.output / "daily_rainfall.png", dpi=140)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(monthly.index.to_timestamp(), monthly.to_numpy(), width=20)
        ax.set(title=f"Monthly rainfall - {args.year}", xlabel="Month", ylabel="Total rainfall (mm)")
        fig.tight_layout()
        fig.savefig(args.output / "monthly_rainfall.png", dpi=140)
        plt.close(fig)

        if args.map:
            make_rainfall_map(args.rainfall, args.year, args.output, point)
    except (ValueError, OSError, KeyError, pd.errors.ParserError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Rainfall grid cell: {point[0]:.2f}, {point[1]:.2f}")
    print(f"Plots and CSV saved in: {args.output}")


if __name__ == "__main__":
    main()
