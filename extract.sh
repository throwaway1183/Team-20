#!/usr/bin/env bash
# run_extract.sh
# Lives in the home directory. Runs data/rainfall/extract_nc.R to convert every
# .nc file in data/rainfall/nc/ into CSV files in data/rainfall/data/.
#
# Usage (from anywhere):  bash ~/run_extract.sh

set -euo pipefail

# Resolve paths relative to this script's location (the home directory)
HOME_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIN_DIR="${HOME_DIR}/data/rainfall"
NC_DIR="${RAIN_DIR}/nc"
OUT_DIR="${RAIN_DIR}/data"
R_SCRIPT="${RAIN_DIR}/extract_nc.R"

# ---- sanity checks ----------------------------------------------------------
if ! command -v Rscript >/dev/null 2>&1; then
  echo "Error: Rscript not found. Please install R first." >&2
  exit 1
fi

if [[ ! -d "${NC_DIR}" ]]; then
  echo "Error: input directory not found: ${NC_DIR}" >&2
  exit 1
fi

if [[ ! -f "${R_SCRIPT}" ]]; then
  echo "Error: R script not found: ${R_SCRIPT}" >&2
  exit 1
fi

# Count .nc files (case-insensitive)
NC_COUNT=$(find "${NC_DIR}" -maxdepth 1 -type f -iname '*.nc' | wc -l)
if [[ "${NC_COUNT}" -eq 0 ]]; then
  echo "Error: no .nc files found in ${NC_DIR}" >&2
  exit 1
fi

# ---- make sure the output directory exists ----------------------------------
mkdir -p "${OUT_DIR}"

# ---- run the extraction -----------------------------------------------------
echo "Found ${NC_COUNT} .nc file(s) in ${NC_DIR}"
Rscript "${R_SCRIPT}"

CSV_COUNT=$(find "${OUT_DIR}" -maxdepth 1 -type f -name '*.csv' | wc -l)
echo "Finished. ${CSV_COUNT} CSV file(s) now in ${OUT_DIR}"