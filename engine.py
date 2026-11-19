"""Seven-calendar-day directional research model. No order execution."""
import numpy as np
import pandas as pd
import json
from urllib.parse import quote
from urllib.request import Request, urlopen
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, accuracy_score, log_loss
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ASSETS = {
    "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "Zlato (futures proxy)": "GC=F",
    "Stříbro (futures proxy)": "SI=F", "Ropa WTI futures": "CL=F",
    "Nasdaq 100": "^NDX", "S&P 500": "^GSPC",
}
FEATURES = ["ret1", "ret5", "ret20", "vol10", "vol30", "vol_ratio", "downside_vol20",
            "drawdown20", "ma10", "ma30", "range", "volume_z", "rsi14", "ema20",
            "macd", "support", "resistance"]

# Market-specific cross-asset context. Each source is lagged in analyze() to avoid
# using information from another market's close that was not available yet.
CONTEXT_BY_SYMBOL = {
    "BTC-USD": {"eth": "ETH-USD", "sp500": "^GSPC", "usd": "DX-Y.NYB", "us10y": "^TNX"},
    "ETH-USD": {"btc": "BTC-USD", "sp500": "^GSPC", "usd": "DX-Y.NYB", "us10y": "^TNX"},
    "GC=F": {"silver": "SI=F", "sp500": "^GSPC", "usd": "DX-Y.NYB", "us10y": "^TNX"},
    "SI=F": {"gold": "GC=F", "sp500": "^GSPC", "usd": "DX-Y.NYB", "us10y": "^TNX"},
    "CL=F": {"sp500": "^GSPC", "usd": "DX-Y.NYB", "us10y": "^TNX"},
    "^NDX": {"sp500": "^GSPC", "usd": "DX-Y.NYB", "us10y": "^TNX", "btc": "BTC-USD"},
    "^GSPC": {"nasdaq": "^NDX", "usd": "DX-Y.NYB", "us10y": "^TNX", "btc": "BTC-USD"},
}


def validate_history(df, symbol, today=None):
    """Reject unusable or stale observations before issuing *new* forecasts.

    Historical futures can be negative (WTI in 2020); don't assume positive prices.
    """
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(df.columns) or len(df) < 550:
        raise ValueError("Nedostatečná historie OHLC (minimálně 550 pozorování).")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("Historie není jednoznačně seřazena podle data.")
    prices = df[list(required)].apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(prices).all(axis=1)
    consistent = ((prices.High >= prices.Low) &
                  (prices.High >= prices[["Open", "Close"]].max(axis=1) - 1e-6) &
                  (prices.Low <= prices[["Open", "Close"]].min(axis=1) + 1e-6))
    invalid = int((~finite | ~consistent).sum())
    if invalid > max(3, int(len(df) * .01)) or not (finite.iloc[-1] and consistent.iloc[-1]):
        raise ValueError(f"Nekonzistentní či chybějící OHLC data ({invalid} řádků).")
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.now(tz="UTC").tz_localize(None)
    age = (today.normalize() - df.index[-1].normalize()).days
    if age < 0 or age > (2 if symbol.endswith("-USD") else 7):
        raise ValueError(f"Neaktuální uzavřená seance ({age} kalendářních dní).")
    warnings = []
    if invalid:
        warnings.append(f"{invalid} historických svíček má nekonzistentní OHLC")
    if (df.index.to_series().diff().dt.days.dropna() > 12).any():
        warnings.append("Historie obsahuje delší výpadek kotací")
    if symbol in ("GC=F", "SI=F", "CL=F"):
        warnings.append("Kontinuální futures mohou obsahovat skoky při rolování kontraktů")
    return {"source": "Yahoo Finance Chart", "bars": len(df), "age_days": age, "warnings": warnings}

