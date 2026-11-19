"""Build a public snapshot and append immutable forecasts."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from engine import ASSETS, CONTEXT_BY_SYMBOL, analyze, fetch

logging.basicConfig(level=logging.INFO)
OUTPUT = Path("public/data.json")
VERSION = "daily-ensemble-v3"


def refresh():
    now = datetime.now(timezone.utc).isoformat()
    old = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    history = old.get("forecasts", {})
    results = {}
    series = {}
    errors = {}
    symbols = list(dict.fromkeys([*ASSETS.values(), "DX-Y.NYB", "^TNX"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        requests = {symbol: pool.submit(fetch, symbol) for symbol in symbols}
        for symbol, request in requests.items():
            try:
                series[symbol] = request.result()
            except Exception as error:
                logging.warning("%s: %s", symbol, error)
                errors[symbol] = "Zdroj dat je nedostupný"
    for name, symbol in ASSETS.items():
        try:
            df = series[symbol]
            expected = CONTEXT_BY_SYMBOL.get(symbol, {})
            context = {name: series[src]["Close"] for name, src in expected.items()
                       if src != symbol and src in series}
            missing_context = [name for name, src in expected.items() if src not in series]
            model = analyze(df, context)
            date = model["last_date"]
            close = model["last_close"]
            prior = float(df.Close.iloc[-2])
            probability = model["probability"]
            date_text = str(date.date())
            key = f"{symbol}/{date_text}/{VERSION}"
            for record in history.values():
                if record["symbol"] != symbol or "outcome" in record:
                    continue
                evaluation = pd.Timestamp(record["target"])
                later = df.loc[df.index >= evaluation, "Close"]
                if not later.empty:
                    record["outcome"] = "up" if float(later.iloc[0]) > record["close"] else "flat_or_down"
                    record["outcome_date"] = str(later.index[0].date())
            history.setdefault(key, {
                "symbol": symbol, "date": date_text, "close": close, "up": probability,
                "target": str((date + pd.Timedelta(days=7)).date()), "created": now,
            })
            results[symbol] = {
                "name": name, "date": date_text, "close": close,
                "change": (close - prior) / abs(prior) if prior else None,
                "quote": df.attrs.get("quote"), "up": history[key]["up"],
                "target": history[key]["target"], "metrics": model["metrics"],
                "reliability": model["reliability"].to_dict("records"),
                "indicators": model["indicators"].astype(object).where(model["indicators"].notna(), None).to_dict(),
                "regime": model["regime"],
                "reference_range": model["reference_range"],
                "quality": {**df.attrs.get("quality", {}), "missing_context": missing_context},
                "model_version": VERSION,
                "context": list(context),
                "prices": [[str(d.date()), float(c)] for d, c in df.Close.tail(120).items()],
            }
        except Exception:
            logging.exception("Analysis failed: %s", symbol)
            errors[symbol] = "Aktualizace analýzy selhala"
            results[symbol] = {**old.get("markets", {}).get(symbol, {}), "name": name, "stale": True}
    payload = {"updated": now, "markets": results, "forecasts": history, "errors": errors}
    if any("up" in data and not data.get("stale") for data in results.values()):
        pending = OUTPUT.with_suffix(".tmp")
        pending.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        pending.replace(OUTPUT)
    return not errors


if __name__ == "__main__":
    raise SystemExit(0 if refresh() else 1)
