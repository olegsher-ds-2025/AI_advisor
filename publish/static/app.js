const COLORS = ["#2563eb", "#15803d", "#b45309", "#7c3aed", "#b42318", "#0891b2"];
const SCORE_COLUMNS = ["quality", "growth", "value", "momentum", "risk", "total"];
const PAGE_SIZE = 50;
const view = document.getElementById("view");
let index = null;
let listState = { sort: "total", asc: false, sector: "", query: "", page: 0 };

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const num = (v, digits = 0) => (v == null ? "-" : v.toFixed(digits));
const signed = (v) => (v == null ? "-" : (Math.round(v) > 0 ? "+" : "") + (Math.round(v) || 0));
const cls = (v) => (Math.round(v) > 0 ? "up" : Math.round(v) < 0 ? "down" : "");

async function loadJson(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`${path}: ${resp.status}`);
  return resp.json();
}


const vote = (cond, up, down) => (cond === up ? 1 : cond === down ? -1 : 0);

function technicalVotes(f) {
  return [
    ["RSI 14", f.rsi < 30 ? 1 : f.rsi > 70 ? -1 : 0, num(f.rsi, 0)],
    ["Supertrend", f.supertrend_direction, f.supertrend_direction > 0 ? "uptrend" : "downtrend"],
    ["Alligator", vote(f.alligator, "up", "down"), f.alligator],
    ["IIX 21", f.iix > 10 ? 1 : f.iix < -10 ? -1 : 0, num(f.iix, 1)],
  ];
}

function technicalScore(f) {
  if (!f) return null;
  const votes = technicalVotes(f);
  return votes.reduce((sum, v) => sum + v[1], 0) / votes.length;
}

function technicalLabel(score) {
  if (score == null) return "-";
  return score > 0.5 ? "Strong buy" : score > 0.1 ? "Buy" : score < -0.5 ? "Strong sell" : score < -0.1 ? "Sell" : "Neutral";
}

const tone = (score) => (score > 0.1 ? "up" : score < -0.1 ? "down" : "");

function technicalCell(f) {
  const score = technicalScore(f);
  return el("td", { className: tone(score), textContent: technicalLabel(score) });
}

const SVG_NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs) => {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
};

function gauge({ title, position, label, left, right, note }) {
  const cx = 100, cy = 100, r = 80, segments = 5;
  const colors = ["#b42318", "#e8836f", "#98a2b3", "#6dbf86", "#15803d"];
  const point = (t, radius = r) => [cx - radius * Math.cos(Math.PI * t), cy - radius * Math.sin(Math.PI * t)];
  const svg = svgEl("svg", { viewBox: "0 0 200 120", role: "img", "aria-label": `${title}: ${label}` });
  for (let i = 0; i < segments; i++) {
    const [x1, y1] = point(i / segments), [x2, y2] = point((i + 1) / segments);
    svg.append(svgEl("path", { d: `M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2}`, fill: "none", stroke: colors[i], "stroke-width": 14 }));
  }
  const t = Math.min(1, Math.max(0, position));
  const [nx, ny] = point(t, r - 12);
  svg.append(svgEl("line", { x1: cx, y1: cy, x2: nx, y2: ny, stroke: "currentColor", "stroke-width": 3, "stroke-linecap": "round" }));
  svg.append(svgEl("circle", { cx, cy, r: 5, fill: "currentColor" }));
  const caption = (x, anchor, text) => {
    const node = svgEl("text", { x, y: 116, "text-anchor": anchor, "font-size": 10, fill: "currentColor", opacity: 0.7 });
    node.textContent = text;
    return node;
  };
  svg.append(caption(14, "start", left), caption(186, "end", right));
  return el("figure", { className: "gauge" }, el("figcaption", { textContent: title }), svg, el("strong", { textContent: label }), el("div", { className: "muted", textContent: note }));
}

