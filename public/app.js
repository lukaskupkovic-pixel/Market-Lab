"use strict";
const markets = {"BTC-USD":"Bitcoin","ETH-USD":"Ethereum","GC=F":"Zlato · futures","SI=F":"Stříbro · futures","CL=F":"Ropa WTI futures","^NDX":"Nasdaq 100","^GSPC":"S&P 500"};
const status = document.querySelector("#status");
const nav = document.querySelector("#markets");
const detail = document.querySelector("#detail");
let snapshot = {};
let current = "BTC-USD";
const researchPreview = new URLSearchParams(window.location.search).get("research") === "1";
const number = new Intl.NumberFormat("cs-CZ", {maximumFractionDigits: 3});
const dateTime = new Intl.DateTimeFormat("cs-CZ", {dateStyle:"medium",timeStyle:"short",timeZone:"Europe/Prague"});
const pct = p => Number.isFinite(p) ? number.format(p * 100) + " %" : "—";
const fmt = p => Number.isFinite(p) ? number.format(p) : "—";
const price = p => Number.isFinite(p) ? new Intl.NumberFormat("cs-CZ", {minimumFractionDigits:2, maximumFractionDigits:2}).format(p) : "—";
const marketHeadlines = {
  "BTC-USD":["BTC/USD · Bitcoin","Spotový trh · USD"],
  "ETH-USD":["ETH/USD · Ethereum","Spotový trh · USD"],
  "GC=F":["XAU/USD · Gold","GC=F futures proxy · není spot XAU/USD"],
  "SI=F":["XAG/USD · Silver","SI=F futures proxy · není spot XAG/USD"],
  "CL=F":["WTI · Crude oil","Kontinuální futures · USD"],
  "^NDX":["Nasdaq 100","Akciový index · body"],
  "^GSPC":["S&P 500","Akciový index · body"],
};
const chart = (points, reliability = false) => {
  if (!points.length) return "";
  const ys = points.map(p => p[1]);
  const min = reliability ? 0 : Math.min(...ys);
  const span = reliability ? 1 : Math.max(1e-9, Math.max(...ys) - min);
  const map = ([x,y], i) => [12 + 376 * (reliability ? x : i / Math.max(1, points.length - 1)), 126 - 114 * (y - min) / span];
  const plot = points.map(map);
  return `<svg viewBox="0 0 400 138" role="img" aria-label="${reliability ? "Kalibrace: předpovězený podíl růstu proti pozorovanému" : "Vývoj denních uzavíracích cen"}">
  ${reliability ? '<path d="M12 126 L388 12" stroke="#8b8e98" stroke-dasharray="4 4"/>' : ""}
  <polyline points="${plot.map(pair=>pair.join(",")).join(" ")}" fill="none" stroke="#64edab" stroke-width="2"/>
  ${reliability ? plot.map(([x,y]) => `<circle cx="${x}" cy="${y}" r="4" fill="#64edab"/>`).join("") : ""}</svg>`;
};

