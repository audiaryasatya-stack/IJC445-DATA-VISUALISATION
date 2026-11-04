# IJC445-DATA-VISUALISATION
Smart Building Energy Consumption and PV Generation Visualisation

This project explores energy consumption and photovoltaic (PV) generation in a smart research building in Porto, Portugal, using the RETINA/GECAD dataset (Gomes et al., 2022).

**Research question:** When and where is energy consumed in the building, and how well does PV generation align with its consumption patterns?

The project presents four Python-generated visualisations examining hourly consumption, annual energy patterns, energy use by zone and load type, and the relationship between daily energy consumption and temperature.

**Key messages:**
- Weekday consumption peaks at approximately 6.0 kW, while the building maintains a base load of approximately 2.9 kW.
- PV generation peaks at approximately 2.7 kW, remaining below the building's average base load.
- Socket loads account for approximately 67% of annual mean power, with Zone 2 (server room) contributing approximately 46%.
- Daily energy consumption is positively associated with temperature on both weekdays and weekends.

## Composite Visualisation

figures/module2/composite.png 

The composite contains four charts:
- **Chart A:** Hourly electricity consumption and PV generation.
- **Chart B:** Heatmap of hourly electricity consumption across 365 days.
- **Chart C:** Annual mean power by building zone and load type.
- **Chart D:** Daily energy consumption against daily mean temperature.

## Repository Contents

- `code/module2_composite.py` – Main visualisation script.
- `code/smart_building_data.py` – Data loading and cleaning functions.
- `figures/module2/` – Composite visualisation in PNG and PDF formats.
- `results/module2/` – Calculated statistics in JSON format.

## Dataset

Gomes, L., Pinto, T., & Vale, Z. (2022). *A full-year data regarding a smart building* [Data set]. Zenodo.

https://doi.org/10.5281/zenodo.6778782

## Tools and Technologies

Python 3.13, pandas, NumPy and matplotlib.

## Running the Code

Install the required packages:

```bash
pip install -r requirements.txt
```
Place `dataset.xlsx` in the `data/` folder, then run:

```bash
python code/module2_composite.py
```

The scripts generate the composite visualisation and the corresponding statistical results.