function technicalGauge(indicators) {
  const frames = Object.keys(indicators);
  const host = el("div", { className: "gauge-host" });
  const select = el("select", {}, ...frames.map((f) => el("option", { value: f, textContent: f, selected: f === "daily" })));
  const detail = el("div", { className: "table-wrap" });
  const render = () => {
    const f = indicators[select.value];
    const score = technicalScore(f);
    const votes = technicalVotes(f);
    host.replaceChildren(gauge({ title: "Technical summary", position: (score + 1) / 2, label: technicalLabel(score), left: "Sell", right: "Buy", note: `${select.value} timeframe` }));
    detail.replaceChildren(el("table", {}, el("tbody", {}, ...votes.map(([name, v, reading]) =>
      el("tr", {}, el("td", { textContent: name }), el("td", { textContent: reading }), el("td", { className: tone(v), textContent: v > 0 ? "buy" : v < 0 ? "sell" : "neutral" }))))));
  };
  select.onchange = render;
  render();
  return el("div", {}, el("div", { className: "controls" }, el("label", { textContent: "Timeframe " }, select)), host, detail);
}

function scoreGauge(title, value, left, right, note) {
  const label = value == null ? "-" : value.toFixed(0);
  return gauge({ title, position: (value ?? 50) / 100, label, left, right, note });
}

function lineChart(series, labels) {
  const width = 600, height = 180, pad = 6;
  const values = series.flatMap((s) => s.values).filter((v) => v != null);
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const n = series[0].values.length;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.classList.add("chart");
  series.forEach((s, i) => {
    const d = s.values
      .map((v, j) => (v == null ? null : `${(j / (n - 1)) * width},${height - pad - ((v - lo) / span) * (height - 2 * pad)}`))
      .filter(Boolean)
      .map((p, k) => (k ? "L" : "M") + p)
      .join("");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("stroke", COLORS[i % COLORS.length]);
    svg.append(path);
  });
  const legend = el("div", { className: "legend muted" }, ...series.map((s, i) => {
    const swatch = el("span", { textContent: s.name });
    swatch.style.color = COLORS[i % COLORS.length];
    return swatch;
  }));
  return el("div", {}, svg, legend, el("div", { className: "muted", textContent: `${labels[0]} to ${labels[labels.length - 1]}   range ${lo.toFixed(2)} - ${hi.toFixed(2)}` }));
}

function topPicks() {
  const head = el("tr", {}, ...["#", "Symbol", "Name", "Sector", "Total", "3m chg", "Technical (daily)"].map((t) => el("th", { textContent: t })));
  const rows = index.top.map((r, i) =>
    el("tr", {},
      el("td", { textContent: i + 1 }),
      el("td", {}, el("a", { href: `#/s/${r.symbol}`, textContent: r.symbol })),
      el("td", { textContent: r.name || "" }),
      el("td", { textContent: r.sector || "" }),
      el("td", { textContent: num(r.total) }),
      el("td", { className: cls(r.total_change), textContent: signed(r.total_change) }),
      technicalCell(r.daily)));
  return el("section", {},
    el("h2", { textContent: `Top ${index.top.length} by score today` }),
    el("p", { className: "muted", textContent: `Highest total scores as of ${index.as_of}, only stocks with all five category scores. A research shortlist to investigate, not buy recommendations or investment advice. Open a stock for the thesis, bull and bear case.` }),
    el("div", { className: "table-wrap" }, el("table", {}, el("thead", {}, head), el("tbody", {}, ...rows))));
}

function columnLegend() {
  const labels = { sector: "Sector", quality: "Quality", growth: "Growth", value: "Value", momentum: "Momentum", risk: "Risk", total: "Total", total_change: `${index.delta_months}m chg` };
  return el("details", { open: true },
    el("summary", { textContent: "What the columns mean" }),
    ...Object.entries(labels).flatMap(([key, label]) => [el("strong", { textContent: label }), el("p", { className: "muted", textContent: index.columns[key] })]),
    el("p", { className: "muted", textContent: "Risk: 100 = lowest volatility and smallest drawdown. Scores rank stocks against each other on each date, they don't predict returns." }));
}

