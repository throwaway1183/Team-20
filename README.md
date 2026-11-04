# Team 20 - Does Rain Make Onions Cry?

**CS215 Data Analysis and Interpretation**

We explore one question: **Are onion-price spikes more frequent after unusually wet months?** This project uses CSV files, pandas, matplotlib and R. 

## Team

- Tsewang Namgyal — 25B0986
- Vadlamudi Lokesh — 25B1006
- Bharadhwaj Torati — 25B1073
- Bharat Chandra — 25B1086


## Quick start

Run these commands from the **repository root**.

```bash
# 1. Create a Python environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install Python dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. Extract rainfall CSV files
bash extract.sh 
# Or, if CSVs are already in data/rainfall/data/: ignore

# 4. Run the analysis (explicit project configuration)
python onion_analysis.py
```

Open **`results/district_report.html`** in a browser to explore the results. The script also writes a copy of `district_report.html` to the repository root.



## Repository layout

The scripts expect this layout:

```text
.
├── README.md
├── requirements.txt
├── extract.sh                    # Rainfall CSV setup / optional NetCDF conversion
├── onion_analysis.py             # Main district-level rainfall/price analysis
├── rainfall.py                   # Standalone rainfall plots for a grid location
├── data/
│   ├── prices/
│   │   └── onion_prices.csv       # Required onion-price dataset
│   └── rainfall/
│       ├── data/
│       │   ├── RF25_ind2021_rfp25.csv
│       │   ├── RF25_ind2022_rfp25.csv
│       │   ├── ...
│       │   └── RF25_ind2025_rfp25.csv
│       ├── nc/                    # source .nc files
│       └── extract_nc.R           # R conversion script
├── results/                       # Created by onion_analysis.py
└── plots/                         # Created by rainfall.py
```

The `.nc` files and `extract_nc.R` are **optional** and are only needed when converting rainfall data from NetCDF to CSV. The files shown for 2021–2025 illustrate the dataset naming convention.

## Requirements

- **Python 3.9+ recommended** with `pip` and `venv`.
- Dependencies listed in `requirements.txt`:
  - `pandas>=2.0`
  - `matplotlib>=3.7`
- **Bash** for `extract.sh` (Linux, macOS, Git Bash, or WSL).
- Enough disk space for rainfall CSVs, intermediate data, and generated results. Large inputs are read in chunks, though intermediate district data is also held in memory.
- **Optional:** R (`Rscript`) and the R packages used by your copy of `data/rainfall/extract_nc.R` if starting with NetCDF files. The earlier converter uses `ncdf4`; inspect the converter for any additional package imports. `libnetcdf-dev` may be needed to install `ncdf4` on Linux.

On Windows, activate a virtual environment with `.venv\Scripts\activate` in Command Prompt or `.venv\Scripts\Activate.ps1` in PowerShell. Use Git Bash or WSL for the extraction script.
