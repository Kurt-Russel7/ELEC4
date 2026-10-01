/* Bangon Turismo - chart helpers (Plotly.js).
   Each page passes data from Flask as JSON and calls one of these functions. */
const BT = (function () {
  const COLORS = {
    selected: '#4a86e8',
    benchmark: '#e0287c',
    grid: '#e6e6ec',
    text: '#55555f',
    covid: 'rgba(224, 40, 124, 0.07)',
    band: 'rgba(224, 40, 124, 0.14)',
    status: { 'Fully Recovered': '#34b36b', 'Partially Recovered': '#a95ce0', 'Lagging': '#e0407e' },
    muted: '#c9c9d3',
  };
  const FONT = { family: 'Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif', size: 11, color: COLORS.text };
  const CONFIG = { displayModeBar: false, responsive: true };

  function baseLayout(extra) {
    return Object.assign({
      font: FONT,
      margin: { l: 56, r: 48, t: 10, b: 32 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      showlegend: false,
      hovermode: 'x unified',
      xaxis: { gridcolor: COLORS.grid, zeroline: false, linecolor: COLORS.grid },
      yaxis: { gridcolor: COLORS.grid, zeroline: false, separatethousands: true, tickformat: '~s' },
    }, extra || {});
  }

  function covidShape(isYears) {
    return {
      type: 'rect', xref: 'x', yref: 'paper', y0: 0, y1: 1, line: { width: 0 },
      fillcolor: COLORS.covid, layer: 'below',
      x0: isYears ? 2019.5 : '2020-03-01', x1: isYears ? 2022.5 : '2022-12-31',
    };
  }

  function splitMarker() {
    return {
      shapes: [{ type: 'line', xref: 'x', yref: 'paper', x0: '2023-01-01', x1: '2023-01-01', y0: 0, y1: 1,
                 line: { color: '#9a9aa6', width: 1 } }],
      annotations: [{ x: '2023-01-01', y: 0.02, xref: 'x', yref: 'paper', text: 'Test starts',
                      showarrow: false, xanchor: 'left', font: { size: 10, color: '#7a7a86' } }],
    };
  }

  function endLabel(x, y, color, text) {
    return { x: x, y: y, text: text, showarrow: false, xanchor: 'left', xshift: 6,
             font: { size: 11, color: color } };
  }

  function fmt(v) {
    if (v === null || v === undefined) return '';
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (a >= 1e3) return (v / 1e3).toFixed(1) + 'K';
    return v.toFixed(0);
  }

  // Small trend line inside a KPI card
  function sparkline(id, x, y) {
    const el = document.getElementById(id);
    if (!el || !y.length) return;
    Plotly.newPlot(el, [{
      x: x, y: y, type: 'scatter', mode: 'lines', line: { color: COLORS.selected, width: 2, shape: 'spline' },
      fill: 'tozeroy', fillcolor: 'rgba(74, 134, 232, 0.12)', hovertemplate: '%{x}: %{y:,.0f}<extra></extra>',
    }, {
      x: [x[x.length - 1]], y: [y[y.length - 1]], mode: 'markers', marker: { color: COLORS.selected, size: 6 },
      hoverinfo: 'skip',
    }], {
      margin: { l: 0, r: 4, t: 4, b: 0 }, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      showlegend: false, xaxis: { visible: false }, yaxis: { visible: false, rangemode: 'tozero' },
      font: FONT, hovermode: 'closest',
    }, CONFIG);
  }

  // Selected series vs benchmark (design 1's "selected region vs organization benchmark")
  function compareChart(id, x, selected, benchmark, opts) {
    opts = opts || {};
    const traces = [{
      x: x, y: selected, name: 'Selected', type: 'scatter', mode: 'lines',
      line: { color: COLORS.selected, width: 1.8 }, hovertemplate: '%{y:,.0f}',
    }];
    const ann = [endLabel(x[x.length - 1], selected[selected.length - 1], COLORS.selected, fmt(selected[selected.length - 1]))];
    if (benchmark) {
      traces.push({
        x: x, y: benchmark, name: 'Benchmark', type: 'scatter', mode: 'lines',
        line: { color: COLORS.benchmark, width: 1.5 }, hovertemplate: '%{y:,.0f}',
      });
      ann.push(endLabel(x[x.length - 1], benchmark[benchmark.length - 1], COLORS.benchmark, fmt(benchmark[benchmark.length - 1])));
    }
    const shapes = [];
    if (opts.covid) shapes.push(covidShape(false));
    if (opts.covidYears) shapes.push(covidShape(true));
    if (opts.ref100) {
      shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 100, y1: 100,
                    line: { color: '#9a9aa6', width: 1, dash: 'dot' } });
    }
    if (opts.testSplit && x.some(function (d) { return d >= '2023-01-01'; })) {
      const m = splitMarker();
      shapes.push.apply(shapes, m.shapes);
      ann.push.apply(ann, m.annotations);
    }
    const layout = baseLayout({ shapes: shapes, annotations: ann });
    layout.xaxis.range = [x[0], x[x.length - 1]];
    if (opts.ref100) layout.yaxis.tickformat = ',.0f';
    Plotly.newPlot(id, traces, layout, CONFIG);
  }

  // Recovery rate bars coloured by status, with 80% and 100% thresholds
  function recoveryBars(id, cats, rates, status) {
    Plotly.newPlot(id, [{
      x: rates, y: cats, type: 'bar', orientation: 'h',
      marker: { color: status.map(function (s) { return COLORS.status[s]; }) },
      text: rates.map(function (r) { return r.toFixed(1) + '%'; }), textposition: 'outside',
      hovertemplate: '%{y}: %{x:.1f}%<extra></extra>', cliponaxis: false,
    }], baseLayout({
      margin: { l: 170, r: 60, t: 10, b: 32 },
      hovermode: 'closest',
      xaxis: { gridcolor: COLORS.grid, zeroline: false, ticksuffix: '%', rangemode: 'tozero' },
      yaxis: { autorange: 'reversed', gridcolor: 'rgba(0,0,0,0)' },
      shapes: [80, 100].map(function (v) {
        return { type: 'line', yref: 'paper', y0: 0, y1: 1, x0: v, x1: v,
                 line: { color: '#9a9aa6', width: 1, dash: 'dash' } };
      }),
    }), CONFIG);
  }

  // One line per category, indexed to 2019 = 100, labelled at the end (borrowed from design 2)
  function indexLines(id, x, lines) {
    const traces = [], ann = [];
    const palette = ['#4a86e8', '#e0287c', '#2fa37a', '#a95ce0', '#e8913a', '#3f3f4a', '#16a3b8'];
    const showAll = lines.every(function (l) { return l.highlight; });
    // draw muted lines first so the highlighted one sits on top
    const order = lines.map(function (l, i) { return i; })
      .sort(function (a, b) { return lines[a].highlight - lines[b].highlight; });
    order.forEach(function (i) {
      const l = lines[i];
      const color = showAll ? palette[i % palette.length] : (l.highlight ? COLORS.selected : COLORS.muted);
      traces.push({ x: x, y: l.y, name: l.name, type: 'scatter', mode: 'lines',
                    line: { color: color, width: l.highlight && !showAll ? 2.4 : 1.4 },
                    hovertemplate: l.name + ': %{y:.1f}<extra></extra>' });
      if (l.highlight && !showAll) ann.push(endLabel(x[x.length - 1], l.y[l.y.length - 1], color, l.name));
    });
    Plotly.newPlot(id, traces, baseLayout({
      margin: { l: 48, r: showAll ? 16 : 150, t: 10, b: 32 },
      hovermode: 'closest',
      showlegend: showAll,
      legend: { orientation: 'h', y: -0.15, font: { size: 10 } },
      xaxis: { gridcolor: COLORS.grid, zeroline: false, range: [x[0], x[x.length - 1]] },
      yaxis: { gridcolor: COLORS.grid, zeroline: false, tickformat: ',.0f' },
      shapes: [covidShape(true), { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 100, y1: 100,
                                   line: { color: '#9a9aa6', width: 1, dash: 'dot' } }],
      annotations: ann,
    }), CONFIG);
  }

  // History + forecast with 95% band
  function forecastChart(id, d) {
    const lastX = d.hist_x[d.hist_x.length - 1], lastY = d.hist_y[d.hist_y.length - 1];
    const fx = [lastX].concat(d.fc_x), fy = [lastY].concat(d.fc_y);
    Plotly.newPlot(id, [
      { x: d.fc_x.concat(d.fc_x.slice().reverse()), y: d.hi.concat(d.lo.slice().reverse()),
        fill: 'toself', fillcolor: COLORS.band, line: { width: 0 }, hoverinfo: 'skip', type: 'scatter' },
      { x: d.fc_x, y: d.hi, mode: 'lines', line: { width: 0 }, hovertemplate: 'Upper 95%: %{y:,.0f}<extra></extra>' },
      { x: d.fc_x, y: d.lo, mode: 'lines', line: { width: 0 }, hovertemplate: 'Lower 95%: %{y:,.0f}<extra></extra>' },
      { x: d.hist_x, y: d.hist_y, mode: 'lines', line: { color: COLORS.selected, width: 1.8 },
        hovertemplate: 'Actual: %{y:,.0f}<extra></extra>' },
      { x: fx, y: fy, mode: 'lines', line: { color: COLORS.benchmark, width: 2 },
        hovertemplate: 'Forecast: %{y:,.0f}<extra></extra>' },
    ], baseLayout({
      margin: { l: 56, r: 64, t: 10, b: 32 },
      shapes: [covidShape(false), { type: 'line', xref: 'x', yref: 'paper', x0: d.fc_x[0], x1: d.fc_x[0], y0: 0, y1: 1,
                                    line: { color: '#9a9aa6', width: 1 } }],
      annotations: [
        endLabel(d.fc_x[d.fc_x.length - 1], d.fc_y[d.fc_y.length - 1], COLORS.benchmark, fmt(d.fc_y[d.fc_y.length - 1])),
        { x: d.fc_x[0], y: 0.98, xref: 'x', yref: 'paper', text: 'Forecast', showarrow: false, xanchor: 'left',
          xshift: 4, font: { size: 10, color: '#7a7a86' } },
      ],
    }), CONFIG);
  }

  // Actual vs each model's predictions on the 2023-2025 test period
  function testChart(id, d) {
    const modelColors = { 'Linear Regression': '#e8913a', 'Polynomial Regression': '#a95ce0', 'SARIMA': COLORS.benchmark };
    const traces = [{ x: d.x, y: d.actual, name: 'Actual', mode: 'lines',
                      line: { color: COLORS.selected, width: 2.4 }, hovertemplate: 'Actual: %{y:,.0f}<extra></extra>' }];
    const ann = [endLabel(d.x[d.x.length - 1], d.actual[d.actual.length - 1], COLORS.selected, 'Actual')];
    Object.keys(d.preds).forEach(function (m) {
      const y = d.preds[m];
      traces.push({ x: d.x, y: y, name: m, mode: 'lines', line: { color: modelColors[m], width: 1.5, dash: 'dash' },
                    hovertemplate: m + ': %{y:,.0f}<extra></extra>' });
      ann.push(endLabel(d.x[d.x.length - 1], y[y.length - 1], modelColors[m], m));
    });
    Plotly.newPlot(id, traces, baseLayout({ margin: { l: 56, r: 150, t: 10, b: 32 }, annotations: ann }), CONFIG);
  }

  return { sparkline: sparkline, compareChart: compareChart, recoveryBars: recoveryBars,
           indexLines: indexLines, forecastChart: forecastChart, testChart: testChart };
})();
