# reconciler.py
from typing import Dict, Any
import copy

MAX_AUTO_ADJUST = 10.00  # money threshold for safe auto-attribution (configurable)

def reconcile(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input: parser candidate output (income dict, expense dict, declared totals, cash_in_hand)
    Output: corrected record with deterministic totals and reconciliation metadata.
    Rules:
      - Declared totals (if present) take precedence.
      - ZIMRA shared is annotation only (do not change totals).
      - If declared_total_income exists and sum(income) differs by <= MAX_AUTO_ADJUST:
          add an 'Adjustment' income entry to force-match and mark 'auto_adjusted'
      - If declared_total_expenses exists: use it for final total_expenses (but keep itemized sums as metadata)
    """
    out = copy.deepcopy(parsed)

    income = out.get('income', {}) or {}
    expenses = out.get('expenses', {}) or {}
    declared_inc = out.get('declared_total_income')
    declared_exp = out.get('declared_total_expenses')
    cash_recorded = out.get('cash_in_hand')

    sum_income = round(sum(income.values()), 2)
    itemized_exp_sum = round(sum(v for k, v in expenses.items() if not k.startswith('Zimra (Shared)')), 2)

    # Respect declared totals
    if declared_inc is not None:
        declared_inc = round(float(declared_inc), 2)
        diff = round(declared_inc - sum_income, 2)
        if abs(diff) <= MAX_AUTO_ADJUST and diff != 0:
            # safe auto-attribute
            income['Adjustment'] = round(diff, 2)
            sum_income = declared_inc
            out['auto_adjusted_income'] = True
        else:
            out['auto_adjusted_income'] = False

    if declared_exp is not None:
        total_expenses = round(float(declared_exp), 2)
        out['expenses_itemized_sum'] = itemized_exp_sum
        out['expenses_mismatch'] = round(itemized_exp_sum - total_expenses, 2)
    else:
        total_expenses = itemized_exp_sum
        out['expenses_itemized_sum'] = itemized_exp_sum
        out['expenses_mismatch'] = 0.0

    total_income = round(sum_income, 2)
    total_expenses = round(total_expenses, 2)

    # Final cash: prefer recorded cash if present (constitution demands cash is factual)
    final_cash = cash_recorded if cash_recorded is not None else round(total_income - total_expenses, 2)

    out.update({
        'income': income,
        'total_income': total_income,
        'expenses': expenses,
        'total_expenses': total_expenses,
        'cash_in_hand': round(final_cash, 2),
        'reconciled': True
    })

    return out
