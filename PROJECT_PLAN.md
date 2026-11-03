# Simple project plan

## Question
Do unusually wet months tend to be followed by sharp increases in onion prices?

## Data
- Daily gridded rainfall (2021-2025 CSV files) with `LONGITUDE`, `LATITUDE`, `TIME`, `RAINFALL`.
- Daily onion prices with `State/UT`, `District`, `Modal Price`, `Price Date`.

## Steps
1. Choose one district, such as Kurnool, and provide its approximate latitude/longitude.
2. Find the nearest rainfall grid cell (0.25 degrees) and total the daily rainfall by month.
3. Take the monthly median of daily onion prices for that district.
4. Define unusually wet months using the same calendar month's average rain in 2021-2025. Define a price spike as an increase >=20%.
5. Compare the proportion of months with spikes after wet and normal months, and draw charts.

## Limitations
- Nearest grid point is not exact district rainfall.
- Monthly rainfall baselines from 2021-2025 are not official historical rainfall normals.
- District median prices may combine multiple mandis.
- There may be few comparable months or price spikes, so conclusions are tentative.
- Association is not proof that heavy rainfall causes onion prices to rise.

## Deliverables
`results/monthly_results.csv`, `results/spike_rates.csv`, `results/summary.txt`, and four charts; optional India-wide rainfall charts in `plots/`.
