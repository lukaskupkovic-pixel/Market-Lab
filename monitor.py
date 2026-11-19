"""Production-only evaluation of immutable, matured published predictions."""
import numpy as np
import pandas as pd


def degradation_report(history, symbol, version, minimum=20):
    """Only non-overlapping 7d outcomes of the *same* model version count.

    A warning is based on live paper forecasts, never the already used
    historical train/validation/test sample. Missing history means unknown,
    not a passing result.
    """
    observations = []
    for key, record in history.items():
        if record.get("symbol") != symbol or not str(key).endswith("/" + version):
            continue
        if record.get("outcome") not in ("up", "flat_or_down"):
            continue
        try:
            start, end = pd.Timestamp(record["date"]), pd.Timestamp(record["outcome_date"])
            p = float(record["up"])
        except (ValueError, TypeError, KeyError):
            continue
        if not (0 <= p <= 1) or (end - start).days < 7 or (end - start).days > 10:
            continue
        observations.append((start, end, p, int(record["outcome"] == "up")))
    observations.sort(key=lambda value: value[0])
    independent = []
    last_end = pd.Timestamp.min
    for item in observations:
        if item[0] > last_end:
            independent.append(item)
            last_end = item[1]
    if len(independent) < minimum:
        return {"status": "insufficient", "count": len(independent), "minimum": minimum}
    recent = independent[-minimum:]
    recent_brier = float(np.mean([(p - y) ** 2 for _, _, p, y in recent]))
    # Compare with a fixed 50:50 reference as well as the prior independent
    # published window if one exists. Thresholds are predeclared, not tuned
    # to observed forecasts. This is an alarm, not a significance proof.
    previous = independent[-2 * minimum:-minimum] if len(independent) >= 2 * minimum else []
    previous_brier = float(np.mean([(p - y) ** 2 for _, _, p, y in previous])) if previous else None
    degraded = recent_brier > .27 and (previous_brier is None or recent_brier > previous_brier + .025)
    return {"status": "degraded" if degraded else "watch", "count": len(independent),
            "window": minimum, "recent_brier": round(recent_brier, 4),
            "previous_brier": round(previous_brier, 4) if previous_brier is not None else None,
            "reference_brier": .25, "blocks_signal": degraded}

