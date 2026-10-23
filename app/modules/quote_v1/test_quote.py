import pytest

from app.modules.quote_v1 import DuplicateQuote, EmptyQuote, Quotes


def test_operational_principle_one_quote_per_call():
    q = Quotes()
    lines = [{"number": "AT-FB01", "name": "x", "qty": 1}] * 3
    quote = q.create("call-1", {"car": "Atto", "zone": "front bumper"}, lines)
    assert [x["id"] for x in q.list()] == [quote]
    assert len(q.for_call("call-1")["lines"]) == 3
    with pytest.raises(DuplicateQuote):
        q.create("call-1", {}, lines)


def test_empty_quote_refused():
    with pytest.raises(EmptyQuote):
        Quotes().create("call-2", {}, [])
