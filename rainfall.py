import pandas as pd
import matplotlib.pyplot as plt

# Collect all the rainfall data of 2025
df2025 = pd.read_csv("data/rainfall/data/RF25_ind2025_rfp25.csv")
df2025 = df2025.dropna()

# store location specific mean rainfall
avgrainfall = df2025.groupby(["LATITUDE", "LONGITUDE"])["RAINFALL"].mean().reset_index()

max_avg_rainfall = avgrainfall["RAINFALL"].max()

# make a heatmap based on the location and mean rainfall throughout the year
heatmap = (
    avgrainfall.pivot(index="LATITUDE", columns="LONGITUDE", values="RAINFALL")
    .sort_index()
    .sort_index(axis=1)
)

# plot the heatmap
plt.figure(1, figsize=(12, 8))
plt.pcolormesh(
    heatmap.columns, heatmap.index, heatmap.values, shading="auto", cmap="YlGnBu"
)

plt.colorbar(label="Average Rainfall")
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title("Average Rainfall Across India")

plt.savefig("plots/avgrainfall.png")
plt.show()


# choose a specific location and plot it's temporal variation of percentage excess with respect to its mean
lat = 17.5
lon = 74.5

location_data = df2025[
    (df2025["LATITUDE"] == lat) & (df2025["LONGITUDE"] == lon)
].copy()
avg = location_data["RAINFALL"].mean()

location_data["PCT_EXCESS"] = (
    ((location_data["RAINFALL"] - avg) / avg) * 100 * avg / max_avg_rainfall
)

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