let view = "signals";
function assess(m) {
  if (m?.up == null) return {label:"Nedostatek dat", reason:"Odhad není k dispozici."};
  if (m.stale) return {label:"Starší data", reason:"Poslední aktualizace trhu selhala."};
  if (m.quality?.missing_context?.length) return {label:"Bez signálu", reason:"Chybí některé z požadovaných kontextových řad: " + m.quality.missing_context.join(", ") + "."};
  const b = m.metrics;
  if (!b || typeof b.weak !== "boolean") return {label:"Nedostatek dat", reason:"Historické ověření chybí."};
  if (b.test_count < 50) return {label:"Bez signálu", reason:"V testu je méně než 50 nepřekrývajících se výhledů."};
  if (b.weak) return {label:"Bez signálu", reason:`Zatím neprokázaná výhoda. Brier ${fmt(b.brier)} proti ${fmt(b.best_baseline_brier ?? Math.min(.25,b.baseline_brier))}. Požadujeme zlepšení alespoň 0,005 a kladnou dolní mez 95% bootstrap intervalu.`};
  return {label:"Sledovat", reason:"Model překonal jednoduché reference na oddělených testovacích datech, včetně intervalu nejistoty. Minulé výsledky nezaručují budoucí."};
}
function scout(m) {
  const momentum = m.indicators?.ret5;
  const average = m.indicators?.ma10;
  if (!Number.isFinite(momentum) || !Number.isFinite(average)) return "Krátkodobé indikátory chybí.";
  return `Momentum za 5 seancí ${pct(momentum)}. Cena je ${pct(Math.abs(average))} ${average >= 0 ? "nad" : "pod"} desetidenním průměrem.`;
}
function directionSummary(probability) {
  if (!Number.isFinite(probability)) return "Není k dispozici";
  if (probability >= .65) return "Převaha růstu";
  if (probability >= .5) return "Mírná převaha růstu";
  if (probability > .35) return "Mírná převaha poklesu";
  return "Převaha poklesu";
}
function explainForecast(m, verdict) {
  const momentum = m.indicators?.ret5;
  const volRatio = m.indicators?.vol_ratio;
  const sentences = [];
  if (Number.isFinite(momentum)) {
    sentences.push(`Pětidenní momentum je ${pct(momentum)} (${momentum >= 0 ? "kladné" : "záporné"}).`);
  }
  if (Number.isFinite(volRatio)) {
    sentences.push(volRatio > 1.3
      ? "Krátkodobá volatilita je výrazně vyšší než třicetidenní průměr."
      : "Krátkodobá volatilita není výrazně zvýšená vůči třicetidennímu období.");
  }
  sentences.push(`Tržní režim: ${m.regime || "neurčený"}.`);
  if (verdict.label !== "Sledovat") {
    sentences.push("Historický test zatím neprokázal dostatečnou predikční výhodu.");
  }
  return sentences.join(" ");
}
function scenarioMarkup(symbol, m, verdict) {
  const [headline, subtitle] = marketHeadlines[symbol];
  const positive = Math.max(0, Math.min(100, 100 * m.up));
  const negative = 100 - positive;
  const good = verdict.label === "Sledovat";
  const range = m.reference_range;
  const rangeAvailable = Number.isFinite(range?.low) && Number.isFinite(range?.high);
  const rangeUnit = symbol.startsWith("^") ? "bodů" : "USD";
  const rangeValue = rangeAvailable ? `${price(range.low)}–${price(range.high)} ${rangeUnit}` : "Zatím nedostupné";
  return `<article class="panel forecast-panel" aria-label="Sedmidenní pravděpodobnostní scénáře">
    <div class="forecast-heading">
      <div class="forecast-title">
        <span class="forecast-icon" aria-hidden="true">⌁</span>
        <div><h2>${headline}</h2><p>${subtitle} · výhled 7 dní</p></div>
      </div>
      <span class="forecast-badge ${good ? "badge-good" : "badge-warn"}">${good ? "Historicky ověřeno" : "Zatím neověřeno"}</span>
    </div>
    <div class="scenario-grid">
      <div class="scenario-card scenario-up"><span>Růst</span><strong>${pct(m.up)}</strong></div>
      <div class="scenario-card scenario-neutral"><span>Neutrální</span><strong>—</strong><small>Nemodelováno</small></div>
      <div class="scenario-card scenario-down"><span>Pokles*</span><strong>${pct(1-m.up)}</strong></div>
    </div>
    <p class="scenario-note">* Pokles zahrnuje i stejnou cenu. Současný model rozlišuje dvě třídy; samostatnou pravděpodobnost neutrálního scénáře zatím nepočítá.</p>
    <div class="probability-title"><span>Pravděpodobnostní výhled</span><strong>7 dní</strong></div>
    <div class="probability-bar" role="img" aria-label="Pravděpodobnost růstu ${pct(m.up)}, poklesu nebo stejné ceny ${pct(1-m.up)}">
      <div class="bar-up" style="width:${positive}%"></div>
      <div class="bar-down" style="width:${negative}%"></div>
    </div>
    <div class="forecast-facts">
      <div><span>Nejpravděpodobnější směr</span><strong>${directionSummary(m.up)}</strong></div>
      <div><span>Tržní režim</span><strong>${m.regime || "Neurčený"}</strong></div>
      <div><span>Historické 80% pásmo · 7 dní</span><strong>${rangeValue}</strong><small>Orientační historické rozpětí, není to predikční interval${range?.count ? " · " + range.count + " výhledů" : ""}</small></div>
      <div><span>Kvalita modelu</span><strong class="${good ? "quality-good" : "quality-warning"}">${verdict.label}</strong></div>
    </div>
    <div class="explanation-box">
      <h3><span aria-hidden="true">✧</span> Vysvětlení předpovědi</h3>
      <p>${explainForecast(m, verdict)}</p>
      <p class="explanation-disclaimer">Jde o popis tržních ukazatelů, nikoli o prokázanou příčinu rozhodnutí statistického modelu.</p>
    </div>
    <p class="forecast-footnote">Odhad od uzavření ${m.date} · cíl ${m.target} (první následující závěr při uzavřeném trhu). Pravděpodobnost není obchodní doporučení.</p>
    <details class="source-details"><summary>Model, vstupy a kvalita dat</summary>
      <dl class="agent-notes"><dt>Scout</dt><dd>${scout(m)}</dd><dt>Model</dt><dd>Varianta ${m.metrics.selected_model || "původní"} · odhad růstu ${pct(m.up)}</dd><dt>Skeptik</dt><dd>${verdict.reason}</dd></dl>
      <p>Zdroj: ${m.quality?.source || "Yahoo Finance Chart"} · stáří seance ${m.quality?.age_days ?? "—"} dní · ${m.quality?.bars ?? "—"} svíček.</p>
      <p>Kontextové řady: ${(m.context || []).join(", ") || "nedostupné"} (s časovým posunem).</p>
      <dl class="indicator-grid">
        <dt>RSI 14</dt><dd>${fmt(m.indicators?.rsi14)}</dd>
        <dt>Momentum 20 seancí</dt><dd>${pct(m.indicators?.ret20)}</dd>
        <dt>Volatilita 30 seancí</dt><dd>${pct(m.indicators?.vol30)}</dd>
        <dt>Odchylka od SMA 10</dt><dd>${pct(m.indicators?.ma10)}</dd>
      </dl>
      ${m.quality?.warnings?.length ? `<p class="warn">${m.quality.warnings.join(" · ")}</p>` : ""}
      ${m.quality?.missing_context?.length ? `<p class="warn">Chybějící kontext: ${m.quality.missing_context.join(", ")}</p>` : ""}
    </details>
  </article>`;
}
const tabs = document.createElement("div");
tabs.className = "view-tabs";
tabs.setAttribute("role", "group");
tabs.setAttribute("aria-label", "Zobrazení detailu");
const views = {signals:"Signály", stats:"Statistiky", report:"Reportér"};
for (const [id,label] of Object.entries(views)) {
  const button = document.createElement("button");
  button.textContent = label;
  button.dataset.view = id;
  button.onclick = () => {view = id; render();};
  tabs.append(button);
}
detail.before(tabs);


