"""
module2_composite.py
====================
IJC445 Data Visualisation -- Composite Visualisation

Question addressed by the composite:
    "When and where is energy consumed in this smart research building, and
     how well does PV generation line up with that rhythm of consumption?"

The composite is ONE figure made of four charts that are read together:
  (a) Chart A  hourly profile of consumption (inferred weekdays vs weekends)
               and PV generation             -> WHEN within the day
  (b) Chart B  day x hour heatmap of consumption over the whole year
               -> WHEN within the year (weekly rhythm, holidays, sensor
                  outages, base-load change)
  (c) Chart C  average load by zone and load type -> WHERE / WHICH load
  (d) Chart D  daily energy vs daily mean temperature -> environmental DRIVER

Code flow
---------
  1. Load & clean the data through the shared module `smart_building_data`
     (zeros and frozen readings -> NaN, PV-meter failure days flagged,
     inferred weekday/weekend labels).
  2. Compute the summary tables each chart needs (sections "Chart A" .. "Chart D").
  3. Build the 2 x 2 composite with matplotlib GridSpec, one block per chart,
     sharing a single colour vocabulary (Okabe-Ito palette, colour-blind safe).
  4. Save the composite (PNG + PDF) and the quoted numbers (facts.json).

All charts are produced programmatically; nothing is drawn by hand.
Run:  python module2_composite.py
"""

from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import gridspec
from matplotlib.colors import LinearSegmentedColormap

import smart_building_data as sbd

HERE = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.join(HERE, "..", "figures", "module2")
RES_DIR = os.path.join(HERE, "..", "results", "module2")
os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(RES_DIR, exist_ok=True)

# --------------------------------------------------------------------------- #
# Colour vocabulary (Okabe & Ito, 2008) -- identical meaning in every chart
# --------------------------------------------------------------------------- #
C_CONS = "#0072B2"        # consumption, weekdays
C_WEEKEND = "#56B4E9"     # consumption, weekends (inferred)
C_PV = "#E69F00"          # photovoltaic generation
C_LOAD = {sbd.LOAD_SOCKETS: "#CC79A7", sbd.LOAD_HVAC: "#D55E00", sbd.LOAD_LIGHT: "#009E73"}
HATCH = {sbd.LOAD_SOCKETS: "..", sbd.LOAD_HVAC: "", sbd.LOAD_LIGHT: "//"}   # secondary encoding
GRID = dict(color="#dddddd", linewidth=0.6)
# single-hue sequential ramp (white -> consumption blue) for the heatmap: monotonic lightness
CMAP_SEQ = LinearSegmentedColormap.from_list("cons_seq", ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"])

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#666666",
        "legend.frameon": False,
        "legend.fontsize": 8,
        "savefig.dpi": 220,
        "savefig.bbox": "tight",
    }
)

# =========================================================================== #
# 1. DATA
# =========================================================================== #
print(">> loading data ...")
raw = sbd.load_building()            # 5-minute building data, cleaned
zones = sbd.load_all_zones()         # per-load data for the five zones
hourly = sbd.hourly_building(raw)    # hourly means (8,760 rows)
FACTS: dict = {}                     # numbers quoted in the report

# --- Chart A: daily profile ---------------------------------------------- #
# Mean and inter-quartile range of consumption for every hour, split by the
# inferred day type; the PV profile uses only days with a working PV meter.
full_hours = hourly[hourly["n_valid"] == 12]
prof = (
    full_hours.groupby(["is_weekend", "hour"])["consumption_kw"]
    .agg(mean="mean", q25=lambda s: s.quantile(0.25), q75=lambda s: s.quantile(0.75))
    .reset_index()
)
pv_prof = hourly[hourly["pv_valid"]].groupby("hour")["generation_kw"].mean()
wk = prof[~prof.is_weekend].set_index("hour")
we = prof[prof.is_weekend].set_index("hour")
FACTS["weekday_peak_kw"] = round(wk["mean"].max(), 2)
FACTS["weekday_peak_hour"] = int(wk["mean"].idxmax())
FACTS["weekend_peak_kw"] = round(we["mean"].max(), 2)
FACTS["night_base_kw"] = round(wk["mean"].loc[[1, 2, 3, 4]].mean(), 2)
FACTS["pv_peak_kw"] = round(pv_prof.max(), 2)
FACTS["pv_peak_hour"] = int(pv_prof.idxmax())
FACTS["pv_over_weekend_hours"] = [int(h) for h in pv_prof.index if pv_prof[h] > we["mean"][h]]

# --- Chart B: day x hour heatmap ----------------------------------------- #
heat = hourly.pivot(index="hour", columns="day", values="consumption_kw")   # 24 x 365 matrix
heat_arr = np.ma.masked_invalid(heat.values)                                # NaN -> masked (grey)
FACTS["heat_missing_cells"] = int(np.isnan(heat.values).sum())

