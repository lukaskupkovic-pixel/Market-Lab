"""Seven-calendar-day directional research model. No order execution."""
import numpy as np
import pandas as pd
import json
from urllib.parse import quote
from urllib.request import Request, urlopen
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, accuracy_score, log_loss

ASSETS = {
    "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "Zlato (futures proxy)": "GC=F",
    "Stříbro (futures proxy)": "SI=F", "Ropa WTI futures": "CL=F",
    "Nasdaq 100": "^NDX", "S&P 500": "^GSPC",
}
FEATURES = ["ret1", "ret5", "ret20", "vol10", "vol30", "ma10", "ma30",
            "range", "volume_z", "rsi14", "ema20", "macd", "support", "resistance"]

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
            df.attrs["quote"] = {"price": meta.get("regularMarketPrice"),
                                 "timestamp": meta.get("regularMarketTime")}
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

def fit_model(X,y):
    model = HistGradientBoostingClassifier(max_iter=90, max_leaf_nodes=7, learning_rate=0.045, l2_regularization=5, random_state=42)
    model.fit(X,y.astype(int))
    return model

def analyze(df, context=None):
    X = features(df)
    for name, series in (context or {}).items():
        # A one-date lag avoids importing closes published later in the same session.
        prior = series.reindex(series.index.union(X.index)).sort_index().ffill(limit=4).shift(1).reindex(X.index)
        change = prior.diff() / prior.shift(1).abs()
        X[f"{name}_change"] = change
        X[f"{name}_corr"] = X["ret1"].rolling(30, min_periods=15).corr(change)
    columns = list(X.columns)
    X = X.replace([np.inf, -np.inf], np.nan)
    y, label_end = labels(df)
    dataset = X.join(y.rename("target")).dropna(subset=["target", "ret20", "vol30"])
    if len(dataset)<550: raise ValueError("Pro validaci je potřeba alespoň 550 použitelných historických dnů.")
    # Chronological walk-forward: expanding train, 7-day purged boundary, 60-observation test windows.
    n=len(dataset); start=max(350,int(n*.55)); step=60
    preds=[]; actual=[]; timestamps=[]
    for i in range(start,n,step):
        end=min(i+step,n)
        train_dates=dataset.index[:i]
        train_dates=train_dates[label_end.reindex(train_dates).to_numpy() < dataset.index[i]]
        if len(train_dates)<250: continue
        model=fit_model(dataset.loc[train_dates,columns],dataset.loc[train_dates,"target"])
        block=dataset.iloc[i:end]
        preds.extend(model.predict_proba(block[columns])[:,1]); actual.extend(block.target.astype(int)); timestamps.extend(block.index)
    if len(preds)<100: raise ValueError("Nedostatek mimovzorkových predikcí.")
    p=np.asarray(preds); truth=np.asarray(actual)
    # Calibration only on past out-of-sample predictions, with a time embargo.
    dates = pd.DatetimeIndex(timestamps)
    split = int(len(p) * .65)
    cal_mask = label_end.loc[dates].to_numpy() < dates[split]
    calibration = LogisticRegression(C=1, random_state=42)
    def odds(prob):
        clipped = np.clip(prob, 1e-5, 1 - 1e-5)
        return np.log(clipped / (1 - clipped)).reshape(-1, 1)
    calibration.fit(odds(p[cal_mask]), truth[cal_mask])
    # Select non-overlapping forecast windows for scoring.
    selected = []
    previous_end = pd.Timestamp.min
    for i in range(split, len(dates)):
        if dates[i] > previous_end:
            selected.append(i)
            previous_end = label_end.at[dates[i]]
    test_dates = dates[selected]
    test_truth = truth[selected]
    p_test = calibration.predict_proba(odds(p[selected]))[:, 1]
    baseline = np.full(len(selected), truth[cal_mask].mean())
    metrics = {
        "brier": brier_score_loss(test_truth, p_test),
        "accuracy": accuracy_score(test_truth, p_test >= .5),
        "log_loss": log_loss(test_truth, p_test, labels=[0, 1]),
        "baseline_brier": brier_score_loss(test_truth, baseline),
        "fair_coin_brier": .25,
        "test_count": len(selected), "test_start": str(test_dates[0].date()),
        "test_end": str(test_dates[-1].date()),
    }
    metrics["weak"] = len(selected) < 50 or metrics["brier"] > min(.25, metrics["baseline_brier"]) - .005
    # Current inference: only fully matured labels are used.
    last_date=X.index[-1]
    train_idx=dataset.index[label_end.reindex(dataset.index).to_numpy() <= last_date]
    latest_model=fit_model(dataset.loc[train_idx,columns],dataset.loc[train_idx,"target"])
    raw=latest_model.predict_proba(X.loc[[last_date],columns])[:,1]
    prob=float(calibration.predict_proba(odds(raw))[0,1])
    test=pd.DataFrame({"date":test_dates,"actual":test_truth,"probability":p_test})
    test["bucket"]=pd.cut(test.probability,bins=np.linspace(0,1,6),include_lowest=True)
    reliability=test.groupby("bucket",observed=False).agg(predicted=("probability","mean"),observed=("actual","mean"),count=("actual","size")).dropna().reset_index(drop=True)
    return {"probability":prob,"metrics":metrics,"test":test,"reliability":reliability,"last_date":last_date,"last_close":float(df.loc[last_date,"Close"]),"history":df,"indicators": X.loc[last_date, FEATURES]}