function reporter(symbol) {
  const records = Object.values(snapshot.forecasts ?? {}).filter(f => f.symbol === symbol)
    .sort((a,b) => (b.created ?? b.date).localeCompare(a.created ?? a.date));
  const settled = records.filter(f => f.outcome === "up" || f.outcome === "flat_or_down");
  const buckets = new Map();
  for (const f of settled) {
    const low = Math.min(95, 5 * Math.floor(f.up * 20));
    const bucket = buckets.get(low) ?? {total:0, up:0};
    bucket.total++;
    if (f.outcome === "up") bucket.up++;
    buckets.set(low, bucket);
  }
  const rows = [...buckets].sort(([a],[b]) => a-b).map(([low,b]) =>
    `<dt>${low}–${low+5} %</dt><dd>${b.up} z ${b.total} rostlo · ${pct(b.up/b.total)}</dd>`).join("");
  const history = records.slice(0,20).map(f => {
    const result = f.outcome === "up" ? "Růst" : f.outcome === "flat_or_down" ? "Pokles / beze změny" : "Čeká na závěr";
    const published = f.created ? dateTime.format(new Date(f.created)) : f.date;
    return `<dt>${published}<br><small>Cíl ${f.target}</small></dt><dd>${pct(f.up)} růst<br><small>${result}${f.outcome_date ? " · "+f.outcome_date : ""}</small></dd>`;
  }).join("");
  return `<article class="panel"><h2>Reportér · ${markets[symbol]}</h2>
  <p>${records.length} zveřejněných · ${settled.length} vyhodnocených · ${records.length-settled.length} čeká</p>
  <h3>Růst podle pásma odhadu</h3>
  ${rows ? `<dl class="agent-notes">${rows}</dl><p>Počty zahrnují i překrývající se výhledy.</p>` : "<p>Zatím žádný dokončený výhled.</p>"}
  <h3>Poslední zveřejněné odhady</h3>
  ${history ? `<dl class="agent-notes">${history}</dl>` : "<p>Historie zatím není dostupná.</p>"}</article>`;
}

