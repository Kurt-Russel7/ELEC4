import numpy as np
import pandas as pd
from flask import Flask, render_template, request

import analysis as A

# Edit these to match how you describe the data in your paper.
DATA_SOURCE_NOTE = "Source: Kaggle inbound tourism expenditure dataset (modified), monthly, 2000-2025"
UNIT_LABEL = "₱ million"

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True   # pick up template edits without restarting the server

print("Training models and preparing results...")
R = A.build_all()
CATEGORIES = sorted(R["wide"].columns)
YEARS = sorted(int(y) for y in R["annual"]["Year"].unique())
print("Ready.")

POST_PANDEMIC_FROM = 2020     # first year offered in the "Compare with 2019" picker

STATUS_CLASS = {"Fully Recovered": "healthy", "Partially Recovered": "warning", "Lagging": "critical"}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def get_filters():
    cat = request.args.get("category", "All")
    model = request.args.get("model", "Best")
    try:
        y_from = int(request.args.get("from", YEARS[0]))
        y_to = int(request.args.get("to", YEARS[-1]))
    except ValueError:
        y_from, y_to = YEARS[0], YEARS[-1]
    if cat != "All" and cat not in CATEGORIES:
        cat = "All"
    if model != "Best" and model not in A.MODEL_NAMES:
        model = "Best"
    y_from = min(max(y_from, YEARS[0]), YEARS[-1] - 1)
    y_to = min(max(y_to, y_from + 1), YEARS[-1])
    return {"category": cat, "model": model, "from": y_from, "to": y_to}


def base_context(f, page):
    return {
        "f": f, "page": page, "categories": CATEGORIES, "models": A.MODEL_NAMES,
        "years": YEARS, "unit": UNIT_LABEL, "source_note": DATA_SOURCE_NOTE,
        "status_class": STATUS_CLASS,
    }


def monthly_series(cat):
    """Monthly values for one category, or the total of all categories."""
    w = R["wide"]
    return w.sum(axis=1) if cat == "All" else w[cat]


def annual_series(cat):
    a = R["annual"]
    if cat == "All":
        return a.groupby("Year")["Expenditure"].sum()
    return a[a["Category"] == cat].set_index("Year")["Expenditure"]


def model_for(cat, model):
    """The model to use for a category: the chosen one, or its best (lowest RMSE)."""
    if model != "Best":
        return model
    return R["best"].set_index("Category").loc[cat, "Model"]


def to_list(s):
    return [None if pd.isna(v) else float(v) for v in s]


def dates(idx):
    return [d.strftime("%Y-%m-%d") for d in idx]


def heat_color(v):
    """Cell colour for the YoY growth heatmap: red for decline, green for growth."""
    if v is None or pd.isna(v):
        return "transparent"
    v = max(min(v, 60), -100)
    if v < 0:
        a = 0.12 + 0.75 * (-v / 100)
        return f"rgba(214, 51, 108, {a:.2f})"
    a = 0.10 + 0.70 * (v / 60)
    return f"rgba(46, 160, 110, {a:.2f})"