def fetch(symbol):
    errors = []
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?range=10y&interval=1d"
        try:
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as response:
                result = json.load(response)["chart"]["result"][0]
            meta = result["meta"]
            stamps = pd.to_datetime(result["timestamp"], unit="s", utc=True)
            dates = stamps.tz_convert(meta["exchangeTimezoneName"]).normalize().tz_localize(None)
            df = pd.DataFrame(result["indicators"]["quote"][0], index=dates).rename(columns=str.title)
            df = df.sort_index().loc[lambda d: ~d.index.duplicated(keep="last")].dropna(subset=["Close"])
            # Use only completed local calendar days for the daily model.
            today = pd.Timestamp.now(tz=meta["exchangeTimezoneName"]).normalize().tz_localize(None)
            df = df.loc[df.index < today].copy()
            if df.empty:
                raise ValueError("empty history")
            quality = validate_history(df, symbol)
            df.attrs["quote"] = {"price": meta.get("regularMarketPrice"),
                                 "timestamp": meta.get("regularMarketTime")}
            df.attrs["quality"] = quality
            return df
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            errors.append(str(error))
    raise ValueError(f"{symbol}: {' / '.join(errors)}")

def features(df):
    x = pd.DataFrame(index=df.index)
    close = df["Close"].astype(float)
    scale = close.shift(1).abs().replace(0, np.nan)
    r = close.diff() / scale
    x["ret1"] = r
    x["ret5"] = (close - close.shift(5)) / close.shift(5).abs()
    x["ret20"] = (close - close.shift(20)) / close.shift(20).abs()
    x["vol10"] = r.rolling(10).std()
    x["vol30"] = r.rolling(30).std()
    x["vol_ratio"] = (x["vol10"] / x["vol30"].replace(0, np.nan)).clip(0, 10)
    x["downside_vol20"] = r.clip(upper=0).rolling(20).std()
    x["drawdown20"] = close / close.rolling(20).max().replace(0, np.nan) - 1
    x["ma10"] = close / close.rolling(10).mean() - 1
    x["ma30"] = close / close.rolling(30).mean() - 1
    x["range"] = (df["High"] - df["Low"]) / close
    if "Volume" in df:
        vol = df["Volume"].astype(float).replace(0, np.nan)
        x["volume_z"] = ((vol - vol.rolling(30).mean()) / vol.rolling(30).std()).clip(-5,5)
    else: x["volume_z"] = 0.0
    delta = close.diff(); up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    x["rsi14"] = 100 - 100 / (1 + up / down.replace(0,np.nan))
    x["ema20"] = (close - close.ewm(span=20, adjust=False).mean()) / close.abs()
    x["macd"] = (close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()) / close.abs()
    x["support"] = (close - df["Low"].rolling(20).min()) / close.abs()
    x["resistance"] = (df["High"].rolling(20).max() - close) / close.abs()
    x["rsi14"] = x["rsi14"].mask((down == 0) & (up > 0), 100).mask((down == 0) & (up == 0), 50)
    x = x.replace([np.inf,-np.inf],np.nan)
    x["volume_z"] = x["volume_z"].fillna(0)
    return x

def labels(df):
    # First close on or after 7 calendar days; cap at 10 days for market closures.
    dates = df.index
    vals = df["Close"].to_numpy(dtype=float)
    future_idx = dates.searchsorted(dates + pd.Timedelta(days=7), side="left")
    y = np.full(len(df), np.nan)
    valid = future_idx < len(df)
    rows = np.where(valid)[0]
    valid_rows = rows[(dates[future_idx[rows]] - dates[rows]).days <= 10]
    y[valid_rows] = (vals[future_idx[valid_rows]] > vals[valid_rows]).astype(float)
    # Last observation date for label availability; used for purging.
    ends = pd.Series(pd.NaT,index=dates,dtype="datetime64[ns]")
    ends.iloc[valid_rows] = dates[future_idx[valid_rows]]
    return pd.Series(y,index=dates), ends

def fit_candidates(X, y):
    """Two deliberately different learners: a regularized linear baseline and
    a shallow non-linear model. Neither receives future labels or test data.
    """
    linear = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=0.3, max_iter=400, random_state=42),
    )
    boosted = HistGradientBoostingClassifier(
        max_iter=80, max_leaf_nodes=7, min_samples_leaf=30,
        learning_rate=0.045, l2_regularization=8, random_state=42,
    )
    linear.fit(X, y.astype(int))
    boosted.fit(X, y.astype(int))
    return {"linear": linear, "boosted": boosted}


def candidate_probabilities(models, X):
    linear = models["linear"].predict_proba(X)[:, 1]
    boosted = models["boosted"].predict_proba(X)[:, 1]
    # The blend weight is fixed ahead of validation, never fitted on the test set.
    return {"linear": linear, "boosted": boosted, "blend": 0.5 * (linear + boosted)}


