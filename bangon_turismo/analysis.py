"""
Bangon Turismo - data preparation, analysis, forecasting, and evaluation.

Kept separate from the web app (app.py) so the analysis can be run, tested,
and documented on its own:   python analysis.py

Setup (same as the R model-development script):
  Train : Jan 2000 - Dec 2022
  Test  : Jan 2023 - Dec 2025 (36 months)
  Models: Linear Regression, Polynomial Regression, SARIMA
  Metric: MAE, RMSE, MAPE
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")

DATA_FILE = Path(__file__).parent / "data" / "philippines_inbound_tourism_monthly_expenditure.csv"

TRAIN_END = "2022-12-01"
TEST_START = "2023-01-01"
COVID_START = "2020-03-01"      # start of lockdowns
COVID_END = "2022-12-01"        # last month treated as COVID-affected
BASELINE_YEAR = 2019
FORECAST_MONTHS = 36            # Jan 2026 - Dec 2028

SHORT_NAMES = {
    "Accommodation services for visitors": "Accommodation",
    "Food and beverage serving services": "Food & Beverage",
    "Transport services": "Transport",
    "Travel agencies and other reservation services": "Travel Agencies",
    "Entertainment and recreation services": "Entertainment & Recreation",
    "Shopping": "Shopping",
    "Other services": "Other Services",
}

MODEL_NAMES = ["Linear Regression", "Polynomial Regression", "SARIMA"]

# SARIMA orders chosen by auto.arima() in R during model development.
# "train" = fitted on 2000-2022 (for testing); "full" = fitted on 2000-2025 (for 2026-2028).
# Every SARIMA model also includes a drift (time trend) term and the COVID dummy.
SARIMA_ORDERS = {
    "Accommodation":              {"train": ((3, 0, 0), (0, 1, 2, 12)), "full": ((1, 0, 2), (1, 1, 2, 12))},
    "Entertainment & Recreation": {"train": ((3, 0, 0), (0, 1, 2, 12)), "full": ((1, 0, 3), (1, 1, 1, 12))},
    "Food & Beverage":            {"train": ((1, 0, 0), (0, 1, 1, 12)), "full": ((1, 0, 0), (1, 1, 2, 12))},
    "Other Services":             {"train": ((1, 0, 2), (0, 1, 2, 12)), "full": ((1, 0, 3), (0, 1, 2, 12))},
    "Shopping":                   {"train": ((1, 0, 0), (0, 1, 0, 12)), "full": ((2, 0, 4), (1, 1, 1, 12))},
    "Transport":                  {"train": ((3, 0, 0), (0, 1, 2, 12)), "full": ((1, 0, 3), (0, 1, 2, 12))},
    "Travel Agencies":            {"train": ((3, 0, 0), (0, 1, 2, 12)), "full": ((1, 0, 3), (0, 1, 2, 12))},
}


# --------------------------------------------------------------------------
# Objective 1 - collect and prepare the data
# --------------------------------------------------------------------------
def load_data(source=DATA_FILE) -> pd.DataFrame:
    df = pd.read_csv(source)
    df = df.rename(columns={
        "Tourism_Product_Category": "Category",
        "Inbound_Expenditure_Millions_PHP": "Expenditure",
    })
    df["Date"] = pd.to_datetime(df["Date"])
    df["Category"] = df["Category"].str.strip()
    df["Category"] = df["Category"].map(SHORT_NAMES).fillna(df["Category"])
    df = df.sort_values(["Category", "Date"]).reset_index(drop=True)
    df["Year"] = df["Date"].dt.year
    return df[["Date", "Year", "Category", "Expenditure"]]


def to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """One column per category, one row per month."""
    wide = df.pivot(index="Date", columns="Category", values="Expenditure")
    wide.index.freq = "MS"
    return wide


# --------------------------------------------------------------------------
# Objective 2 - trends, YoY growth, recovery rate
# --------------------------------------------------------------------------
def annual_summary(df: pd.DataFrame) -> pd.DataFrame:
    annual = df.groupby(["Category", "Year"], as_index=False)["Expenditure"].sum()
    annual["YoY_Growth_pct"] = annual.groupby("Category")["Expenditure"].pct_change() * 100
    return annual


def recovery_status(rate: float) -> str:
    if rate >= 100:
        return "Fully Recovered"
    if rate >= 80:
        return "Partially Recovered"
    return "Lagging"


def recovery_table(annual: pd.DataFrame, year: int) -> pd.DataFrame:
    base = annual[annual["Year"] == BASELINE_YEAR].set_index("Category")["Expenditure"]
    cur = annual[annual["Year"] == year].set_index("Category")["Expenditure"]
    out = pd.DataFrame({"Baseline": base, "Current": cur})
    out["Recovery_Rate_pct"] = cur / base * 100
    out["Status"] = out["Recovery_Rate_pct"].apply(recovery_status)
    return out.sort_values("Recovery_Rate_pct", ascending=False).reset_index()


# --------------------------------------------------------------------------
# Objective 3 - forecasting models
# --------------------------------------------------------------------------
def covid_dummy(index: pd.DatetimeIndex) -> np.ndarray:
    return ((index >= COVID_START) & (index <= COVID_END)).astype(float)


def _future_index(y: pd.Series, h: int) -> pd.DatetimeIndex:
    return pd.date_range(y.index[-1] + pd.offsets.MonthBegin(1), periods=h, freq="MS")


def _regression_design(index, t, poly):
    X = pd.DataFrame(index=index)
    X["trend"] = t
    if poly:
        X["trend2"] = t ** 2
    for m in range(2, 13):                      # month dummies, January = base
        X[f"m{m}"] = (index.month == m).astype(float)
    X["covid"] = covid_dummy(index)
    return sm.add_constant(X, has_constant="add")


def fit_regression(y: pd.Series, h: int, poly: bool = False) -> pd.DataFrame:
    n = len(y)
    future_idx = _future_index(y, h)
    X_train = _regression_design(y.index, np.arange(1, n + 1, dtype=float), poly)
    X_future = _regression_design(future_idx, np.arange(n + 1, n + h + 1, dtype=float), poly)
    X_future["covid"] = 0.0                     # assume no new COVID-type shock

    fit = sm.OLS(y.values, X_train).fit()
    pred = fit.get_prediction(X_future).summary_frame(alpha=0.05)
    return pd.DataFrame({
        "Forecast": pred["mean"].values,
        "Lower_95": pred["obs_ci_lower"].values,
        "Upper_95": pred["obs_ci_upper"].values,
    }, index=future_idx)


def fit_sarima(y: pd.Series, h: int, category: str, stage: str) -> pd.DataFrame:
    order, seasonal = SARIMA_ORDERS[category][stage]
    n = len(y)
    exog = np.column_stack([np.arange(1, n + 1), covid_dummy(y.index)])        # drift + COVID
    exog_future = np.column_stack([np.arange(n + 1, n + h + 1), np.zeros(h)])

    fit = SARIMAX(y, exog=exog, order=order, seasonal_order=seasonal).fit(disp=False)
    fc = fit.get_forecast(steps=h, exog=exog_future)
    ci = fc.conf_int(alpha=0.05)
    return pd.DataFrame({
        "Forecast": fc.predicted_mean.values,
        "Lower_95": ci.iloc[:, 0].values,
        "Upper_95": ci.iloc[:, 1].values,
    }, index=_future_index(y, h))


def run_model(name, y, h, category, stage):
    if name == "Linear Regression":
        return fit_regression(y, h, poly=False)
    if name == "Polynomial Regression":
        return fit_regression(y, h, poly=True)
    if name == "SARIMA":
        return fit_sarima(y, h, category, stage)
    raise ValueError(f"Unknown model: {name}")


# --------------------------------------------------------------------------
# Objective 4 - evaluation
# --------------------------------------------------------------------------
def mae(a, f):
    return float(np.mean(np.abs(a - f)))


def rmse(a, f):
    return float(np.sqrt(np.mean((a - f) ** 2)))


def mape(a, f):
    return float(np.mean(np.abs((a - f) / a)) * 100)


def evaluate(wide: pd.DataFrame):
    """Train on 2000-2022, test on 2023-2025. Returns (metrics, test predictions)."""
    rows, preds = [], []
    for cat in wide.columns:
        train, test = wide[cat][:TRAIN_END], wide[cat][TEST_START:]
        for m in MODEL_NAMES:
            f = run_model(m, train, len(test), cat, "train")["Forecast"].values
            a = test.values
            rows.append({"Category": cat, "Model": m,
                         "MAE": mae(a, f), "RMSE": rmse(a, f), "MAPE": mape(a, f)})
            preds.append(pd.DataFrame({"Date": test.index, "Category": cat, "Model": m,
                                       "Actual": a, "Predicted": f}))
    return pd.DataFrame(rows), pd.concat(preds, ignore_index=True)


def best_models(metrics: pd.DataFrame) -> pd.DataFrame:
    """Best model per category = lowest RMSE on the test set."""
    return metrics.loc[metrics.groupby("Category")["RMSE"].idxmin()].reset_index(drop=True)


def future_forecasts(wide: pd.DataFrame, h: int = FORECAST_MONTHS) -> pd.DataFrame:
    """Refit every model on all data (2000-2025) and forecast h months ahead."""
    out = []
    for cat in wide.columns:
        for m in MODEL_NAMES:
            fc = run_model(m, wide[cat], h, cat, "full").reset_index(names="Date")
            fc["Category"], fc["Model"] = cat, m
            out.append(fc)
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------------------
# Run everything once (used by the web app at startup)
# --------------------------------------------------------------------------
def build_all():
    df = load_data()
    wide = to_wide(df)
    annual = annual_summary(df)
    metrics, test_preds = evaluate(wide)
    best = best_models(metrics)
    future = future_forecasts(wide)
    return {"df": df, "wide": wide, "annual": annual, "metrics": metrics,
            "test_preds": test_preds, "best": best, "future": future}


if __name__ == "__main__":
    out = Path(__file__).parent / "outputs"
    out.mkdir(exist_ok=True)
    r = build_all()
    r["metrics"].round(2).to_csv(out / "model_accuracy_results.csv", index=False)
    r["annual"].round(2).to_csv(out / "annual_yoy_growth.csv", index=False)
    recovery_table(r["annual"], 2025).round(2).to_csv(out / "recovery_rates.csv", index=False)
    r["future"].round(2).to_csv(out / "forecast_2026_2028_monthly.csv", index=False)

    pd.set_option("display.width", 200)
    print(r["metrics"].round(2).to_string(index=False))
    print("\nAverage per model:")
    print(r["metrics"].groupby("Model")[["MAE", "RMSE", "MAPE"]].mean().round(2))
    print("\nBest model per category:")
    print(r["best"].round(2).to_string(index=False))
    print(f"\nCSV files saved to {out}")
