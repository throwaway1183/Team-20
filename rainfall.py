import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib.colors import PowerNorm
import numpy as np

# Collect all the rainfall data of 2025

files = sorted(Path("data/rainfall/data").glob("RF*_ind*_rfp25.csv"))

df2025 = pd.concat([pd.read_csv(file) for file in files], ignore_index=True)

df2025 = df2025.dropna(subset=["LATITUDE", "LONGITUDE", "RAINFALL"])

print("Files combined:", len(files))
print("Total rows:", len(df2025))

# store location specific mean rainfall
avgrainfall = df2025.groupby(["LATITUDE", "LONGITUDE"])["RAINFALL"].mean().reset_index()
stdrainfall = df2025.groupby(["LATITUDE", "LONGITUDE"])["RAINFALL"].std().reset_index()


max_avg_rainfall = avgrainfall["RAINFALL"].max()

# make a heatmap based on the location and mean rainfall throughout the year
heatmap = (
    avgrainfall.pivot(index="LATITUDE", columns="LONGITUDE", values="RAINFALL")
    .sort_index()
    .sort_index(axis=1)
)
values = heatmap.to_numpy(dtype=float)
vmax = np.nanpercentile(values, 99)

# plot the heatmap
plt.figure(1, figsize=(12, 8))
plt.pcolormesh(
    heatmap.columns,
    heatmap.index,
    heatmap.values,
    shading="auto",
    cmap="inferno",
    norm=PowerNorm(gamma=0.5, vmin=0, vmax=vmax),
)

plt.colorbar(label="Average Rainfall")
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title("Average Rainfall Across India")

plt.savefig("plots/avgrainfall.png")
plt.show()


# choose a specific location and plot it's temporal variation of percentage excess with respect to its mean
lat = 20
lon = 80

location_data = df2025[
    (df2025["LATITUDE"] == lat) & (df2025["LONGITUDE"] == lon)
].copy()
avg = location_data["RAINFALL"].mean()
std = location_data["RAINFALL"].std()

location_data["PCT_EXCESS"] = (location_data["RAINFALL"] - avg) / std

location_data["TIME"] = pd.to_datetime(location_data["TIME"])
location_data = location_data.sort_values("TIME")


plt.figure(2, figsize=(14, 5))
plt.plot(location_data["TIME"], location_data["PCT_EXCESS"])

plt.axhline(0, color="black", linestyle="--")
plt.xlabel("Date")
plt.ylabel("Percentage Excess (%)")
plt.title(f"Rainfall Deviation at ({lat}, {lon})")
plt.grid(True)
plt.savefig("plots/pctexcess.png")
plt.show()

# For every position make a heatmap of how many days there is an abnormal amount of rainfall
# We shall consider that a day has an abnormal amount of rainfall in that region if the rainfall on that day is atleast 3 sample standard deviations above the sample mean of rainfall in that region

# plot the heatmap of number of abnormal days with rainfall per region
CONST = 3

df2025["W"] = df2025["RAINFALL"] > df2025.groupby(["LATITUDE", "LONGITUDE"])[
    "RAINFALL"
].transform("mean") + CONST * df2025.groupby(["LATITUDE", "LONGITUDE"])[
    "RAINFALL"
].transform(
    "std"
).astype(
    int
)

spatial_W = df2025.groupby(["LATITUDE", "LONGITUDE"], as_index=False)["W"].sum()

heatmap = (
    spatial_W.pivot(index="LATITUDE", columns="LONGITUDE", values="W")
    .sort_index()
    .sort_index(axis=1)
)

# plot the heatmap
plt.figure(3, figsize=(12, 8))
plt.pcolormesh(
    heatmap.columns, heatmap.index, heatmap.values, shading="auto", cmap="inferno"
)

plt.colorbar(label="W")
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title("W Across India")

plt.savefig("plots/abnormalrainfall.png")
plt.show()
