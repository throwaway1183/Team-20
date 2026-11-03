# Team 20 - Does Rain Make Onions Cry?

**CS215 Data Analysis and Interpretation — simple student project**

We explore one question: **Are onion-price spikes more frequent after unusually wet months?** This project uses your actual CSV files, pandas, and matplotlib. It does not use machine learning or try to prove that rainfall causes price changes.

## Team

- Tsewang Namgyal — 25B0986
- Vadlamudi Lokesh — 25B1006
- Bharadhwaj Torati — 25B1073
- Bharat Chandra — 25B1086

## Installation

You already have a Python virtual environment, so activate it if needed. From the `Team-20` root:

```bash
python -m pip install -r requirements.txt
```

No R is needed **when the CSVs already exist**. To check whether rainfall CSVs are present:

```bash
bash extract.sh
```

```bash
python onion_analysis.py
```

The defaults are **State/UT = Andhra Pradesh**, **District = Kurnool**, and nearby **latitude 15.83, longitude 78.05**, because those are a concrete district and price example you supplied.

If you want to study a different district, change **all four matching settings**:

```bash
python onion_analysis.py --state Maharashtra --district Nashik --latitude 20.0 --longitude 73.8
```

If `Nashik` is not how the district is spelled in your CSV, use the exact spelling shown in its `District` column. The coordinates are approximate and must describe the same place as the district; otherwise the comparison is misleading.

The script reads all five rainfall years **in chunks**, keeping only the requested nearby grid point. This avoids filling RAM with tens of millions of rainfall rows.

Output in `results/`:

| File | What it shows |
|---|---|
| `monthly_results.csv` | One row per month: price, price change, rainfall, wet/normal/dry label |
| `spike_rates.csv` | Count of wet and normal months and their price-spike rates |
| `summary.txt` | Simple written result and important limitations |
| `onion_prices.png` | Monthly median price line plot |
| `monthly_rainfall.png` | Rainfall line plot |
| `spike_comparison.png` | Percentage of months with price spikes after wet vs normal months |
| `rainfall_vs_price.png` | Rainfall level compared with percentage price change |

1. **Daily district price:** median of that day's `Modal Price` rows; **monthly price:** median of the daily values in that month.
2. **Monthly rainfall:** sum of valid daily rainfall at the nearest 0.25° grid point. Months with fewer than 20 observed days are skipped.
3. **Typical rainfall:** average rainfall for the **same calendar month** across the available years (e.g. January compared to other Januaries). This is a rough baseline, **not official historical IMD normal rainfall**.
4. **Unusually wet:** at least 120% of the corresponding month's typical rainfall. **Normal:** 80% to less than 120%. Dry months and calendar months whose baseline is less than 10 mm are excluded from the wet-vs-normal comparison.
5. **Price spike:** monthly median onion price increased by **20% or more** from the preceding month.
6. By default compare **last month's rain** with **this month's price change**. Try same-month rainfall with `--lag 0` or rainfall two months earlier with `--lag 2`.
7. Count how frequently a price spike followed wet months and normal months.

Example options:

```bash
python onion_analysis.py --lag 0 --spike-threshold 15
```

**Interpret carefully:** this is a small observational analysis. Rainfall at one grid point is not district-wide rainfall. Price data may mix different mandis within the district. Rainfall, harvest seasons, storage, transportation, and market factors all matter. A higher spike percentage after wet months does **not** prove a causal relationship.