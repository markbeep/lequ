from hypothesis import given
from hypothesis import strategies as st

from lequ.cogs.quote import parse_quote_args, target_id


@given(st.text(max_size=120))
def test_parse_never_raises_and_respects_all(rest: str) -> None:
    result = parse_quote_args(rest)
    if not rest.split():
        assert result is None
        return
    assert result is not None
    mode, target, text = result
    assert mode in {"list", "add", "random"}
    assert target == target.split()[0] if target else True
    words = rest.split(maxsplit=1)
    first = words[0]
    second = words[1] if len(words) > 1 else ""
    if first.lower() == "all" or second.lower() == "all":
        assert mode == "list"
        assert text == ""
    if mode == "add":
        assert target and text
        assert text == rest.split(maxsplit=1)[1]
    if mode == "random":
        assert target and text == ""


@given(st.text(max_size=80))
def test_target_id_only_accepts_mentions(token: str) -> None:
    result = target_id(token)
    if result is not None:
        assert token.startswith("<@") and token.endswith(">")
        assert token == f"<@{result}>" or token == f"<@!{result}>"


def test_parse_examples() -> None:
    assert parse_quote_args("") is None
    assert parse_quote_args("   ") is None
    assert parse_quote_args("alice") == ("random", "alice", "")
    assert parse_quote_args("alice hello world") == ("add", "alice", "hello world")
    assert parse_quote_args("all alice") == ("list", "alice", "")
    assert parse_quote_args("alice all") == ("list", "alice", "")
    assert parse_quote_args("all") == ("list", "", "")
    assert parse_quote_args("all <@123>") == ("list", "<@123>", "")
    assert parse_quote_args("123 all") == ("list", "123", "")
