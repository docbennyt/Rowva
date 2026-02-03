from parser import parse_whatsapp_day
from logic import validate_and_summarize


def test_validate_summarize_example():
    raw = (
        "Sunday. 4Jan 25 Table. 291 Arrests. 1 Table payment. 2037 Arrest. 1 "
        "Expenses schoolboy transport 26 Joseline. 6 Total amnt 2038 Less expenses. 32 Cash in hand. 2006"
    )

    parsed = parse_whatsapp_day(raw)
    res = validate_and_summarize(parsed)
    st = res['structured_text']

    assert "Income:" in st
    assert any("table payment" in line.lower() and "2037" in line for line in st.splitlines())
    assert "Expenses:" in st
    assert any("transport" in line.lower() and ("26" in line or "26.00" in line) for line in st.splitlines())
    assert any("joseline" in line.lower() and ("6" in line) for line in st.splitlines())

    assert "-> Total Income: $ 2038" in st
    assert "-> Total Expenses: $ 32" in st
    assert "Expected cash: $ 2006" in st
    assert "WARNING: You recorded" not in st
    assert res['has_issue'] is False