#!/usr/bin/env bash
# Optional helper: copy your existing rainfall CSVs into the expected folder.
# Usage: bash extract.sh /path/to/your/rainfall_csv_folder
# If CSVs are already in data/rainfall/data/, no action is needed.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$ROOT/data/rainfall/data"
mkdir -p "$DEST"
shopt -s nullglob

if [[ $# -gt 1 ]]; then
    echo "Usage: bash extract.sh [folder_with_rainfall_csvs]" >&2
    exit 1
fi

if [[ $# -eq 1 ]]; then
    SOURCE="$1"
    if [[ ! -d "$SOURCE" ]]; then
        echo "Folder not found: $SOURCE" >&2
        exit 1
    fi
    csvs=("$SOURCE"/*.csv)
    if (( ${#csvs[@]} == 0 )); then
        echo "No CSV files in: $SOURCE" >&2
        exit 1
    fi
    for file in "${csvs[@]}"; do
        if [[ "$(cd "$(dirname "$file")" && pwd)" != "$DEST" ]]; then
            cp -n "$file" "$DEST/"
        fi
    done
    echo "Rainfall CSVs are ready in: $DEST"
else
    csvs=("$DEST"/*.csv)
    if (( ${#csvs[@]} > 0 )); then
        echo "Already found ${#csvs[@]} rainfall CSV(s) in: $DEST"
    else
        # Keep compatibility with the original project if its R converter is available.
        NC_DIR="$ROOT/data/rainfall/nc"
        R_CONVERTER="$ROOT/data/rainfall/extract_nc.R"
        nc_files=("$NC_DIR"/*.nc)
        if (( ${#nc_files[@]} > 0 )) && [[ -f "$R_CONVERTER" ]]; then
            if ! command -v Rscript >/dev/null 2>&1; then
                echo "NetCDF files found, but Rscript is not installed." >&2
                exit 1
            fi
            echo "Converting ${#nc_files[@]} NetCDF file(s) using the existing R converter..."
            Rscript "$R_CONVERTER"
            csvs=("$DEST"/*.csv)
            if (( ${#csvs[@]} == 0 )); then
                echo "The R converter ran but did not create any CSV files in $DEST" >&2
                exit 1
            fi
            echo "Created ${#csvs[@]} CSV file(s)."
        else
            echo "Put your existing rainfall CSVs in: $DEST"
            echo "Or run: bash extract.sh /path/to/your/csv_folder"
            echo "If your dataset is NetCDF (.nc), keep your old data/rainfall/extract_nc.R converter."
            exit 1
        fi
    fi
fi