# --- Chart C: load composition ------------------------------------------- #
# Mean power of every individual load, then summed per (zone, load type).
per_load = zones.groupby(["zone", "load_type", "load"])["power_w"].mean()
load_mean = per_load.groupby(["zone", "load_type"]).sum().unstack().fillna(0) / 1000
load_mean = load_mean[[sbd.LOAD_SOCKETS, sbd.LOAD_HVAC, sbd.LOAD_LIGHT]]
zone_tot = load_mean.sum(axis=1)
FACTS["zone_total_kw"] = zone_tot.round(2).to_dict()
FACTS["share_type_pct"] = (100 * load_mean.sum() / load_mean.values.sum()).round(1).to_dict()
FACTS["share_zone2_pct"] = round(100 * zone_tot[2] / zone_tot.sum(), 1)
FACTS["sum_zones_kw"] = round(zone_tot.sum(), 2)
FACTS["building_mean_kw"] = round(raw["consumption_w"].mean() / 1000, 2)

# --- Chart D: daily energy vs temperature -------------------------------- #
daily = hourly.groupby("day").agg(
    cons_kwh=("consumption_kw", "sum"), temp=("temperature_c", "mean"),
    n_valid=("n_valid", "sum"), is_weekend=("is_weekend", "first"),
)
daily = daily[(daily["n_valid"] == sbd.INTERVALS_PER_DAY)].dropna(subset=["temp"])   # complete days only
fit = {}
for flag in (False, True):          # simple linear regression per day type
    sub = daily[daily.is_weekend == flag]
    slope, intercept = np.polyfit(sub["temp"], sub["cons_kwh"], 1)
    r = np.corrcoef(sub["temp"], sub["cons_kwh"])[0, 1]
    fit[flag] = dict(slope=slope, intercept=intercept, r=r, n=len(sub))
FACTS["fit_weekday"] = {k: round(float(v), 3) for k, v in fit[False].items()}
FACTS["fit_weekend"] = {k: round(float(v), 3) for k, v in fit[True].items()}

# =========================================================================== #
# 2. COMPOSITE FIGURE (2 rows x 2 columns)
# =========================================================================== #
print(">> drawing composite ...")
fig = plt.figure(figsize=(12.5, 8.2))
gs = gridspec.GridSpec(2, 2, width_ratios=[1, 1.35], height_ratios=[1, 1], hspace=0.5, wspace=0.22)

# ---------------------------- (a) Chart A ------------------------------- #
ax = fig.add_subplot(gs[0, 0])
# ribbons = inter-quartile range (uncertainty), lines = hourly means
ax.fill_between(wk.index, wk["q25"], wk["q75"], color=C_CONS, alpha=0.18, lw=0)
ax.fill_between(we.index, we["q25"], we["q75"], color=C_WEEKEND, alpha=0.22, lw=0)
ax.plot(wk.index, wk["mean"], color=C_CONS, lw=2.2, label="Consumption, weekdays")
ax.plot(we.index, we["mean"], color=C_WEEKEND, lw=2.2, ls="--", label="Consumption, weekends")
ax.plot(pv_prof.index, pv_prof.values, color=C_PV, lw=2.2, ls="-.", label="PV generation")
# selective direct labels
ax.annotate(f"peak {wk['mean'].max():.1f} kW (hour {wk['mean'].idxmax()})", (wk["mean"].idxmax(), wk["mean"].max()),
            xytext=(14, 14), textcoords="offset points", fontsize=8, color=C_CONS,
            arrowprops=dict(arrowstyle="-", color=C_CONS, lw=0.7))
ax.annotate(f"base load ≈ {FACTS['night_base_kw']:.1f} kW", (2.3, FACTS["night_base_kw"]), xytext=(0, -18),
            textcoords="offset points", fontsize=8, color="#444")
ax.annotate(f"PV max. {pv_prof.max():.1f} kW", (pv_prof.idxmax(), pv_prof.max()), xytext=(14, -16),
            textcoords="offset points", fontsize=8, color="#8a5a00",
            arrowprops=dict(arrowstyle="-", color=C_PV, lw=0.7))
ax.set_xlim(0, 23)
ax.set_xticks(range(0, 24, 3))
ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 3)])
ax.set_ylim(0, 7.3)                      # shared zero baseline for all three series
ax.set_xlabel("Hour of day")
ax.set_ylabel("Mean power (kW)")
ax.set_title("(a) Daily rhythm: consumption vs PV generation")
ax.legend(loc="upper left")
ax.grid(axis="y", **GRID)
ax.set_axisbelow(True)
ax.text(0, -0.33, "Ribbons = inter-quartile range (25–75 %). Day type inferred from\nthe 7-day periodicity (the dataset contains no dates).",
        transform=ax.transAxes, fontsize=7.5, color="#555")

# ---------------------------- (b) Chart B ------------------------------- #
ax = fig.add_subplot(gs[0, 1])
cmap = CMAP_SEQ.copy()
cmap.set_bad("#bdbdbd")                               # missing cells = neutral grey, not zero
im = ax.imshow(heat_arr, aspect="auto", origin="lower", cmap=cmap, vmin=0, vmax=8,
               extent=[-0.5, 364.5, -0.5, 23.5], interpolation="nearest")
