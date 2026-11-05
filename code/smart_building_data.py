"""
smart_building_data.py
======================
Shared data-loading and cleaning module for Module 2 (IJC445 Data
Visualisation) and Module 3 (IJC437 Introduction to Data Science).

Data source : Gomes, L., Pinto, T., & Vale, Z. (2022). A full-year data
              regarding a smart building [Data set]. Zenodo.
              https://doi.org/10.5281/zenodo.6778782  (licence CC BY 4.0)

Structure of the workbook `dataset.xlsx` (10 sheets, 5-minute resolution, 365 days):
  - building_energy : building-level consumption (W) and PV generation (W)
  - building_sensor : building-level temperature (°C)
  - zone#k_energy   : power/voltage/current per load (HVAC, light, sockets) for zone k
  - zone#k_sensor   : lamp intensity, temperature, humidity for zone k (k = 1..3)

Important notes from the data provider (Zenodo):
  * The data are raw and untreated; there are no missing periods, but a
    "fixed" zero value indicates a system failure (zero voltage = zone error).
  * The `time` column only contains the time of day, WITHOUT dates. Row order
    is assumed to be chronological; 105,120 rows = 365 days x 288 five-minute
    intervals.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# File locations
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
# Primary location: <repository root>/data/dataset.xlsx (works from any working directory)
DEFAULT_PATH = os.path.normpath(os.path.join(HERE, "..", "data", "dataset.xlsx"))
_LOCAL_COPY = os.path.normpath(
    os.path.join(HERE, "..", "..", "3. INTRODUCTION TO DATA SCIENCE", "dataset.xlsx")
)
if not os.path.exists(DEFAULT_PATH) and os.path.exists(_LOCAL_COPY):
    DEFAULT_PATH = _LOCAL_COPY                 # fallback for the original coursework folder

INTERVALS_PER_DAY = 288          # 24 hours x 12 five-minute intervals
INTERVAL_HOURS = 5 / 60          # interval length in hours (for W -> Wh)
STALE_RUN_INTERVALS = 12         # >= 12 identical consecutive readings (1 h) = stuck reading

# Day-of-week positions inferred from the 7-day periodicity of daily energy.
# Day index 0 behaves like a working day; positions (day mod 7) == 4 and 5 have
# much lower consumption and are interpreted as the weekend.
WEEKEND_POSITIONS = (4, 5)
DOW_LABELS = {0: "Tue", 1: "Wed", 2: "Thu", 3: "Fri", 4: "Sat", 5: "Sun", 6: "Mon"}

# Load-type names used throughout both modules
LOAD_HVAC, LOAD_LIGHT, LOAD_SOCKETS = "HVAC", "Lighting", "Sockets"

CACHE_DIR = os.path.join(HERE, "cache")   # pickle cache so the ~40 s Excel read happens once


@lru_cache(maxsize=None)
def _excel(path: str = DEFAULT_PATH) -> pd.ExcelFile:
    """Open the workbook once (cached) because the file is large."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Dataset not found at {path}\n"
            "Download dataset.xlsx from https://doi.org/10.5281/zenodo.6778782 "
            "and place it in the data/ folder of this repository."
        )
    return pd.ExcelFile(path)