function render() {
  for (const button of tabs.children) button.setAttribute('aria-pressed', button.dataset.view === view);
  nav.replaceChildren();
  for (const [symbol,name] of Object.entries(markets)) {
    const m = snapshot.markets?.[symbol];
    const button = document.createElement("button");
    button.setAttribute("aria-pressed", symbol === current);
    const verdict = assess(m);
    button.innerHTML = `<small>${name}</small><strong class="${verdict.label === "Sledovat" ? (m.up >= .5 ? "up" : "down") : ""}">${verdict.label === "Sledovat" ? pct(m.up) : verdict.label}</strong><small>${verdict.label === "Sledovat" ? "Odhad růstu · 7 dní" : verdict.reason.split(". ")[0]}</small>`;
    button.onclick = () => {current = symbol; render();};
    nav.append(button);
  }
  const m = snapshot.markets?.[current];
  if (view === "report") {
    detail.innerHTML = reporter(current);
    return;
  }
  if (m?.up == null || !m.metrics) {
    detail.innerHTML = `<div class="panel"><h2>${markets[current]}</h2><p>Pro tento trh zatím není dostupná ověřená datová sada a modelový odhad.</p></div>`;
    return;
  }
  const b = m.metrics;
  const q = m.quote;
  const verdict = assess(m);
  detail.innerHTML = scenarioMarkup(current, m, verdict) + `<article class="panel market-chart-panel"><h2>Vývoj ceny · ${markets[current]}</h2>
  <div class="stats"><div>Poslední kotace <strong>${fmt(q?.price ?? m.close)}</strong><br><small>${q?.timestamp ? dateTime.format(new Date(q.timestamp * 1000)) : m.date} · Yahoo Finance</small></div><div>Poslední uzavřená seance <strong>${pct(m.change)}</strong><br><small>${m.date} · závěr ${fmt(m.close)}</small></div></div>
  ${chart(m.prices)}
  <p>${m.prices[0][0]} až ${m.prices.at(-1)[0]} · denní závěry</p></article>
  <article class="panel" data-statistics><h2>Historické ověření</h2>
  <p>${b.test_start} až ${b.test_end} · ${b.test_count} nepřekrývajících se výhledů · výběr modelu proběhl na starších validačních datech</p>
  <dl><dt>Vybraný model</dt><dd>${b.selected_model ?? "původní"}</dd><dt>Accuracy</dt><dd>${pct(b.accuracy)}</dd><dt>Brier score</dt><dd>${fmt(b.brier)}</dd><dt>Log loss</dt><dd>${fmt(b.log_loss)}</dd><dt>Brier historické četnosti</dt><dd>${fmt(b.baseline_brier)}</dd><dt>Brier odhadu 50 %</dt><dd>${fmt(b.fair_coin_brier ?? .25)}</dd><dt>Brier momentum reference</dt><dd>${fmt(b.momentum_brier)}</dd><dt>Zlepšení proti nejlepší referenci</dt><dd>${fmt(b.improvement)}</dd><dt>95% bootstrap interval zlepšení</dt><dd>${b.improvement_ci ? b.improvement_ci.map(fmt).join(" až ") : "—"}</dd></dl>
  <p>Samostatné modely na závěrečném testu: ${b.test_candidates_brier ? Object.entries(b.test_candidates_brier).map(([k,v])=>k+": "+fmt(v)).join(" · ") : "nejsou k dispozici"}. Nejde o výsledky reálných obchodů.</p>
  ${chart(m.reliability.map(b=>[b.predicted,b.observed]),true)}
  <p>Kalibrace · osa x odhad, osa y pozorovaná četnost. Obě osy 0–100 %.</p>
  </article>`;
  for (const panel of detail.children) panel.hidden = view === "stats" ? !panel.hasAttribute("data-statistics") : panel.hasAttribute("data-statistics");
}
async function load() {
  status.textContent = researchPreview ? "Načítám výzkumný snapshot v2…" : "Načítám poslední zveřejněná data…";
  try {
    const response = await fetch(researchPreview ? "./research-v2.json" : "./data.json", {cache:"no-store"});
    if (!response.ok) throw Error(response.status);
    snapshot = await response.json();
    status.textContent = researchPreview ?
      `VÝZKUMNÝ NÁHLED v2 · historický snapshot z ${dateTime.format(new Date(snapshot.updated))} · není živě aktualizován ani určen k obchodování` :
      `Poslední zpracování ${dateTime.format(new Date(snapshot.updated))}`;
    if (Object.keys(snapshot.errors ?? {}).length) status.textContent += " · některé zdroje nejsou dostupné";
  } catch {
    status.textContent = "Zveřejněná data se nepodařilo načíst.";
  }
  render();
}
document.querySelector("#reload").onclick = load;
render();
load();