function listView() {
  const sectors = [...new Set(index.rows.map((r) => r.sector).filter(Boolean))].sort();
  const search = el("input", { type: "search", placeholder: "Symbol or name", value: listState.query });
  const sector = el("select", {}, el("option", { value: "", textContent: "All sectors" }), ...sectors.map((s) => el("option", { value: s, textContent: s, selected: s === listState.sector })));
  const tableHost = el("div", { className: "table-wrap" });

  const render = () => {
    const q = listState.query.toLowerCase();
    const rows = index.rows
      .filter((r) => (!listState.sector || r.sector === listState.sector) && (!q || r.symbol.toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q)))
      .sort((a, b) => {
        const x = a[listState.sort] ?? -Infinity, y = b[listState.sort] ?? -Infinity;
        return (x < y ? -1 : x > y ? 1 : 0) * (listState.asc ? 1 : -1);
      });
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    listState.page = Math.min(listState.page, pages - 1);
    const columns = [["symbol", "Symbol"], ["name", "Name"], ["sector", "Sector"], ...SCORE_COLUMNS.map((c) => [c, c[0].toUpperCase() + c.slice(1)]), ["total_change", `${index.delta_months}m chg`]];

    const head = el("tr", {}, ...columns.map(([key, label]) => {
      const th = el("th", { textContent: label, title: index.columns[key] || "" });
      if (key === listState.sort) th.classList.add("sorted", ...(listState.asc ? ["asc"] : []));
      th.onclick = () => { listState.asc = listState.sort === key ? !listState.asc : key === "symbol" || key === "name" || key === "sector"; listState.sort = key; render(); };
      return th;
    }));
    const body = rows.slice(listState.page * PAGE_SIZE, (listState.page + 1) * PAGE_SIZE).map((r) =>
      el("tr", {},
        el("td", {}, el("a", { href: `#/s/${r.symbol}`, textContent: r.symbol })),
        el("td", { textContent: r.name || "" }),
        el("td", { textContent: r.sector || "" }),
        ...SCORE_COLUMNS.map((c) => el("td", { textContent: num(r[c]) })),
        el("td", { className: cls(r.total_change), textContent: signed(r.total_change) })));

    const prev = el("button", { textContent: "Prev", disabled: listState.page === 0, onclick: () => { listState.page--; render(); } });
    const next = el("button", { textContent: "Next", disabled: listState.page >= pages - 1, onclick: () => { listState.page++; render(); } });
    tableHost.replaceChildren(el("table", {}, el("thead", {}, head), el("tbody", {}, ...body)), el("div", { className: "pager" }, prev, el("span", { textContent: `Page ${listState.page + 1} / ${pages} (${rows.length} stocks)` }), next));
  };

  search.oninput = () => { listState.query = search.value; listState.page = 0; render(); };
  sector.onchange = () => { listState.sector = sector.value; listState.page = 0; render(); };
  render();
  view.replaceChildren(topPicks(), el("h2", { textContent: "All stocks" }), el("div", { className: "controls" }, search, sector), tableHost, columnLegend());
}

function indicatorTable(indicators) {
  const frames = Object.keys(indicators);
  const rows = [
    ["Close", (f) => num(f.close, 2)],
    ["Change %", (f) => num(f.change_pct, 2)],
    ["RSI 14", (f) => num(f.rsi, 1)],
    ["ATR 14", (f) => num(f.atr, 2)],
    ["Supertrend", (f) => `${num(f.supertrend, 2)} (${f.supertrend_direction > 0 ? "up" : "down"})`],
    ["Alligator", (f) => f.alligator],
    ["IIX 21", (f) => num(f.iix, 1)],
  ];
  return el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}), ...frames.map((f) => el("th", { textContent: f })))),
    el("tbody", {}, ...rows.map(([label, fn]) => el("tr", {}, el("td", { textContent: label }), ...frames.map((f) => el("td", { textContent: fn(indicators[f]) }))))));
}