ax.set_xlabel("Day index (0 = first recorded day; month labels are approximate)")
ax.set_ylabel("Hour of day")
ax.set_yticks([0, 6, 12, 18, 23])
ax.set_yticklabels(["00", "06", "12", "18", "23"])
month_start = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30])
ax.set_xticks(month_start)
ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
ax.tick_params(axis="x", length=2)
ax.set_title("(b) Hourly consumption across the year (day × hour)")
cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
cb.set_label("Mean hourly power (kW)")
cb.ax.tick_params(labelsize=8)
# structural annotation: base-load break + footnote
ax.axvline(295, color="#222", lw=1, ls=":")
ax.annotate("night base load drops\n≈ day 295 (server room)", xy=(295, 2.5), xytext=(-6, 0), textcoords="offset points",
            fontsize=7.5, color="#222", ha="right", va="center",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85))
ax.text(0, -0.33, "Light vertical columns = weekends & public holidays (7-day rhythm);\ngrey columns = sensor outages (missing values).",
        transform=ax.transAxes, fontsize=7.5, color="#555")
for s in ax.spines.values():
    s.set_visible(False)

# ---------------------------- (c) Chart C ------------------------------- #
ax = fig.add_subplot(gs[1, 0])
ylabels = [f"Zone {z}" + (" (server room)" if z == 2 else " (meeting room)" if z == 1 else "") for z in load_mean.index]
left = np.zeros(len(load_mean))
for lt in load_mean.columns:         # stacked horizontal bars, sockets first (common baseline)
    vals = load_mean[lt].values
    ax.barh(ylabels, vals, left=left, color=C_LOAD[lt], hatch=HATCH[lt], edgecolor="white", linewidth=1.2, height=0.62, label=lt)
    for i, v in enumerate(vals):     # value labels inside segments that are wide enough
        if v > 0.18:
            ax.text(left[i] + v / 2, i, f"{v:.2f}", ha="center", va="center", fontsize=7.5, color="#222",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    left += vals
for i, tot in enumerate(left):       # totals and shares at the end of each bar
    ax.text(tot + 0.03, i, f"{tot:.2f} kW ({100*tot/left.sum():.0f} %)", va="center", fontsize=8, color="#222")
ax.invert_yaxis()
ax.set_xlim(0, left.max() * 1.42)
ax.set_xlabel("Annual mean power (kW)")
ax.set_title("(c) Where energy is used: load by zone and type")
ax.legend(loc="lower right", title="Load type", title_fontsize=8)
ax.grid(axis="x", **GRID)
ax.set_axisbelow(True)
ax.text(0, -0.33, f"Full-year averages (including nights & weekends).\nSum of zones {left.sum():.2f} kW ≈ building meter {FACTS['building_mean_kw']:.2f} kW.",
        transform=ax.transAxes, fontsize=7.5, color="#555")

# ---------------------------- (d) Chart D ------------------------------- #
ax = fig.add_subplot(gs[1, 1])
xs = np.linspace(daily["temp"].min(), daily["temp"].max(), 50)
for flag, col, mk, lab in [(False, C_CONS, "o", "Weekdays"), (True, C_WEEKEND, "^", "Weekends/holidays (Sat–Sun positions)")]:
    sub = daily[daily.is_weekend == flag]
    ax.scatter(sub["temp"], sub["cons_kwh"], s=22, color=col, marker=mk, alpha=0.7, edgecolor="white", linewidth=0.5,
               label=f"{lab}, n = {len(sub)}")
    f = fit[flag]
    ax.plot(xs, f["intercept"] + f["slope"] * xs, color=col, lw=1.6, ls="-" if not flag else "--")
ax.text(0.98, 0.04,
        f"Weekdays: r = {fit[False]['r']:.2f}, +{fit[False]['slope']:.1f} kWh per °C\n"
        f"Weekends/holidays: r = {fit[True]['r']:.2f}, +{fit[True]['slope']:.1f} kWh per °C",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#222",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc"))
ax.set_xlabel("Daily mean temperature (°C)")
ax.set_ylabel("Daily energy (kWh)")
ax.set_title("(d) Driver: daily energy vs temperature")
ax.legend(loc="upper left")
ax.grid(**GRID)
ax.set_axisbelow(True)
ax.set_ylim(30, 160)
ax.text(0, -0.33, "Lines = simple linear regression per day type;\ndays with sensor outages excluded.",
        transform=ax.transAxes, fontsize=7.5, color="#555")

fig.suptitle(
    "When and where is energy consumed in a smart research building, and how well does PV generation match that rhythm?\n"
    "Source: Gomes, Pinto & Vale (2022), RETINA/GECAD dataset, 365 days × 288 five-minute intervals.",
    fontsize=11, fontweight="bold", y=0.995,
)
fig.savefig(os.path.join(FIG_DIR, "composite.png"))
fig.savefig(os.path.join(FIG_DIR, "composite.pdf"))
plt.close(fig)

# =========================================================================== #
# 3. SAVE THE QUOTED NUMBERS
# =========================================================================== #
with open(os.path.join(RES_DIR, "facts.json"), "w") as f:
    json.dump(FACTS, f, indent=2, default=str)
print(json.dumps(FACTS, indent=1, default=str))
print(">> done:", os.path.join(FIG_DIR, "composite.png"))
