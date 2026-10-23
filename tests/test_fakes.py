import asyncio

from app.adapters.fakes import KeywordDecider
from app.adapters.ports import Option, Question


def decide(text, *options):
    q = Question("q", "", tuple(Option(v, h) for v, h in options))
    a = asyncio.run(KeywordDecider().decide(text, [q])).get("q")
    return a.value if a else None


def test_matches_word_prefix_case_insensitive():
    assert decide("It got DENTED badly", ("moderate", "dent")) == "moderate"


def test_does_not_match_inside_a_word():
    assert decide("there was an accident", ("moderate", "dent")) is None
    assert decide("the headlight is gone", ("minor", "light")) is None


def test_multi_word_hint_and_last_mention_wins():
    opts = (("left", "driver side"), ("right", "passenger side"))
    assert decide("driver  side... no, passenger side", *opts) == "right"


def test_longer_phrase_ending_at_same_place_wins():
    opts = (("front fender", "fender"), ("quarter panel", "rear fender"))
    assert decide("the rear fender is scraped", *opts) == "quarter panel"
