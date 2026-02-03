from parser import parse_whatsapp_day


def test_case_simple_arrest():
    raw = (
        "Sunday. 4Jan 25 Table. 291 Arrests. 1 Table payment. 2037 Arrest. 1 "
        "Expenses schoolboy transport 26 Joseline. 6 Total amnt 2038 Less expenses. 32 Cash in hand. 2006"
    )
    parsed = parse_whatsapp_day(raw)
    assert parsed['date'].startswith('2025')
    assert parsed['tables_count'] == 291
    assert parsed['arrests_count'] == 1
    assert any('table payment' in k.lower() and v == 2037 for k, v in parsed['income'].items())
    assert any('arrest' in k.lower() and v == 1 for k, v in parsed['income'].items())
    assert parsed['total_income'] == 2038.0
    assert parsed['total_expenses'] == 32.0
    assert parsed['cash_in_hand'] == 2006.0


def test_case_zimra_monday():
    raw = (
        "Monday. 29Dec 25\nTables. 401\nArrests. 10\nTable payment. 2807\nArrests. 10\n"
        "Expenses. Schoolboy transport. 26\nJoseline. 6\nJoseline overtime.sunday. 24\nSchoolboy salaries. 800\nZimra 280\nSagas 10\nTotal amnt. 2817\nLess expenses. 1146\nCash in hand. 1671"
    )
    parsed = parse_whatsapp_day(raw)
    assert parsed['date'].startswith('2025')
    assert parsed['tables_count'] == 401
    assert parsed['arrests_count'] == 10
    assert any('table payment' in k.lower() and v == 2807 for k, v in parsed['income'].items())
    assert any('arrest' in k.lower() and v == 10 for k, v in parsed['income'].items())
    # Confirm Zimra split recorded
    assert parsed['expenses'].get('Zimra (Net)', 0) == 140.0
    assert parsed['expenses'].get('Zimra (Shared)', 0) == 140.0
    assert parsed['total_income'] == 2817.0
    assert parsed['total_expenses'] == 1146.0
    assert parsed['cash_in_hand'] == 1671.0