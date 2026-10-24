import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lequ import queries
from lequ.cogs.admin import AdminCog
from lequ.cogs.quote import QuoteCog
from lequ.db import get_session
from lequ.ui import code_span, safe_text
from tests.commands import group, invoke, subcommand, subgroup
from tests.conftest import reset_db
from tests.fakes import FakeBot, FakeInteraction, as_bot
from tests.helpers import seed_base, sent_text


def only_message(interaction: FakeInteraction) -> str:
    assert len(interaction.response.messages) == 1
    return sent_text(interaction.response.messages[0])


@settings(max_examples=50, deadline=None)
@given(value=st.one_of(st.none(), st.text(max_size=20)))
async def test_prefix_command_always_responds(value: str | None) -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    cmd = subcommand(group(cog, "admin"), "prefix")
    interaction = FakeInteraction()
    await invoke(cmd, cog, interaction, value)
    message = only_message(interaction)

    valid = (
        value is not None
        and 1 <= len(value) <= 10
        and not any(c.isspace() for c in value)
    )
    async with get_session() as session:
        settings = await queries.get_guild_settings(session, 1)
    if valid:
        assert value is not None
        assert settings.prefix == value
        assert message == safe_text(f"Prefix set to {code_span(value)}.")
    elif value is None:
        assert settings.prefix == "$"
        assert message == "Prefix reset to `$`."
    else:
        assert message == "The prefix must be 1 to 10 characters without whitespace."


@settings(max_examples=50, deadline=None)
@given(value=st.one_of(st.none(), st.integers(min_value=-1000, max_value=5000)))
async def test_max_quote_length_always_responds(value: int | None) -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    cmd = subcommand(group(cog, "admin"), "max-quote-length")
    interaction = FakeInteraction()
    await invoke(cmd, cog, interaction, value)
    message = only_message(interaction)

    async with get_session() as session:
        settings = await queries.get_guild_settings(session, 1)
    if value is None:
        assert settings.max_quote_length == 500
        assert message == "Max quote length reset to 500."
    elif 1 <= value <= 2000:
        assert settings.max_quote_length == value
        assert message == f"Max quote length set to {value}."
    else:
        assert settings.max_quote_length == 500
        assert message == "The max quote length must be between 1 and 2000."


@settings(max_examples=50, deadline=None)
@given(
    name=st.sampled_from(["alice", "bob", "nobody", "123", "all"]),
    alias=st.text(max_size=20),
)
async def test_alias_add_always_responds(name: str, alias: str) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    cmd = subcommand(group(cog, "alias"), "add")
    interaction = FakeInteraction()
    await invoke(cmd, cog, interaction, name, alias)
    only_message(interaction)


@settings(max_examples=30, deadline=None)
@given(alias=st.text(max_size=20))
async def test_alias_remove_always_responds(alias: str) -> None:
    await reset_db()
    cog = QuoteCog(as_bot(FakeBot()))
    cmd = subcommand(group(cog, "alias"), "remove")
    interaction = FakeInteraction()
    await invoke(cmd, cog, interaction, alias)
    only_message(interaction)


@settings(max_examples=50, deadline=None)
@given(emote=st.text(max_size=20))
async def test_emoji_commands_always_respond(emote: str) -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    emote_group = subgroup(group(cog, "admin"), "emote")
    add = subcommand(emote_group, "add")
    remove = subcommand(emote_group, "remove")
    list_cmd = subcommand(emote_group, "list")

    for cmd, args in ((add, (emote,)), (remove, (emote,)), (list_cmd, ())):
        interaction = FakeInteraction()
        await invoke(cmd, cog, interaction, *args)
        only_message(interaction)


VALID_EMOJIS = [
    "👍",
    "⭐",
    "❤️",
    "👨‍👩‍👧‍👦",
    "1️⃣",
    "🏳️‍🌈",
    "<:AddQuote:123456789012345678>",
    "<a:party:123456789012345678>",
]

INVALID_EMOJIS = ["`", "@everyone", "not an emoji", "```", "AddQuote", "", "<:x:1>"]


@pytest.mark.parametrize("emote", VALID_EMOJIS)
async def test_emoji_add_accepts_real_emojis(emote: str) -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    cmd = subcommand(subgroup(group(cog, "admin"), "emote"), "add")
    interaction = FakeInteraction()
    await invoke(cmd, cog, interaction, emote)
    assert only_message(interaction) == "Added."
    async with get_session() as session:
        assert await queries.get_emojis(session, 1) == [emote]


@pytest.mark.parametrize("emote", INVALID_EMOJIS)
async def test_emoji_add_rejects_text(emote: str) -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    cmd = subcommand(subgroup(group(cog, "admin"), "emote"), "add")
    interaction = FakeInteraction()
    await invoke(cmd, cog, interaction, emote)
    assert only_message(interaction) == "That is not a valid emoji."
    async with get_session() as session:
        assert await queries.get_emojis(session, 1) == []


async def test_reports_with_no_reports_responds() -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    cmd = subcommand(group(cog, "admin"), "reports")
    interaction = FakeInteraction()
    await invoke(cmd, cog, interaction)
    assert only_message(interaction) == "There are no outstanding reports."
