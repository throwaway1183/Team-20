# Team 20 — Does Rain Make Onions Cry?

A simple data-analysis project comparing **weekly onion-price spikes** with unusually wet and normal **monthly rainfall** across **all districts** for which coordinates and data are available. This is a descriptive comparison, not a formal hypothesis test. You can set the number of weeks used to define a price spike with `--weeks N`.

## Files and folders

Keep your existing rainfall and price CSVs in their original locations:

```text
Team-20/
├── onion_analysis.py
├── data/
│   ├── prices/
│   │   └── onion_prices.csv
│   └── rainfall/
│       └── data/
│           ├── RF25_ind2021_rfp25.csv
│           ├── RF25_ind2022_rfp25.csv
│           ├── RF25_ind2023_rfp25.csv
│           ├── RF25_ind2024_rfp25.csv
│           └── RF25_ind2025_rfp25.csv
└── results/       # generated automatically
```

You do **not** need to download new datasets or rerun NetCDF conversion if these CSVs already exist.

## Run

From `Team-20`:

```bash
python3 -m pip install -r requirements.txt
python3 onion_analysis.py              # 1-week price change (default)
python3 onion_analysis.py --weeks 2    # 2-week price change
python3 onion_analysis.py --weeks 4    # 4-week price change
python3 onion_analysis.py --weeks 8    # 8-week price change
```

The script finds all `(State/UT, District)` pairs in your price CSV and matches each with an approximate location in the rainfall grid. On the first run it tries to download district coordinates and saves a cache; internet is needed for that step. To use your own coordinates without a download, provide a CSV with columns `State/UT,District,Latitude,Longitude`:

```bash
python3 onion_analysis.py --locations district_locations.csv
```

## How the calculations work

**Weekly onion-price spike**

1. Read dates using `DD-MM-YYYY` and convert prices like `"1,537.00"` to numbers.
2. Take the median of all prices for each district on each date, then the median of those daily prices for each **Monday–Sunday week**.
3. Compare this week's median with the median **N calendar weeks earlier** using `--weeks N` (default `1`):

   `price_change_pct = 100 * (this_week_price / price_N_weeks_ago - 1)`

4. A price increase of **at least 20% over N weeks** counts as a spike (`--spike-threshold 20`). All weeks within the N-week comparison window must contain at least one observed price; missing weeks invalidate that comparison. For example, `--weeks 4` compares the current week with four weeks earlier, but only if all five weekly prices exist.

**Monthly rainfall**

- Daily rainfall is summed for the closest 0.25° grid cell; a month must have at least **25 valid daily readings**.
- For a given month/year, compute the *mean (μ)* and *sample standard deviation (σ)* of rainfall for that **same calendar month in the other available years**. At least **four other years** are required.
- **Wet:** monthly rainfall **strictly greater than μ + 2σ**.
- **Normal:** monthly rainfall **less than or equal to μ + 2σ**, including dry months and zero-rainfall months.
- **Unclassified:** only months lacking rainfall readings or enough reference years. No minimum rainfall or standard deviation cutoff is imposed.
- This project uses **"normal" to mean "not extremely wet"**, rather than a meteorological definition of average rainfall. Thus drought months are included in the normal group.

**Matching rain to prices**

The default is `--lag 1`: a price week is assigned by its **Sunday (end) date**; every week ending in July uses the **rainfall classification for June**. Thus several weekly price observations can share the same month's rainfall label. This is expected and means the weekly observations are not independent.

You can try `--lag 2` (two previous months) or `--lag 0` (same month). **Caution:** `--lag 0` pairs an early-month price week with the *whole month's rainfall*, including rainfall after that week; use it as a descriptive comparison only.

The 20% monthly spike threshold from the original proposal is now interpreted as **20% over the selected number of weeks**. With `--weeks 1`, this means a single-week increase; with `--weeks 4`, it means an increase across four weeks. Overlapping multiweek windows are not independent. Changing `--weeks` changes the definition of a spike, so compare results carefully. If you want to examine smaller weekly movements, try:

```bash
python3 onion_analysis.py --spike-threshold 10
```

Do not change thresholds just to make the hypothesis look supported.

## Output (`results/`)

| File | Contents |
|---|---|
| `summary.txt` | Overall weekly spike rates after wet and normal rainfall, and a simple conclusion. |
| `district_results.csv` | All districts, `wet_weeks`, `normal_weeks`, spike counts, rates, and availability status. |
| `all_weekly_results.csv` | Weekly median prices, selected comparison window (`comparison_weeks`), price N weeks earlier (`reference_onion_price`), N-week percentage change, price-spike indicator, and rainfall details. |
| `district_comparison.png` | Weekly spike-rate comparison for up to 20 districts with both conditions. |
| `unmatched_districts.csv` | District names whose coordinates were unavailable. |
| `missing_locations_template.csv` | Sheet to add your own coordinates for those districts. |
| `district_coordinates_cache.json` | Coordinates cache, if obtained by the script. |

**Note:** If you ran the old *monthly* script earlier, `results/all_monthly_results.csv` may still be present. It is an older output; use **`all_weekly_results.csv`** for this version.

## Hypothesis

- **H0:** The selected N-week onion-price spike rates are the same after unusually wet versus normal rainfall.
- **H1:** The selected N-week spike rate is higher after unusually wet rainfall.

The program **compares the observed rates only**. It does not calculate a p-value or prove that rain causes changes in onion prices.

The baseline uses a short set of rainfall years (often 2021–2025) rather than official long-term rainfall normals, and each district is represented by an approximate rainfall-grid cell. Treat findings as exploratory.
