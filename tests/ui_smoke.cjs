/* Offline rendering smoke test, without a browser or external requests. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

async function verify(query, filename) {
  const data = JSON.parse(fs.readFileSync(filename, "utf8"));
  const make = () => ({
    dataset: {}, children: [], attributes: {},
    setAttribute(k, v) { this.attributes[k] = v; },
    append(child) { this.children.push(child); },
    before() {},
    replaceChildren() { this.children = []; },
    innerHTML: "",
    textContent: "",
  });
  const status = make();
  const markets = make();
  const detail = make();
  const reload = make();
  const nodes = {"#status": status, "#markets": markets, "#detail": detail, "#reload": reload};
  const document = { querySelector: key => nodes[key], createElement: make };
  const context = {
    document, window: {location: {search: query}}, URLSearchParams,
    Intl, Date, Number, console,
    fetch: async () => ({ok: true, json: async () => data}),
  };
  vm.runInNewContext(fs.readFileSync("public/app.js", "utf8"), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(markets.children.length, 7);
  assert.match(detail.innerHTML, /scenario-grid/);
  assert.match(detail.innerHTML, /Neutrální/);
  assert.match(detail.innerHTML, /Nemodelováno/);
  assert.match(detail.innerHTML, /Historické 80% pásmo/);
  assert.match(detail.innerHTML, /Vysvětlení předpovědi/);
  if (query.includes("research=1")) assert.match(detail.innerHTML, /Citlivost aktuálního modelu/);
  markets.children[3].onclick(); // SI futures: should show a silver proxy label.
  assert.match(detail.innerHTML, /XAG\/USD · Silver/);
  assert.match(detail.innerHTML, /není spot XAG\/USD/);
  if (query.includes("research=1")) assert.match(status.textContent, /VÝZKUMNÝ NÁHLED/);
}

(async () => {
  await verify("?research=1", "public/research-v3.json");
  await verify("", "public/data.json");
  console.log("UI rendering: research and default snapshot passed");
})().catch(error => {console.error(error); process.exitCode = 1;});
