import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib.colors import PowerNorm
import numpy as np

district_coords = pd.read_csv("data/Ind_adm2_Points.csv")
onion_prices = pd.read_csv("data/onionprices.csv")

centroids = district_coords.groupby("Ind_adm2_ID", as_index=False).agg(
    {
        **{
            col: "first"
            for col in district_coords.columns
            if col not in ["Latitude", "Longitude"]
        },
        "Latitude": "mean",
        "Longitude": "mean",
    }
)
centroids["Latitude"] = round(centroids["Latitude"] * 4) / 4
centroids["Longitude"] = round(centroids["Longitude"] * 4) / 4
print(centroids)

onion_prices = onion_prices.merge(
    centroids[["District", "Latitude", "Longitude"]], on="District", how="left"
)

print(onion_prices.head(100))

# Convert columns to appropriate types
onion_prices["Price Date"] = pd.to_datetime(
    onion_prices["Price Date"], format="%d-%m-%Y"
)
onion_prices["Modal Price"] = pd.to_numeric(
    onion_prices["Modal Price"], errors="coerce"
)

# Sort chronologically within each district
onion_prices = onion_prices.sort_values(["State/UT", "District", "Price Date"])

# Get previous available observation for each district
groups = onion_prices.groupby(["State/UT", "District"])

prev_price = groups["Modal Price"].shift(1)
prev_date = groups["Price Date"].shift(1)

# Check whether the previous observation is exactly one calendar day earlier
valid = (
    (onion_prices["Price Date"] - prev_date == pd.Timedelta(days=1))
    & prev_price.notna()
    & (prev_price != 0)
)

# Calculate percentage increment
onion_prices["Price Increment (%)"] = (
    ((onion_prices["Modal Price"] - prev_price) / prev_price * 100)
    .where(valid)
    .astype("Float64")
)

# Optional: restore chronological ordering
onion_prices = onion_prices.reset_index(drop=True)

print(onion_prices.head(500))
onion_prices.to_csv("onions.csv")