# --------------------------------------------------------------------------
# Page 1 - Overview
# --------------------------------------------------------------------------
@app.route("/")
def overview():
    f = get_filters()
    cat, y_to = f["category"], f["to"]
    ctx = base_context(f, "overview")

    ann = annual_series(cat)
    cur, prev, base = ann.get(y_to), ann.get(y_to - 1), ann.get(A.BASELINE_YEAR)
    rec_rate = cur / base * 100 if y_to > A.BASELINE_YEAR else None
    rec_all = A.recovery_table(R["annual"], max(y_to, A.BASELINE_YEAR + 1))

    # Forecast for next year and model accuracy for the selection
    cats = CATEGORIES if cat == "All" else [cat]
    fut = R["future"]
    next_year = fut["Date"].dt.year.min()
    fc_next = sum(
        fut[(fut["Category"] == c) & (fut["Model"] == model_for(c, f["model"]))
            & (fut["Date"].dt.year == next_year)]["Forecast"].sum()
        for c in cats
    )
    met = R["metrics"].set_index(["Category", "Model"])
    mape_val = np.mean([met.loc[(c, model_for(c, f["model"])), "MAPE"] for c in cats])

    ctx["kpi"] = {
        "total": cur, "total_change": (cur / prev - 1) * 100 if prev else None,
        "spark_x": [int(y) for y in ann.index if f["from"] <= y <= y_to],
        "spark_y": [float(v) for y, v in ann.items() if f["from"] <= y <= y_to],
        "recovery": rec_rate,
        "recovery_status": A.recovery_status(rec_rate) if rec_rate is not None else None,
        "yoy": (cur / prev - 1) * 100 if prev else None,
        "fully": int((rec_all["Status"] == "Fully Recovered").sum()),
        "slowest": rec_all.iloc[-1]["Category"],
        "slowest_rate": float(rec_all.iloc[-1]["Recovery_Rate_pct"]),
        "slowest_status": rec_all.iloc[-1]["Status"],
        "n_cat": len(CATEGORIES),
        "forecast_next": fc_next, "next_year": int(next_year),
        "mape": mape_val,
        "model_label": "best model per category" if f["model"] == "Best" else f["model"],
    }

    # Chart A - monthly expenditure (selected vs all-category average)
    m_sel = monthly_series(cat)
    m_avg = R["wide"].mean(axis=1)
    win = (m_sel.index.year >= f["from"]) & (m_sel.index.year <= y_to)
    # Chart B - recovery index, 2019 = 100
    a_sel = annual_series(cat)
    a_all = annual_series("All")
    yrs = [int(y) for y in a_sel.index if f["from"] <= y <= y_to]
    ctx["charts"] = {
        "monthly": {
            "x": dates(m_sel.index[win]),
            "selected": to_list(m_sel[win]),
            "benchmark": None if cat == "All" else to_list(m_avg[win]),
            "selected_name": "All categories (total)" if cat == "All" else cat,
        },
        "index": {
            "x": yrs,
            "selected": [float(a_sel[y] / a_sel[A.BASELINE_YEAR] * 100) for y in yrs],
            "benchmark": None if cat == "All" else
                         [float(a_all[y] / a_all[A.BASELINE_YEAR] * 100) for y in yrs],
            "selected_name": "All categories" if cat == "All" else cat,
        },
    }

    # Recovery table (like "Latest Cases")
    ctx["recovery_rows"] = rec_all.to_dict("records")
    ctx["recovery_year"] = max(y_to, A.BASELINE_YEAR + 1)

    # YoY growth heatmap (borrowed from the retention table in design 2)
    heat_years = [y for y in YEARS if f["from"] < y <= y_to]
    a = R["annual"].pivot(index="Category", columns="Year", values="YoY_Growth_pct")
    ctx["heat"] = {
        "years": heat_years,
        "rows": [{"category": c,
                  "cells": [{"v": a.loc[c, y], "bg": heat_color(a.loc[c, y])} for y in heat_years]}
                 for c in CATEGORIES],
    }
    return render_template("overview.html", **ctx)


# --------------------------------------------------------------------------
# Page 2 - Recovery and category comparison
# --------------------------------------------------------------------------
@app.route("/recovery")
def recovery():
    f = get_filters()
    ctx = base_context(f, "recovery")
    year = max(f["to"], A.BASELINE_YEAR + 1)
    post_years = [y for y in YEARS if y >= POST_PANDEMIC_FROM]
    try:
        ry = int(request.args.get("ry", ""))
    except ValueError:
        ry = None
    if ry in post_years:                   # recovery year picked on the page
        year = ry
    rec = A.recovery_table(R["annual"], year)
    ctx["year"] = year
    ctx["post_years"] = post_years
    ctx["ry"] = ry if ry in post_years else None
    ctx["rows"] = rec.to_dict("records")
    ctx["counts"] = {s: int((rec["Status"] == s).sum()) for s in STATUS_CLASS}

    a = R["annual"]
    yrs = [y for y in YEARS if f["from"] <= y <= f["to"]]
    lines = []
    for c in CATEGORIES:
        s = a[a["Category"] == c].set_index("Year")["Expenditure"]
        lines.append({"name": c, "y": [float(s[y] / s[A.BASELINE_YEAR] * 100) for y in yrs],
                      "highlight": f["category"] in ("All", c)})
    ctx["charts"] = {
        "bars": {"x": rec["Category"].tolist(), "y": to_list(rec["Recovery_Rate_pct"]),
                 "status": rec["Status"].tolist()},
        "index": {"x": yrs, "lines": lines},
    }
    return render_template("recovery.html", **ctx)


