"""
calculations.py
---------------
Financial calculations: who-owes-whom, settlement, anomaly detection.
"""

from __future__ import annotations


def settlement(totals: dict, members: list[str]) -> list[dict]:
    """
    Compute the minimum transactions to settle debts.

    Returns a list of  {payer, receiver, amount}  dicts.
    Algorithm: greedy creditor/debtor matching.
    """
    overall = totals.get("overall", 0)
    n = len(members)
    if n == 0:
        return []

    fair_share = overall / n
    balance = {m: totals.get(m, 0) - fair_share for m in members}

    creditors = sorted(
        [(m, b) for m, b in balance.items() if b > 0], key=lambda x: -x[1]
    )
    debtors = sorted(
        [(m, -b) for m, b in balance.items() if b < 0], key=lambda x: -x[1]
    )

    transactions = []
    ci = di = 0
    while ci < len(creditors) and di < len(debtors):
        cname, camt = creditors[ci]
        dname, damt = debtors[di]
        transfer = min(camt, damt)
        transactions.append(
            {"payer": dname, "receiver": cname, "amount": round(transfer, 2)}
        )
        creditors[ci] = (cname, camt - transfer)
        debtors[di] = (dname, damt - transfer)
        if creditors[ci][1] < 0.01:
            ci += 1
        if debtors[di][1] < 0.01:
            di += 1

    return transactions


def build_summary_text(totals: dict, members: list[str], updated_by: str, added_amount: float) -> str:
    """Return a plain-text summary for email / display."""
    lines = [
        f"Updated by: {updated_by}  (added ₹{added_amount:,.0f})",
        "",
    ]
    for m in members:
        lines.append(f"  {m} total: ₹{totals.get(m, 0):,.0f}")
    lines += ["", f"  Overall total: ₹{totals.get('overall', 0):,.0f}"]
    return "\n".join(lines)


def detect_anomaly(totals: dict, members: list[str]) -> list[str]:
    """
    Very simple anomaly: flag any member whose spend is > 2× the average
    of others.
    Returns list of flagged member names.
    """
    if len(members) < 2:
        return []
    flagged = []
    for m in members:
        others = [totals.get(o, 0) for o in members if o != m]
        avg_others = sum(others) / len(others) if others else 0
        if avg_others > 0 and totals.get(m, 0) > 2 * avg_others:
            flagged.append(m)
    return flagged


def predict_next_month(monthly_series: list[float]) -> float | None:
    """
    Predict next month's total from a list of monthly totals using
    simple linear regression (sklearn).  Returns None if < 2 data points.
    """
    if len(monthly_series) < 2:
        return None
    try:
        from sklearn.linear_model import LinearRegression
        import numpy as np

        X = np.array(range(len(monthly_series))).reshape(-1, 1)
        y = np.array(monthly_series)
        model = LinearRegression().fit(X, y)
        next_x = np.array([[len(monthly_series)]])
        pred = float(model.predict(next_x)[0])
        return max(0.0, round(pred, 2))
    except Exception:
        return None
