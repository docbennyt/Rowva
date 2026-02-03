import json
from parser import parse_whatsapp_day


def test_parse_example():
    raw = (
        "Sunday. 4Jan 25 Table. 291 Arrests. 1 Table payment. 2037 Arrest. 1 "
        "Expenses schoolboy transport 26 Joseline. 6 Total amnt 2038 Less expenses. 32 Cash in hand. 2006"
    )

    parsed = parse_whatsapp_day(raw)

    assert parsed['date'] == '2025-01-04'

    income = json.loads(parsed['income_json'])
    expenses = json.loads(parsed['expenses_json'])

    # Expected items
    assert any('table payment' in k.lower() and v == 2037 for k, v in income.items())
    assert any(('transport' in k.lower() and v == 26) or ('joseline' in k.lower() and v == 6) for k, v in expenses.items())

    assert parsed['total_income'] == 2038.0
    assert parsed['total_expenses'] == 32.0
    assert parsed['cash_in_hand'] == 2006.0
