"use strict";
const markets = {"BTC-USD":"Bitcoin","ETH-USD":"Ethereum","GC=F":"Zlato · futures","SI=F":"Stříbro · futures","CL=F":"Ropa WTI futures","^NDX":"Nasdaq 100","^GSPC":"S&P 500"};
const status = document.querySelector("#status");
const nav = document.querySelector("#markets");
const detail = document.querySelector("#detail");
let snapshot = {};
let current = "BTC-USD";
const number = new Intl.NumberFormat("cs-CZ", {maximumFractionDigits: 3});
const dateTime = new Intl.DateTimeFormat("cs-CZ", {dateStyle:"medium",timeStyle:"short",timeZone:"Europe/Prague"});
const pct = p => Number.isFinite(p) ? number.format(p * 100) + " %" : "—";
const fmt = p => Number.isFinite(p) ? number.format(p) : "—";
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
  const b = m.metrics;
  if (!b || typeof b.weak !== "boolean") return {label:"Nedostatek dat", reason:"Historické ověření chybí."};
  if (b.test_count < 50) return {label:"Bez signálu", reason:"V testu je méně než 50 nepřekrývajících se výhledů."};
  if (b.weak) return {label:"Bez signálu", reason:`Slabý backtest. Brier modelu ${fmt(b.brier)} vůči ${fmt(Math.min(.25,b.baseline_brier))} u lepšího jednoduchého odhadu. Test nedosáhl požadovaného zlepšení 0,005.`};
  return {label:"Sledovat", reason:"Model splnil nastavený práh historického ověření."};
}
function scout(m) {
  const momentum = m.indicators?.ret5;
  const average = m.indicators?.ma10;
  if (!Number.isFinite(momentum) || !Number.isFinite(average)) return "Krátkodobé indikátory chybí.";
  return `Momentum za 5 seancí ${pct(momentum)}. Cena je ${pct(Math.abs(average))} ${average >= 0 ? "nad" : "pod"} desetidenním průměrem.`;
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
  const labels = {rsi14:"RSI 14",ret5:"Momentum 5 seancí",ret20:"Momentum 20 seancí",vol30:"Volatilita 30 seancí",ma10:"Odchylka od SMA 10",ma30:"Odchylka od SMA 30",ema20:"Vzdálenost od EMA 20",macd:"MACD vůči ceně",support:"Vzdálenost od minima 20 seancí",resistance:"Vzdálenost od maxima 20 seancí"};
  detail.innerHTML = `<article class="panel"><h2>${markets[current]}</h2>
  <div class="stats"><div>Poslední kotace <strong>${fmt(q?.price ?? m.close)}</strong><br><small>${q?.timestamp ? dateTime.format(new Date(q.timestamp * 1000)) : m.date} · Yahoo Finance</small></div><div>Poslední uzavřená seance <strong>${pct(m.change)}</strong><br><small>${m.date} · závěr ${fmt(m.close)}</small></div></div>
  ${chart(m.prices)}
  <p>${m.prices[0][0]} až ${m.prices.at(-1)[0]} · denní závěry</p></article>
  <article class="panel"><h2>Sedmidenní výhled</h2><p class="${verdict.label === "Sledovat" ? "" : "warn"}">${verdict.label}</p>
  <div class="signals"><div class="${verdict.label === "Sledovat" ? "up" : ""}"><strong>${pct(m.up)}</strong>Růst</div><div class="${verdict.label === "Sledovat" ? "down" : ""}"><strong>${pct(1-m.up)}</strong>Pokles nebo stejná cena</div></div>
  <p>Modelový odhad od závěru ${m.date}. Cíl připadá na ${m.target}, při zavřeném trhu se vyhodnotí první následující závěr.</p>
  <meter class="signal-meter" min="0" max="1" value="${m.up}" aria-label="Pravděpodobnost růstu"></meter>
  <dl class="agent-notes"><dt>Scout</dt><dd>${scout(m)}</dd><dt>Model</dt><dd>Kalibrovaný odhad růstu ${pct(m.up)}.</dd><dt>Skeptik</dt><dd>${verdict.reason}</dd></dl>
  <details><summary>Vstupy modelu</summary><p>Odhad vychází z trendu, momenta, volatility a cenového rozpětí. Kontextové řady mají časový posun.</p><p>Kontext: ${m.context.join(", ") || "nedostupný"}</p>
  <dl>${Object.entries(labels).map(([k,v])=>`<dt>${v}</dt><dd>${k==="rsi14" ? fmt(m.indicators[k]) : pct(m.indicators[k])}</dd>`).join("")}</dl></details></article>
  <article class="panel" data-statistics><h2>Historické ověření</h2>
  <p>${b.test_start} až ${b.test_end} · ${b.test_count} nepřekrývajících se výhledů</p>
  <dl><dt>Accuracy</dt><dd>${pct(b.accuracy)}</dd><dt>Brier score</dt><dd>${fmt(b.brier)}</dd><dt>Log loss</dt><dd>${fmt(b.log_loss)}</dd><dt>Brier historické četnosti</dt><dd>${fmt(b.baseline_brier)}</dd><dt>Brier odhadu 50 %</dt><dd>0,25</dd></dl>
  ${chart(m.reliability.map(b=>[b.predicted,b.observed]),true)}
  <p>Kalibrace · osa x odhad, osa y pozorovaná četnost. Obě osy 0–100 %.</p>
  </article>`;
  for (const panel of detail.children) panel.hidden = view === "stats" ? !panel.hasAttribute("data-statistics") : panel.hasAttribute("data-statistics");
}
async function load() {
  status.textContent = "Načítám poslední zveřejněná data…";
  try {
    const response = await fetch("./data.json", {cache:"no-store"});
    if (!response.ok) throw Error(response.status);
    snapshot = await response.json();
    status.textContent = `Poslední zpracování ${dateTime.format(new Date(snapshot.updated))}`;
    if (Object.keys(snapshot.errors ?? {}).length) status.textContent += " · některé zdroje nejsou dostupné";
  } catch {
    status.textContent = "Zveřejněná data se nepodařilo načíst.";
  }
  render();
}
document.querySelector("#reload").onclick = load;
render();
load();
