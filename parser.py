# parser.py
import re
import json
from typing import Dict, Any
from rules import (
    extract_date_from_text, is_stat_line, is_income_line, is_expense_line,
    handle_zimra_expense, clean_label, INCOME_INDICATORS, EXPENSE_INDICATORS
)

def extract_amount(line: str) -> float:
    """Extract last numeric value (handles 'ㅡ.1400', '27', etc.)"""
    # Remove non-numeric except . and -
    nums = re.findall(r'[\d,]+\.?\d*', line)
    if nums:
        try:
            return float(nums[-1].replace(',', ''))
        except:
            pass
    return 0.0

def parse_whatsapp_day(raw_text: str) -> Dict[str, Any]:
    """Parse a WhatsApp-style daily note into a structured dict.

    Returns a dict with keys:
      date (ISO str), tables_count, arrests_count, income (dict), expenses (dict),
      total_income, total_expenses, shared_expense, declared_total_income,
      declared_total_expenses, cash_in_hand, raw_text, errors (list)

    Rules implemented:
      - Date extraction using configured regex
      - Numeric extraction: use the last numeric token in a logical segment; handle 'ㅡ.1400' and '11-12. ㅡ.1400'
      - Distinguish stats (Tables/Arrests) vs income (second Arrest / Arrest with amount)
      - ZIMRA split rule applied when 'zimra' appears in expenses
    """

    errors = []
    # Normalize whitespace and unify dot delimiters for easier splitting
    parts = re.split(r"[\n\r]+|\s*\.\s*|;|\s*-\s*", raw_text)
    segments = []

    # Pair regex: 'label ... number' or 'number label ...'
    pair_re = re.compile(r"(\d+(?:[.,]\d+)?\s*[A-Za-z][^\d\n]*)|([A-Za-z][^\d\n]*?\d+(?:[.,]\d+)?)")

    for part in parts:
        part = part.strip()
        if not part:
            continue
        found = False
        for m in pair_re.finditer(part):
            seg = m.group(0).strip()
            # Canonicalize '291 Arrests' -> 'Arrests 291'
            m2 = re.match(r'^(?P<num>\d+(?:[.,]\d+)?)\s*(?P<label>.+)$', seg)
            if m2 and not re.search(r'[A-Za-z]', m2.group('label')):
                seg_std = seg
            elif m2:
                seg_std = f"{m2.group('label').strip()} {m2.group('num')}"
            else:
                seg_std = seg
            segments.append(seg_std)
            found = True
        if not found:
            segments.append(part)

    if not segments:
        errors.append(f"Line '{raw_text}' could not be parsed")
        return {'raw_text': raw_text, 'errors': errors}

    # Extract date (from raw text) and remove it from work string to avoid misattribution
    date_iso = extract_date_from_text(raw_text)

    work_text = raw_text

    # Capture declared totals and cash early from the original raw message (robust when the exporter splits tokens)
    declared_total_income = None
    declared_total_expenses = None
    m = re.search(r"(?:total\s*amnt|total\s*amount)\D*(\d+(?:[.,]\d+)?)", raw_text, flags=re.I)
    if m:
        declared_total_income = float(m.group(1).replace(',', ''))

    m = re.search(r"less\s*expenses\D*(\d+(?:[.,]\d+)?)", raw_text, flags=re.I)
    if m:
        declared_total_expenses = float(m.group(1).replace(',', ''))

    m = re.search(r"cash\s*in\s*hand\D*(\d+(?:[.,]\d+)?)", raw_text, flags=re.I)
    if m:
        cash_in_hand = float(m.group(1).replace(',', ''))
    else:
        cash_in_hand = None

    # Remove declared total lines from work_text before targeted captures (to avoid false matches)
    work_text = re.sub(r"(?:total\s*amnt|total\s*amount)[^\n]*", "", work_text, flags=re.I)
    work_text = re.sub(r"less\s*expenses[^\n]*", "", work_text, flags=re.I)
    work_text = re.sub(r"cash\s*in\s*hand[^\n]*", "", work_text, flags=re.I)

    # Remove the date substring so it doesn't pollute label extraction
    date_match = re.search(r'(?:[A-Za-z]+\.?\s+)(\d{1,2})([A-Za-z]{3,})\s*(\d{2,4})', work_text)
    if date_match:
        work_text = work_text[:date_match.start()] + work_text[date_match.end():]

    # Targeted captures (stats) - run early and remove these spans to avoid later misclassification
    stats = {}
    m = re.search(r"\btables?\b[^\d\n]{0,40}(\d+)", work_text, flags=re.I)
    if m:
        stats['Tables'] = int(m.group(1))
        work_text = work_text[:m.start()] + work_text[m.end():]

    # Arrests may appear twice: first instance is a stat count; a later 'Arrest. [amount]' is income
    m = re.search(r"\barrests?\b[^\d\n]{0,40}(\d+)", work_text, flags=re.I)
    if m:
        stats['Arrests'] = int(m.group(1))
        work_text = work_text[:m.start()] + work_text[m.end():]

    # Helper: last-number extraction for a candidate token
    def last_number(s: str) -> float:
        # handle special ㅡ.1400 tokens and plain numbers
        m = re.findall(r"\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?|\d+", s)
        if m:
            return float(m[-1].replace(',', ''))
        # special cases like 'ㅡ.1400' — look for 3+ digits following a non-digit marker
        m2 = re.search(r'\d{3,}\b', s)
        if m2:
            return float(m2.group(0))
        return 0.0


    # Targeted income captures (keywords)
    income = {}
    consumed_income = set()
    for kw in INCOME_INDICATORS:
        # Pattern: capture label (up to 40 chars before + keyword + up to 1 word after), then digits
        # This prevents "schoolboy" from matching both "schoolboy transport" AND "schoolboy salaries" at once
        pat = re.compile(rf"([A-Za-z ]{{0,40}}{re.escape(kw)}(?:\s+[A-Za-z]+)?)[^\d\n]{{0,40}}(\d+(?:[.,]\d+)?)", flags=re.I)
        matches = list(pat.finditer(work_text))
        spans_to_remove = []
        for m in matches:
            label = clean_label(m.group(1))
            # Strip leading 'Expenses' if present (common in exports)
            label = re.sub(r'^(?:Expenses?\s*)', '', label, flags=re.I).strip().title()
            amt = float(m.group(2).replace(',', ''))
            key = (label.lower(), round(float(amt), 2))
            if key in consumed_income:
                # skip duplicate
                continue
            income[label] = income.get(label, 0.0) + amt
            consumed_income.add(key)
            spans_to_remove.append((m.start(), m.end()))
        # remove all matched slices safely in reverse order to avoid index shifts
        for s, e in reversed(spans_to_remove):
            work_text = work_text[:s] + work_text[e:]
    # Targeted expense captures (keywords) — deterministic order (prefer longer phrases to avoid overlapping matches)
    expenses = {}
    consumed_expenses = set()
    for kw in sorted(EXPENSE_INDICATORS, key=lambda s: -len(s)):
        # Pattern: capture label (up to 40 chars before + keyword + up to 1 word after), then digits
        # This allows "Schoolboy Salaries" to be matched intact, preventing "schoolboy" alone from consuming it
        pat = re.compile(rf"([A-Za-z ]{{0,40}}{re.escape(kw)}(?:\s+[A-Za-z]+)?)[^\d\n]{{0,40}}(\d+(?:[.,]\d+)?)", flags=re.I)
        matches = list(pat.finditer(work_text))
        spans_to_remove = []
        for m in matches:
            label = clean_label(m.group(1))
            label = re.sub(r'^(?:Expenses?\s*)', '', label, flags=re.I).strip().title()
            amt = float(m.group(2).replace(',', ''))
            key = (label.lower(), round(float(amt), 2))
            if key in consumed_expenses:
                spans_to_remove.append((m.start(), m.end()))
                continue
            # Apply ZIMRA rule immediately; do NOT keep original 'Zimra' label to avoid double-counting
            if 'zimra' in label.lower():
                shared = round(amt / 2, 2)
                expenses['Zimra (Net)'] = expenses.get('Zimra (Net)', 0.0) + (amt - shared)
                expenses['Zimra (Shared)'] = expenses.get('Zimra (Shared)', 0.0) + shared
                consumed_expenses.add(( 'zimra (net)', round(float(amt - shared),2) ))
                consumed_expenses.add(( 'zimra (shared)', round(float(shared),2) ))
                consumed_expenses.add(key)
            else:
                expenses[label] = expenses.get(label, 0.0) + amt
                consumed_expenses.add(key)
            spans_to_remove.append((m.start(), m.end()))
        for s, e in reversed(spans_to_remove):
            work_text = work_text[:s] + work_text[e:]

    # Capture named expenses like 'Joseline 6' but avoid weekdays/months
    for m in re.finditer(r"\b([A-Z][a-z]{2,20})\.?\s*(\d+(?:[.,]\d+)?)", work_text):
        name = m.group(1)
        lower_name = name.lower()
        if lower_name in {'sunday','monday','tuesday','wednesday','thursday','friday','saturday',
                          'arrest','arrests','table','tables','total','less','cash','amount','amnt'}:
            continue
        amt = float(m.group(2).replace(',', ''))
        expenses[name] = expenses.get(name, 0.0) + amt
        work_text = work_text[:m.start()] + work_text[m.end():]

    # Fall back to segment-based extraction on remaining text
    parts = re.split(r"[\n\r]+|\s*\.\s*|;|\s*-\s*", work_text)
    pair_re = re.compile(r"(\d+(?:[.,]\d+)?\s*[A-Za-z][^\d\n]*)|([A-Za-z][^\d\n]*?\d+(?:[.,]\d+)?)")

    more_income = {}
    more_expenses = {}

    recent_income = False

    for part in parts:
        part = part.strip()
        if not part:
            continue
        matches = [m.group(0).strip() for m in pair_re.finditer(part)]
        for i, seg in enumerate(matches):
            m2 = re.match(r'^(?P<num>\d+(?:[.,]\d+)?)\s*(?P<label>.+)$', seg)
            if m2 and re.search(r'[A-Za-z]', m2.group('label')):
                seg_std = f"{m2.group('label').strip()} {m2.group('num')}"
            else:
                seg_std = seg

            amt = last_number(seg_std)
            lower = seg_std.lower()

            # skip month/day artifacts
            if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", lower):
                continue

            # Stats (Tables/Arrests) — prefer first matches captured earlier but accept if seen here
            if is_stat_line(lower) and ('table' in lower or 'arrest' in lower):
                if 'Tables' not in stats and 'table' in lower:
                    stats['Tables'] = int(amt)
                    continue
                if 'Arrests' not in stats and 'arrest' in lower:
                    stats['Arrests'] = int(amt)
                    continue

            # Shop payment shorthand like '11-12. ㅡ.1400' -> treat 1400 as one income, ignore '11-12'
            if re.search(r'\d{1,2}-\d{1,2}.*?\d', seg):
                # prefer long numbers as income
                if amt >= 100:
                    more_income['Unlabeled Income'] = more_income.get('Unlabeled Income', 0.0) + amt
                    recent_income = True
                    continue

            # Arrest heuristics: treat 'arrest' with amount > 0 as income only if it's a second arrest or near an income
            if 'arrest' in lower:
                # If the amount is small (<=10) and we either recently saw an income or there was a separate Arrest stat, treat as Arrest Cash
                if amt > 0 and (recent_income or ('Arrests' in stats and int(stats['Arrests']) >= 0 and amt <= 10)):
                    label = 'Arrest Cash'
                    more_income[label] = more_income.get(label, 0.0) + amt
                    recent_income = True
                    continue
                # otherwise skip as it is likely a stat

            # Generic income detection: large unlabeled numbers (>=100) not caught above
            if amt >= 100 and not is_expense_line(lower):
                # avoid mislabeling stats
                label = 'Other Income'
                more_income[label] = more_income.get(label, 0.0) + amt
                recent_income = True
                continue

            # Expense line detection
            if is_expense_line(lower):
                label = clean_label(seg_std)
                label = re.sub(r'^(?:Expenses?\s*)', '', label, flags=re.I).strip().title()
                more_expenses[label] = more_expenses.get(label, 0.0) + amt
                recent_income = False
                continue

            # none matched: continue

    # After targeted captures, fall back to segment-based extraction on remaining text
    parts = re.split(r"[\n\r]+|\s*\.\s*|;|\s*-\s*", work_text)
    # Build segments of label+number in reading order
    pair_re = re.compile(r"(\d+(?:[.,]\d+)?\s*[A-Za-z][^\d\n]*)|([A-Za-z][^\d\n]*?\d+(?:[.,]\d+)?)")

    more_income = {}
    more_expenses = {}

    recent_income = False
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Collect matches so we can look ahead
        matches = [m.group(0).strip() for m in pair_re.finditer(part)]
        for i, seg in enumerate(matches):
            # Normalize 'num label' -> 'label num'
            m2 = re.match(r'^(?P<num>\d+(?:[.,]\d+)?)\s*(?P<label>.+)$', seg)
            if m2 and re.search(r'[A-Za-z]', m2.group('label')):
                seg_std = f"{m2.group('label').strip()} {m2.group('num')}"
            else:
                seg_std = seg

            amt = extract_amount(seg_std)
            lower = seg_std.lower()

            # skip month/day artifacts
            if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", lower):
                continue

            # Stats (prefer first matches; any later 'arrest' may be an income)
            if is_stat_line(lower) and ('table' in lower or 'arrest' in lower):
                if 'Tables' not in stats and 'table' in lower:
                    stats['Tables'] = int(amt)
                    continue
                if 'Arrests' not in stats and 'arrest' in lower:
                    stats['Arrests'] = int(amt)
                    continue
                # Otherwise fall through and let later logic classify (could be income)

            # Special arrest cash or 'plus arrest cash' treated as income
            if 'plus arrest cash' in lower or 'arrest cash' in lower:
                more_income['Arrest Cash'] = more_income.get('Arrest Cash', 0.0) + amt
                recent_income = True
                continue

            # Heuristic: if recent_income True and this target is 'arrest', treat as income
            # Also, if the previous match was an income and this seg is 'arrest' with a small number, treat as income
            next_is_arrest = False
            if i + 1 < len(matches):
                look = matches[i+1]
                if re.search(r"\barrest\b", look, flags=re.I) and extract_amount(look) > 0:
                    next_is_arrest = True

            if 'arrest' in lower and (recent_income or next_is_arrest):
                label = clean_label(seg_std)
                label = re.sub(r'^(?:Expenses?\s*)', '', label, flags=re.I).strip().title()
                more_income[label] = more_income.get(label, 0.0) + amt
                recent_income = True
                continue

            if is_income_line(lower, amt):
                label = clean_label(seg_std)
                label = re.sub(r'^(?:Expenses?\s*)', '', label, flags=re.I).strip().title()
                more_income[label] = more_income.get(label, 0.0) + amt
                recent_income = True
                # Look ahead: if next seg is an 'Arrest' with a small numeric value, include it as income
                if i + 1 < len(matches):
                    nxt = matches[i+1]
                    if re.search(r"^\s*arrest\b", nxt, flags=re.I) and extract_amount(nxt) > 0:
                        # normalize next to label and include
                        nxt_std = re.sub(r'^(?P<label>[^\d]+)\s*(?P<num>\d+)', r"\1 \2", nxt).strip()
                        nxt_amt = extract_amount(nxt_std)
                        nxt_label = re.sub(r'^(?:Expenses?\s*)', '', clean_label(nxt_std), flags=re.I).strip().title()
                        more_income[nxt_label] = more_income.get(nxt_label, 0.0) + nxt_amt
                        # Skip next by advancing index (we can't mutate for-loop index; we'll mark it by setting matches[i+1] to '')
                        matches[i+1] = ''
                continue

            if is_expense_line(lower):
                label = clean_label(seg_std)
                label = re.sub(r'^(?:Expenses?\s*)', '', label, flags=re.I).strip().title()
                more_expenses[label] = more_expenses.get(label, 0.0) + amt
                recent_income = False
                continue

            # If none matched, continue without changing recent_income


    # Merge targeted and discovered items
    for k, v in more_income.items():
        income[k] = income.get(k, 0.0) + v
    for k, v in more_expenses.items():
        expenses[k] = expenses.get(k, 0.0) + v

    # Post-pass: identify short 'Arrest X' items that appear adjacent to income segments in the original text
    # Be conservative: avoid converting large plural 'Arrests' counts (stats) into income entries.
    ARREST_INCOME_MAX = 10  # reasonable small amount threshold to treat as income
    for idx, seg in enumerate(segments):
        if 'arrest' in seg.lower():
            amt = extract_amount(seg)
            if amt <= 0:
                continue
            # If an 'Arrest' is already in income, skip
            if any('arrest' in k.lower() for k in income.keys()):
                continue
            seg_lower = seg.lower()
            # If this exactly matches the recorded arrests stat, skip (it's a stat)
            if 'Arrests' in stats and int(amt) == int(stats.get('Arrests', 0)) and 'arrests' in seg_lower:
                continue
            # If this is a large plural count, skip (likely a stat, not income)
            if amt > ARREST_INCOME_MAX and 'arrests' in seg_lower:
                continue

            # Look around (previous and next) for income hints
            prev = segments[idx - 1] if idx > 0 else ''
            next_seg = segments[idx + 1] if idx + 1 < len(segments) else ''
            prev_lower = prev.lower()
            next_lower = next_seg.lower()

            income_hint = (
                any(kw in prev_lower for kw in INCOME_INDICATORS) or
                any(priv_key.lower() in prev_lower for priv_key in income.keys()) or
                'payment' in prev_lower or 'paid' in prev_lower or
                any(kw in next_lower for kw in INCOME_INDICATORS) or
                any(priv_key.lower() in next_lower for priv_key in income.keys()) or
                'payment' in next_lower or 'paid' in next_lower
            )

            # Only convert to income when the arrest amount is small and we have an income nearby
            if amt <= ARREST_INCOME_MAX and income_hint:
                label = clean_label(seg)
                label = re.sub(r'^(?:Expenses?\s*)', '', label, flags=re.I).strip().title()
                income[label] = income.get(label, 0.0) + amt

    # If we have a declared total income and we're short by a small amount, attribute to Arrest as income
    if declared_total_income is not None:
        missing = declared_total_income - sum(income.values())
        if 0 < missing <= 10 and any('arrest' in s.lower() for s in segments) and not any('arrest' in k.lower() for k in income.keys()):
            income['Arrest'] = income.get('Arrest', 0.0) + missing

    # Apply ZIMRA consolidation for output: shared already stored in expenses with keys if present
    shared_expense = round(expenses.get('Zimra (Shared)', 0.0), 2)
    # Itemized expenses sum (before trusting declared value)
    itemized_expenses_sum = round(sum(v for k, v in expenses.items() if not k.startswith('Zimra (Shared)')), 2)

    # If declared_total_expenses was provided, prefer it for reported totals but record mismatch for transparency
    if declared_total_expenses is not None:
        total_expenses = round(declared_total_expenses, 2)
        expenses_mismatch = round(itemized_expenses_sum - total_expenses, 2)
    else:
        total_expenses = itemized_expenses_sum
        expenses_mismatch = 0.0

    # Totals
    total_income = round(sum(income.values()), 2)

    # Final cash: use recorded if available, else compute
    final_cash = cash_in_hand if cash_in_hand is not None else (total_income - total_expenses)

    return {
        'date': date_iso,
        'raw_text': raw_text,
        'tables_count': stats.get('Tables'),
        'arrests_count': stats.get('Arrests'),
        'income': income,
        'income_json': json.dumps(income),
        'total_income': round(total_income, 2),
        'expenses': expenses,
        'expenses_json': json.dumps(expenses),
        'total_expenses': round(total_expenses, 2),
        'shared_expense': round(shared_expense, 2),
        'declared_total_income': declared_total_income,
        'declared_total_expenses': declared_total_expenses,
        'cash_in_hand': round(final_cash, 2),
        'errors': errors,
        'expenses_itemized_sum': itemized_expenses_sum,
        'expenses_mismatch': expenses_mismatch
    }