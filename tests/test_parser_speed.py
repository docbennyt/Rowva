import time
from parser import parse_whatsapp_day


def test_parser_speed():
    raw = (
        "Sunday. 4Jan 25 Table. 291 Arrests. 1 Table payment. 2037 Arrest. 1 "
        "Expenses schoolboy transport 26 Joseline. 6 Total amnt 2038 Less expenses. 32 Cash in hand. 2006"
    )
    start = time.perf_counter()
    for _ in range(50):
        _ = parse_whatsapp_day(raw)
    elapsed = (time.perf_counter() - start) / 50.0
    # average per run must be < 0.2s
    assert elapsed < 0.2