def _cached(name: str, builder):
    """Return a DataFrame from the pickle cache; build and store it if absent."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    fp = os.path.join(CACHE_DIR, f"{name}.pkl")
    if os.path.exists(fp):
        return pd.read_pickle(fp)
    df = builder()
    df.to_pickle(fp)
    return df


def _add_time_index(df: pd.DataFrame) -> pd.DataFrame:
    """Add day index, slot, hour and the inferred day-of-week position.

    Timestamps in the data mark the END of each interval (00:05 = interval
    00:00-00:05), so slot 0 of every day represents hour 0.
    """
    n = len(df)
    df = df.copy()
    df["day"] = np.arange(n) // INTERVALS_PER_DAY            # 0..364
    df["slot"] = np.arange(n) % INTERVALS_PER_DAY            # 0..287
    df["hour"] = (df["slot"] * 5) // 60                      # 0..23
    df["dow_pos"] = df["day"] % 7                            # position within the 7-day cycle
    df["is_weekend"] = df["dow_pos"].isin(WEEKEND_POSITIONS)
    df["dow_label"] = df["dow_pos"].map(DOW_LABELS)
    return df


def load_building(path: str = DEFAULT_PATH) -> pd.DataFrame:
    """Load building-level energy + temperature (cached); see `_build_building`."""
    return _cached("building", lambda: _build_building(path))


def _build_building(path: str = DEFAULT_PATH) -> pd.DataFrame:
    """Load building-level energy + temperature and flag invalid intervals.

    Output columns:
      consumption_w, generation_w, temperature_c, day, slot, hour, dow_pos,
      is_weekend, dow_label, cons_zero, cons_stale, cons_valid, pv_valid
    Cleaning rules:
      * consumption == 0 W is treated as a sensor failure (the building base
        load is ~2-3 kW and never zero); converted to NaN and recorded in
        `cons_valid` / `cons_zero`.
      * A run of identical consumption values lasting >= 1 hour is treated as a
        stuck (stale) reading (`cons_stale`); also converted to NaN.
      * Days with daily PV energy < 1 kWh are treated as PV-meter failures (a
        7.5 kWp array cannot produce ~0 for a whole day); `pv_valid` = False.
      * An isolated exact 0 °C on the building temperature sensor is treated
        as NaN (its neighbours are far from zero).
    """
    xl = _excel(path)
    energy = xl.parse("building_energy")
    sensor = xl.parse("building_sensor")
    df = pd.DataFrame(
        {
            "time": energy["time"],
            "consumption_w": energy["consumption (w)"].astype(float),
            "generation_w": energy["generation (w)"].astype(float),
            "temperature_c": sensor["temperature (˚C)"].astype(float),
        }
    )
    df = _add_time_index(df)

    # --- consumption: zero = system failure ------------------------------ #
    is_zero = df["consumption_w"] <= 0
    # --- consumption: "frozen" values (identical for >= 1 h) = stuck reading #
    # A building meter never stays constant to the watt for a full hour; long
    # identical runs (e.g. days 95-96 read 6,135 W all day) are interpreted as
    # readings that were not updated (stale readings).
    run_id = (df["consumption_w"] != df["consumption_w"].shift()).cumsum()
    run_len = df.groupby(run_id)["consumption_w"].transform("size")
    is_stale = run_len >= STALE_RUN_INTERVALS
    df["cons_zero"] = is_zero
    df["cons_stale"] = is_stale & ~is_zero
    df["cons_valid"] = ~(is_zero | is_stale)
    df.loc[~df["cons_valid"], "consumption_w"] = np.nan

    # --- PV: days with ~0 energy = PV meter down -------------------------- #
    pv_daily_kwh = df.groupby("day")["generation_w"].sum() * INTERVAL_HOURS / 1000
    bad_pv_days = pv_daily_kwh[pv_daily_kwh < 1.0].index
    df["pv_valid"] = ~df["day"].isin(bad_pv_days)

    # --- temperature: isolated exact zero = sensor glitch ------------------ #
    zero_t = df["temperature_c"] == 0
    neighbour_ok = (df["temperature_c"].shift(1).abs() > 2) | (
        df["temperature_c"].shift(-1).abs() > 2
    )
    df.loc[zero_t & neighbour_ok, "temperature_c"] = np.nan

    return df


def load_zone_energy(zone: int, path: str = DEFAULT_PATH) -> pd.DataFrame:
    """Load sheet `zone#k_energy` (cached); see `_build_zone_energy`."""
    return _cached(f"zone{zone}_energy", lambda: _build_zone_energy(zone, path))


def _build_zone_energy(zone: int, path: str = DEFAULT_PATH) -> pd.DataFrame:
    """Load sheet `zone#k_energy`, which has a two-row header.

    Returns a long-format table with one row per load and interval:
      day, slot, hour, zone, load, load_type, power_w, voltage_v, current_a,
      valid (voltage > 0).
    """
    raw = _excel(path).parse(f"zone#{zone}_energy", header=None)
    top = raw.iloc[0].ffill()
    sub = raw.iloc[1]
    body = raw.iloc[2:].reset_index(drop=True)

    records = []
    for col_idx in range(1, raw.shape[1], 3):
        load_name = str(top[col_idx]).strip()           # e.g. "zone 1 - HVAC#1"
        block = body.iloc[:, col_idx : col_idx + 3].apply(pd.to_numeric, errors="coerce")
        block.columns = ["power_w", "voltage_v", "current_a"]
        block = block.copy()
        block["load"] = load_name
        short = load_name.split(" - ")[-1]
        block["load_type"] = (
            LOAD_HVAC if short.upper().startswith("HVAC")
            else LOAD_LIGHT if short.lower().startswith("light")
            else LOAD_SOCKETS
        )
        block["zone"] = zone
        block["row"] = np.arange(len(block))
        records.append(block)

    long = pd.concat(records, ignore_index=True)
    long["day"] = long["row"] // INTERVALS_PER_DAY
    long["slot"] = long["row"] % INTERVALS_PER_DAY
    long["hour"] = (long["slot"] * 5) // 60
    long["valid"] = long["voltage_v"] > 0          # zero voltage = zone error
    long.loc[~long["valid"], "power_w"] = np.nan
    return long.drop(columns="row")


def load_all_zones(path: str = DEFAULT_PATH) -> pd.DataFrame:
    """Concatenate all five zones into one long table."""
    return pd.concat([load_zone_energy(z, path) for z in range(1, 6)], ignore_index=True)


def hourly_building(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Hourly aggregation (mean power in kW, temperature, PV) -> 8,760 rows."""
    if df is None:
        df = load_building()
    grp = df.groupby(["day", "hour"], as_index=False).agg(
        consumption_kw=("consumption_w", lambda s: s.mean() / 1000),
        generation_kw=("generation_w", lambda s: s.mean() / 1000),
        temperature_c=("temperature_c", "mean"),
        n_valid=("cons_valid", "sum"),
        pv_valid=("pv_valid", "all"),
    )
    grp["dow_pos"] = grp["day"] % 7
    grp["is_weekend"] = grp["dow_pos"].isin(WEEKEND_POSITIONS)
    grp["dow_label"] = grp["dow_pos"].map(DOW_LABELS)
    grp["t_index"] = grp["day"] * 24 + grp["hour"]
    return grp


def daily_profiles(hourly: pd.DataFrame, min_valid_hours: int = 24) -> pd.DataFrame:
    """Day x 24-hour matrix (kW). Days with incomplete hours are dropped."""
    piv = hourly.pivot(index="day", columns="hour", values="consumption_kw")
    complete = piv.notna().sum(axis=1) >= min_valid_hours
    return piv[complete]


if __name__ == "__main__":          # quick self-test
    b = load_building()
    print(b.head())
    print("invalid consumption intervals:", (~b.cons_valid).sum())
    print("invalid PV days:", b.loc[~b.pv_valid, "day"].nunique())
    z = load_all_zones()
    print(z.groupby(["zone", "load_type"])["power_w"].mean().round(0))