# --------------------------------------------------------------------------
# Page 3 - Forecast panel
# --------------------------------------------------------------------------
@app.route("/forecast")
def forecast():
    f = get_filters()
    ctx = base_context(f, "forecast")
    cat = f["category"]
    cats = CATEGORIES if cat == "All" else [cat]

    fut = R["future"]
    parts = [fut[(fut["Category"] == c) & (fut["Model"] == model_for(c, f["model"]))]
             .set_index("Date")[["Forecast", "Lower_95", "Upper_95"]] for c in cats]
    fc = sum(parts[1:], parts[0])          # add categories together when "All"

    hist = monthly_series(cat)
    hist = hist[hist.index.year >= f["from"]]
    ctx["charts"] = {"forecast": {
        "hist_x": dates(hist.index), "hist_y": to_list(hist),
        "fc_x": dates(fc.index), "fc_y": to_list(fc["Forecast"]),
        "lo": to_list(fc["Lower_95"]), "hi": to_list(fc["Upper_95"]),
        "name": "All categories (total)" if cat == "All" else cat,
    }}

    annual_fc = fc.groupby(fc.index.year).sum()
    ctx["annual_rows"] = [{"year": int(y), **r} for y, r in annual_fc.to_dict("index").items()]
    ctx["used_models"] = [{"category": c, "model": model_for(c, f["model"])} for c in cats]

    # Compare all three models for the selection (annual totals)
    comp = []
    for m in A.MODEL_NAMES:
        tot = sum(fut[(fut["Category"] == c) & (fut["Model"] == m)]
                  .groupby(fut["Date"].dt.year)["Forecast"].sum() for c in cats)
        comp.append({"model": m, "values": [float(v) for v in tot.values]})
    ctx["model_comp"] = {"years": [int(y) for y in annual_fc.index], "rows": comp}
    return render_template("forecast.html", **ctx)


# --------------------------------------------------------------------------
# Page 4 - Model evaluation
# --------------------------------------------------------------------------
@app.route("/evaluation")
def evaluation():
    f = get_filters()
    ctx = base_context(f, "evaluation")
    met = R["metrics"]
    best = R["best"]

    avg = met.groupby("Model")[["MAE", "RMSE", "MAPE"]].mean()
    ctx["avg"] = [{"model": m, **avg.loc[m].to_dict(),
                   "wins": int((best["Model"] == m).sum())} for m in A.MODEL_NAMES]

    best_pairs = set(zip(best["Category"], best["Model"]))
    view = met if f["category"] == "All" else met[met["Category"] == f["category"]]
    ctx["rows"] = [{**r, "best": (r["Category"], r["Model"]) in best_pairs}
                   for r in view.to_dict("records")]

    # Actual vs predicted on the test period
    tp = R["test_preds"]
    cats = CATEGORIES if f["category"] == "All" else [f["category"]]
    sel = tp[tp["Category"].isin(cats)]
    actual = sel[sel["Model"] == A.MODEL_NAMES[0]].groupby("Date")["Actual"].sum()
    preds = {m: to_list(sel[sel["Model"] == m].groupby("Date")["Predicted"].sum())
             for m in A.MODEL_NAMES}
    ctx["charts"] = {"test": {"x": dates(actual.index), "actual": to_list(actual), "preds": preds,
                              "name": "All categories (total)" if f["category"] == "All"
                              else f["category"]}}
    ctx["split"] = {"train": "Jan 2000 - Dec 2022", "test": "Jan 2023 - Dec 2025"}
    return render_template("evaluation.html", **ctx)


# --------------------------------------------------------------------------
# Template filters
# --------------------------------------------------------------------------
@app.template_filter("num")
def fmt_num(v, d=0):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:,.{d}f}"


@app.template_filter("pct")
def fmt_pct(v, d=1, sign=False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:+.{d}f}%" if sign else f"{v:.{d}f}%"


if __name__ == "__main__":
    app.run(debug=False)
