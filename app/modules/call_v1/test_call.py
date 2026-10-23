import pytest

from app.modules.call_v1 import CallBook, CallClosed, UnknownCall


def test_operational_principle_partial_then_final():
    book = CallBook()
    call = book.start("demo")
    assert book.version(call) == 0
    book.hear(call, "Atto front bum", final=False)
    assert book.transcript(call) == "Atto front bum"
    assert book.hear(call, "Atto front bumper", final=True) == 1
    assert book.transcript(call) == "Atto front bumper"


def test_ended_call_refuses_speech():
    book = CallBook()
    call = book.start("demo")
    book.end(call)
    with pytest.raises(CallClosed):
        book.hear(call, "x", final=True)


def test_unknown_call():
    with pytest.raises(UnknownCall):
        CallBook().transcript("nope")
