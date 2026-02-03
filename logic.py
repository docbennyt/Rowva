# logic.py
import json
from datetime import datetime
from typing import Dict, List
from config import DEFAULT_CURRENCY

def validate_and_summarize(parsed: Dict) -> Dict:
    """Backward-compatible validation for the UI. Returns same shape as before."""
    # Keep existing behavior but route formatting to format_summary
    structured = format_summary(parsed)
    # Compute numeric values for compatibility
    calc_income = round(parsed.get('total_income', 0.0), 2)
    calc_expenses = round(parsed.get('total_expenses', 0.0), 2)
    expected_cash = round(calc_income - calc_expenses, 2)
    actual_cash = round(parsed.get('cash_in_hand') or 0.0, 2)
    variance = round(actual_cash - expected_cash, 2)

    has_issue = abs(variance) >= 1.0 or (
        parsed.get('declared_total_income') is not None and
        abs(parsed['declared_total_income'] - calc_income) >= 1.0
    )

    return {
        'structured_text': structured,
        'variance': variance,
        'expected_cash': expected_cash,
        'has_issue': has_issue
    }


# New strict formatter
def format_summary(parsed: Dict) -> str:
    """Produce the strict template per UEEU spec (human-friendly, single canonical output).

    Returns a single string (multi-line) with sections:
      - Date
      - OPERATIONAL STATS (Tables, Arrests)
      - INCOME (list, totals)
      - EXPENSES (list, totals; show ZIMRA split calculation when present)
      - Expected cash and (if variance >= $1) a WARNING
    """
    inc = parsed.get('income', {})
    exp = parsed.get('expenses', {})
    tables = parsed.get('tables_count') or 0
    arrests = parsed.get('arrests_count') or 0

    def fmt_amt(v: float) -> str:
        if float(v).is_integer():
            return f"{DEFAULT_CURRENCY} {int(round(v))}"
        return f"{DEFAULT_CURRENCY} {v:.2f}"

    # Date: convert ISO to 'Weekday D Mon YYYY'
    date_iso = parsed.get('date')
    try:
        from datetime import datetime
        dt = datetime.strptime(date_iso, "%Y-%m-%d")
        date_line = dt.strftime("%A %d %b %Y")
    except Exception:
        date_line = date_iso or ''

    lines = []
    lines.append(date_line)
    lines.append("")
    lines.append("OPERATIONAL STATS")
    lines.append(f"- Tables Served: {tables}")
    lines.append(f"- Arrests: {arrests}")
    lines.append("")
    lines.append("INCOME")

    # Income items: deterministic order (Table Payment first if present)
    if inc:
        # sort by name for determinism; prefer 'Table Payment', 'Arrest Cash'
        preferred = ['Table Payment', 'Table payment', 'Arrest Cash', 'Arrests']
        ordered = sorted(inc.items(), key=lambda kv: (0 if kv[0] in preferred else 1, kv[0].lower()))
        for label, amt in ordered:
            # Normalize 'Arrest' label to 'Arrest Cash' if needed
            lab = 'Arrest Cash' if 'arrest' in label.lower() and 'arrest cash' not in label.lower() else label
            lines.append(f"- {lab}: {fmt_amt(amt)}")
    else:
        lines.append("(none)")

    lines.append(f"-> Total Income: {fmt_amt(parsed.get('total_income', 0.0))}")
    lines.append("")
    lines.append("EXPENSES")

    if exp:
        # Show Zimra breakdown if present
        zimra_net = exp.get('Zimra (Net)') or exp.get('Zimra (Net)'.title())
        zimra_shared = exp.get('Zimra (Shared)')
        for label, amt in exp.items():
            # Skip showing shared separately until after list
            if label == 'Zimra (Shared)':
                continue
            lines.append(f"- {label}: {fmt_amt(amt)}")
        if zimra_shared:
            lines.append(f"-> ZIMRA: {fmt_amt(zimra_net + zimra_shared)} -> Shared: {fmt_amt(zimra_shared)} -> Net: {fmt_amt(zimra_net)}")
    else:
        lines.append("(none)")

    # Use declared total if present; if itemized sum differs, show a clear note so user can reconcile
    if parsed.get('declared_total_expenses') is not None and parsed.get('expenses_itemized_sum') is not None:
        item_sum = parsed['expenses_itemized_sum']
        declared_total = parsed['declared_total_expenses']
        if abs(item_sum - declared_total) >= 0.5:
            lines.append(f"NOTE: itemized expenses sum {fmt_amt(item_sum)} but 'Less expenses' is {fmt_amt(declared_total)}; please reconcile.")

    lines.append(f"-> Total Expenses: {fmt_amt(parsed.get('total_expenses', 0.0))}")
    lines.append("")

    expected_cash = round(parsed.get('total_income', 0.0) - parsed.get('total_expenses', 0.0), 2)
    lines.append(f"Expected cash: {fmt_amt(expected_cash)}")

    # Variance: flag only when |diff| >= 1.0
    actual = parsed.get('cash_in_hand') or 0.0
    diff = round(actual - expected_cash, 2)
    if abs(diff) >= 1.0:
        sign = '+' if diff > 0 else ''
        lines.append(f"WARNING: You recorded {fmt_amt(actual)} - check {sign}{fmt_amt(diff)} variance")

    return "\n".join(lines)