def log_odds(prob):
    clipped = np.clip(np.asarray(prob, dtype=float), 1e-5, 1 - 1e-5)
    return np.log(clipped / (1 - clipped)).reshape(-1, 1)


def independent_indices(dates, ends, start, stop, known_before=None):
    """Chronologically select forecast labels whose outcome windows do not overlap."""
    result = []
    previous_end = pd.Timestamp.min
    for i in range(start, stop):
        end = ends.at[dates[i]]
        if pd.isna(end) or (known_before is not None and end >= known_before):
            continue
        if dates[i] > previous_end:
            result.append(i)
            previous_end = end
    return np.asarray(result, dtype=int)


def market_regime(indicators):
    """Descriptive, rule-based regime diagnostic; not a validated model signal."""
    ret = indicators.get("ret20", np.nan)
    vol = indicators.get("vol30", np.nan)
    ratio = indicators.get("vol_ratio", np.nan)
    if not np.isfinite(ret) or not np.isfinite(vol) or vol <= 0:
        return "Neurčený"
    standardized = ret / (vol * np.sqrt(20))
    direction = "Růstový" if standardized > 1 else "Klesající" if standardized < -1 else "Boční"
    if np.isfinite(ratio) and ratio > 1.3:
        return direction + " · zvýšená volatilita"
    return direction


