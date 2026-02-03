# rules.py
import re
from typing import Dict, List, Tuple

# Keywords (case-insensitive)
INCOME_INDICATORS = {
    'table payment', 'shop payment', 'arrest cash', 'plus arrest cash',
    '11-12', '25', 'payment'
}

EXPENSE_INDICATORS = {
    'transport', 'joseline', 'salaries', 'zimra', 'license', 'data',
    'books', 'overtime', 'schoolboy', 'counter', 'sagas', 'police'
}

STATS_INDICATORS = {'tables', 'arrests'}

def is_income_line(line_lower: str, amount: float) -> bool:
    if any(kw in line_lower for kw in INCOME_INDICATORS):
        return True
    # Heuristic: large standalone numbers likely income
    if amount >= 100 and not any(kw in line_lower for kw in EXPENSE_INDICATORS | STATS_INDICATORS):
        return True
    return False

def is_expense_line(line_lower: str) -> bool:
    return any(kw in line_lower for kw in EXPENSE_INDICATORS)

def is_stat_line(line_lower: str) -> bool:
    return any(kw in line_lower for kw in STATS_INDICATORS)

def extract_date_from_text(raw_text: str) -> str:
    """Extract date like 'Sunday. 4Jan 25' → '2025-01-04'"""
    # Match patterns: "Sunday. 4Jan 25", "Mon 29Dec 25", "Sat. 3Jan 26"
    pattern = r'(?:[A-Za-z]+\.?\s+)(\d{1,2})([A-Za-z]{3,})(?:\s+)?(\d{2,4})'
    match = re.search(pattern, raw_text)
    if not match:
        raise ValueError("Date not found in message")
    
    day = int(match.group(1))
    month_str = match.group(2).lower()
    year_short = match.group(3)
    
    # Month mapping
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    month = months.get(month_str[:3])
    if not month:
        raise ValueError(f"Invalid month: {month_str}")
    
    # Handle 2-digit year (assume 20xx)
    year = int(year_short)
    if year < 100:
        year += 2000
    
    try:
        dt = f"{year}-{month:02d}-{day:02d}"
        # Validate
        from datetime import datetime
        datetime.strptime(dt, "%Y-%m-%d")
        return dt
    except ValueError:
        raise ValueError(f"Invalid date: {day}/{month}/{year}")

def handle_zimra_expense(expenses: Dict[str, float]) -> Tuple[Dict[str, float], float]:
    """If ZIMRA exists, compute shared expense (ZIMRA/2) and reduce net expense"""
    shared = 0.0
    zimra_val = None
    
    # Find ZIMRA (case-insensitive)
    zimra_key = None
    for k in expenses:
        if 'zimra' in k.lower():
            zimra_key = k
            zimra_val = expenses[k]
            break
    
    if zimra_val is not None:
        shared = round(zimra_val / 2, 2)
        # Reduce total expense by shared amount
        expenses = expenses.copy()
        expenses[zimra_key] = round(zimra_val - shared, 2)
    
    return expenses, shared

def clean_label(label: str) -> str:
    """Remove amounts, dots, extra spaces"""
    label = re.sub(r'[\d,$.\-–—_]+', ' ', label)
    return re.sub(r'\s+', ' ', label).strip(': ')