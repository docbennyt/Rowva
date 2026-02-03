from parser import parse_whatsapp_day
from logic import format_summary


def test_format_simple_arrest():
    raw = (
        "Sunday. 4Jan 25 Table. 291 Arrests. 1 Table payment. 2037 Arrest. 1 "
        "Expenses schoolboy transport 26 Joseline. 6 Total amnt 2038 Less expenses. 32 Cash in hand. 2006"
    )
    parsed = parse_whatsapp_day(raw)
    out = format_summary(parsed)
    # Date may be weekday-corrected; check day and month
    assert '4 Jan 2025' in out or '04 Jan 2025' in out
    assert 'Tables Served: 291' in out
    assert 'Arrests: 1' in out
    assert 'Table Payment' in out
    assert 'Arrest Cash' in out
    assert '-> Total Income: $ 2038' in out
    assert '-> Total Expenses: $ 32' in out
    assert 'Expected cash: $ 2006' in out


def test_format_zimra():
    raw = (
        "Monday. 29Dec 25\nTables. 401\nArrests. 10\nTable payment. 2807\nArrests. 10\n"
        "Expenses. Schoolboy transport. 26\nJoseline. 6\nJoseline overtime.sunday. 24\nSchoolboy salaries. 800\nZimra 280\nSagas 10\nTotal amnt. 2817\nLess expenses. 1146\nCash in hand. 1671"
    )
    parsed = parse_whatsapp_day(raw)
    out = format_summary(parsed)
    assert 'Monday' in out
    assert 'Tables Served: 401' in out
    assert 'Arrests: 10' in out
    assert 'Table Payment' in out
    assert 'Arrest Cash' in out
    assert 'ZIMRA' in out or 'Zimra' in out
    assert '-> Total Income: $ 2817' in out
    assert '-> Total Expenses: $ 1146' in out
    assert 'Expected cash: $ 1671' in out