def analyze(df, context=None):
    X = features(df)
    for name, series in (context or {}).items():
        # One observation lag on the union calendar: no concurrent external close.
        prior = series.reindex(series.index.union(X.index)).sort_index().ffill(limit=4).shift(1).reindex(X.index)
        change = prior.diff() / prior.shift(1).abs().replace(0, np.nan)
        X[f"{name}_change"] = change
        X[f"{name}_corr"] = X["ret1"].rolling(30, min_periods=15).corr(change)
    columns = list(X.columns)
    X = X.replace([np.inf, -np.inf], np.nan)
    y, label_end = labels(df)
    dataset = X.join(y.rename("target")).dropna(subset=["target", "ret20", "vol30"])
    if len(dataset) < 550:
        raise ValueError("Pro validaci je potřeba alespoň 550 použitelných historických dnů.")

    # Outer walk-forward predictions: for every test block, training labels must
    # have matured strictly before its first date. No random shuffle.
    n = len(dataset)
    start = max(350, int(n * 0.5))
    step = 60
    predictions = {"linear": [], "boosted": [], "blend": []}
    actual, timestamps = [], []
    for i in range(start, n, step):
        train_dates = dataset.index[:i]
        train_dates = train_dates[label_end.reindex(train_dates).to_numpy() < dataset.index[i]]
        if len(train_dates) < 250:
            continue
        models = fit_candidates(dataset.loc[train_dates, columns], dataset.loc[train_dates, "target"])
        block = dataset.iloc[i:min(i + step, n)]
        block_preds = candidate_probabilities(models, block[columns])
        for key in predictions:
            predictions[key].extend(block_preds[key])
        actual.extend(block.target.astype(int))
        timestamps.extend(block.index)
    if len(actual) < 150:
        raise ValueError("Nedostatek mimovzorkových predikcí.")

    dates = pd.DatetimeIndex(timestamps)
    truth = np.asarray(actual, dtype=int)
    raw = {key: np.asarray(value, dtype=float) for key, value in predictions.items()}
    cal_end, val_end = int(len(dates) * .4), int(len(dates) * .6)
    cal_indices = np.where(label_end.loc[dates[:cal_end]].to_numpy() < dates[cal_end])[0]
    validation = independent_indices(dates, label_end, cal_end, val_end, known_before=dates[val_end])
    test_indices = independent_indices(dates, label_end, val_end, len(dates))
    if len(cal_indices) < 80 or len(validation) < 10 or len(test_indices) < 10:
        raise ValueError("Příliš krátká kalibrační, výběrová nebo testovací sada.")
    if len(np.unique(truth[cal_indices])) < 2:
        raise ValueError("Kalibrační sada obsahuje jen jeden směr.")

    # Calibrate models on the earliest OOS sample, select a model using ONLY the
    # subsequent validation slice, then evaluate the selected model on untouched
    # final-period observations. This prevents selecting by test-set luck.
    calibrators = {}
    validation_scores = {}
    for name, pred in raw.items():
        calibrator = LogisticRegression(C=1.0, random_state=42)
        calibrator.fit(log_odds(pred[cal_indices]), truth[cal_indices])
        calibrators[name] = calibrator
        validated = calibrator.predict_proba(log_odds(pred[validation]))[:, 1]
        validation_scores[name] = float(brier_score_loss(truth[validation], validated))
    selected = min(validation_scores, key=validation_scores.get)
    p_test = calibrators[selected].predict_proba(log_odds(raw[selected][test_indices]))[:, 1]
    test_truth = truth[test_indices]
    test_dates = dates[test_indices]

    # Two constant baselines and a deliberately fixed momentum heuristic.
    # The reference is the strongest of them, so gating is conservative.
    historical_up = float(truth[cal_indices].mean())
    reference = {
        "historical": np.full(len(test_indices), historical_up),
        "fair_coin": np.full(len(test_indices), 0.5),
        "momentum": np.where(X.loc[test_dates, "ret20"].to_numpy() > 0, 0.55, 0.45),
    }
    baseline_scores = {key: float(brier_score_loss(test_truth, value)) for key, value in reference.items()}
    baseline_name = min(baseline_scores, key=baseline_scores.get)
    best_baseline = baseline_scores[baseline_name]
    brier = float(brier_score_loss(test_truth, p_test))
    diff = (test_truth - reference[baseline_name]) ** 2 - (test_truth - p_test) ** 2
    rng = np.random.default_rng(42)
    # These outcome windows do not overlap. Bootstrap describes sampling
    # uncertainty, not uncertainty about changes in future market regimes.
    bootstrap = rng.choice(diff, size=(1000, len(diff)), replace=True).mean(axis=1)
    ci_lower, ci_upper = np.quantile(bootstrap, [.025, .975])
    improvement = best_baseline - brier

    metrics = {
        "brier": brier,
        "accuracy": float(accuracy_score(test_truth, p_test >= .5)),
        "log_loss": float(log_loss(test_truth, p_test, labels=[0, 1])),
        "baseline_brier": baseline_scores["historical"],
        "fair_coin_brier": baseline_scores["fair_coin"],
        "momentum_brier": baseline_scores["momentum"],
        "best_baseline": baseline_name,
        "best_baseline_brier": best_baseline,
        "improvement": improvement,
        "improvement_ci": [float(ci_lower), float(ci_upper)],
        "selected_model": selected,
        "validation_brier": validation_scores,
        "test_candidates_brier": {
            key: float(brier_score_loss(test_truth, calibrators[key].predict_proba(log_odds(raw[key][test_indices]))[:, 1]))
            for key in raw
        },
        "test_count": len(test_indices),
        "test_start": str(test_dates[0].date()),
        "test_end": str(test_dates[-1].date()),
    }
    metrics["weak"] = len(test_indices) < 50 or improvement < .005 or ci_lower <= 0

    # Final inference may learn from all outcomes already matured as of the
    # latest completed bar, without changing held-out evaluation metrics.
    last_date = X.index[-1]
    train_idx = dataset.index[label_end.reindex(dataset.index).to_numpy() <= last_date]
    latest_models = fit_candidates(dataset.loc[train_idx, columns], dataset.loc[train_idx, "target"])
    latest_raw = candidate_probabilities(latest_models, X.loc[[last_date], columns])[selected]
    mature = np.where(label_end.loc[dates].to_numpy() <= last_date)[0]
    current_calibrator = LogisticRegression(C=1.0, random_state=42)
    current_calibrator.fit(log_odds(raw[selected][mature]), truth[mature])
    probability = float(current_calibrator.predict_proba(log_odds(latest_raw))[0, 1])

    test = pd.DataFrame({"date": test_dates, "actual": test_truth, "probability": p_test})
    test["bucket"] = pd.cut(test.probability, bins=np.linspace(0, 1, 6), include_lowest=True)
    reliability = test.groupby("bucket", observed=False).agg(
        predicted=("probability", "mean"), observed=("actual", "mean"),
        count=("actual", "size")).dropna().reset_index(drop=True)
    indicator = X.loc[last_date, FEATURES]
    return {
        "probability": probability, "metrics": metrics, "test": test,
        "reliability": reliability, "last_date": last_date,
        "last_close": float(df.loc[last_date, "Close"]),
        "history": df, "indicators": indicator,
        "regime": market_regime(indicator),
    }