function researchBlock(note) {
  if (!note) return el("p", { className: "muted", textContent: "No research note yet." });
  const fields = [["thesis", "Thesis"], ["bull_case", "Bull case"], ["bear_case", "Bear case"], ["risks", "Risks"], ["contradictions", "Contradictions"]];
  return el("div", { className: "note" },
    el("p", { className: "muted", textContent: `Generated by ${note.model} on ${note.generated_at.slice(0, 10)} (data as of ${note.as_of}). AI-written text, verify against the data.` }),
    ...fields.filter(([k]) => note[k]).flatMap(([k, label]) => [el("strong", { textContent: label }), el("p", { textContent: note[k] })]));
}

async function companyView(symbol) {
  view.replaceChildren(el("p", { className: "muted", textContent: "Loading..." }));
  let d;
  try { d = await loadJson(`data/symbols/${encodeURIComponent(symbol)}.json`); }
  catch { view.replaceChildren(el("p", { textContent: `No data for ${symbol}. ` }, el("a", { href: "#/", textContent: "Back" }))); return; }
  const history = d.score_history;
  const latest = Object.fromEntries(SCORE_COLUMNS.map((c) => [c, history[c][history[c].length - 1]]));
  const factors = Object.entries(d.factors).filter(([, v]) => v != null);
  view.replaceChildren(
    el("p", {}, el("a", { href: "#/", textContent: "< All stocks" })),
    el("h2", { textContent: `${d.symbol} - ${d.name || ""} (${d.sector || "n/a"})` }),
    el("p", { className: "muted", textContent: SCORE_COLUMNS.map((c) => `${c} ${num(latest[c])}`).join("   ") }),
    el("h2", { textContent: "Gauges" }),
    el("p", { className: "muted", textContent: "The technical summary is a vote of RSI, Supertrend, Alligator and IIX on one timeframe: a mechanical indicator reading, not a recommendation or investment advice. Value and overall are percentile scores vs the universe." }),
    el("div", { className: "gauges" },
      technicalGauge(d.indicators),
      scoreGauge("Value", latest.value, "Expensive", "Cheap", "P/E, P/S, P/B vs the universe"),
      scoreGauge("Overall score", latest.total, "Weak", "Strong", "average of quality, growth, value, momentum, risk")),
    el("div", { className: "grid" },
      el("div", {}, el("h2", { textContent: "Price (1y close)" }), lineChart([{ name: "close", values: d.prices.close }], d.prices.date)),
      el("div", {}, el("h2", { textContent: "Score history" }), lineChart(SCORE_COLUMNS.map((c) => ({ name: c, values: history[c] })), history.as_of))),
    el("h2", { textContent: "Indicators" }), el("div", { className: "table-wrap" }, indicatorTable(d.indicators)),
    el("h2", { textContent: "AI research note" }), researchBlock(d.research),
    el("h2", { textContent: "Latest factors" }),
    el("div", { className: "table-wrap" }, el("table", {}, el("tbody", {}, ...factors.map(([k, v]) => el("tr", {}, el("td", { textContent: k }), el("td", { textContent: Math.abs(v) >= 1000 ? v.toExponential(3) : v.toFixed(4) })))))));
}

function route() {
  const match = location.hash.match(/^#\/s\/(.+)$/);
  if (match) companyView(decodeURIComponent(match[1]));
  else listView();
  window.scrollTo(0, 0);
}

(async () => {
  index = await loadJson("data/index.json");
  document.getElementById("stamp").textContent = `Data as of ${index.as_of}.`;
  window.addEventListener("hashchange", route);
  route();
})();
