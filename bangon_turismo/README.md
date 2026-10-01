# Bangon Turismo Monitor

Flask web dashboard for analyzing and forecasting Philippine inbound tourism
expenditure by tourism product category.

## How to run

1. Install Python 3.10 or newer.
2. Open a terminal in this folder and install the libraries:

       pip install -r requirements.txt

3. Start the app:

       python app.py

4. Wait for "Ready." (models train once at startup, about 10-20 seconds),
   then open http://127.0.0.1:5000 in your browser.

The charts load Plotly.js from the internet, so you need a connection the first time a page opens.

## Folder structure

    bangon_turismo/
    ├── app.py              Flask routes: prepares data for each page
    ├── analysis.py         Data cleaning, YoY growth, recovery rates, models, metrics
    ├── requirements.txt
    ├── data/               The dataset (CSV)
    ├── templates/          HTML pages (Jinja2)
    │   ├── base.html       Shared top bar, filter sidebar, footer
    │   ├── overview.html
    │   ├── recovery.html
    │   ├── forecast.html
    │   └── evaluation.html
    └── static/
        ├── css/style.css   All styling
        └── js/charts.js    All charts (Plotly.js)

## Pages and proposal features

| Page | Features from the proposal |
|---|---|
| Overview | Trend visualization (COVID period highlighted), growth rate insights (YoY heatmap), recovery status |
| Recovery & comparison | Recovery status, category comparison |
| Forecast | Forecast panel with 95% prediction interval |
| Model evaluation | MAE, RMSE, MAPE on the 2023-2025 test set |

## Running the analysis without the website

    python analysis.py

This prints the accuracy table and saves CSV results to an `outputs/` folder.

## Notes for the paper

- Train: Jan 2000 - Dec 2022. Test: Jan 2023 - Dec 2025. Forecast: Jan 2026 - Dec 2028.
- Every model includes a COVID dummy (Mar 2020 - Dec 2022) and monthly seasonality.
- SARIMA orders were chosen with `auto.arima()` in R and reused in Python (see `SARIMA_ORDERS` in analysis.py).
  Python's statsmodels estimates the coefficients slightly differently, so SARIMA's metrics differ
  a little from the R results. The regression metrics match R exactly.
- The best model per category is the one with the lowest RMSE on the test set.
- Edit `DATA_SOURCE_NOTE` and `UNIT_LABEL` at the top of app.py to match how the data is described in the paper.
