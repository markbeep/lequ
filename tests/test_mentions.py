import discord
from hypothesis import given, settings, strategies as st

from tests.commands import dispatch_prefix, group, invoke, subcommand
from tests.conftest import reset_db
from tests.fakes import (
    FakeBot,
    FakeGuild,
    FakeInteraction,
    FakeMessage,
    FakeUser,
    as_bot,
    as_interaction,
    as_message,
)
from tests.helpers import assert_no_pings, seed_base, sent_text
from lequ import queries
from lequ.cogs.admin import AdminCog
from lequ.cogs.quote import QuoteCog
from lequ.db import get_session
from lequ.ui import FavoriteView, Paginator, respond, safe_text, send_reply

MALICIOUS = ["@everyone", "@here", "<@123>", "<@&123>", "<@!123>", "<@&!123>"]


async def test_send_helpers_strip_everyone_and_here() -> None:
    message = FakeMessage("", FakeUser(1), FakeGuild())
    raw = "@everyone @here <@123> <@&123>"
    await send_reply(as_message(message), raw)
    assert_no_pings(message.replies[0])
    assert sent_text(message.replies[0]) == safe_text(raw)

    interaction = FakeInteraction()
    await respond(as_interaction(interaction), raw)
    assert_no_pings(interaction.response.messages[0])
    assert sent_text(interaction.response.messages[0]) == safe_text(raw)


@settings(max_examples=30, deadline=None)
@given(token=st.sampled_from(MALICIOUS), text=st.text(max_size=20))
async def test_message_commands_never_ping(token: str, text: str) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    guild = FakeGuild()
    for content in (
        f"$q {token}",
        f"$q all {token}",
        f"$q {token} all",
        f"$q {token} {text}",
    ):
        message = FakeMessage(content, FakeUser(42, "Tester"), guild)
        await dispatch_prefix(cog, message)
        assert message.replies, content
        for sent in message.replies:
            assert_no_pings(sent)


async def test_quote_text_mentions_never_ping() -> None:
    await reset_db()
    async with get_session() as session:
        author = await queries.get_or_create_named_user(session, "alice")
        adder = await queries.get_or_create_discord_user(session, 42)
        await queries.add_quote(
            session,
            text="@everyone @here <@123> <@&123>",
            author_id=author.id,
            added_by_id=adder.id,
            guild_id=1,
        )
    cog = QuoteCog(as_bot(FakeBot()))
    for content in ("$q alice", "$q all alice"):
        message = FakeMessage(content, FakeUser(42, "Tester"), FakeGuild())
        await dispatch_prefix(cog, message)
        assert message.replies
        assert_no_pings(message.replies[0])


@settings(max_examples=20, deadline=None)
@given(value=st.sampled_from(MALICIOUS))
async def test_admin_responses_never_ping(value: str) -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    prefix = subcommand(group(cog, "admin"), "prefix")
    interaction = FakeInteraction()
    await invoke(prefix, cog, interaction, value)
    assert_no_pings(interaction.response.messages[0])

    quote_cog = QuoteCog(as_bot(FakeBot()))
    alias = subcommand(group(quote_cog, "alias"), "add")
    interaction = FakeInteraction()
    await invoke(alias, quote_cog, interaction, value, value)
    assert_no_pings(interaction.response.messages[0])


async def test_button_responses_never_ping() -> None:
    await reset_db()
    interaction = FakeInteraction()
    await FavoriteView(1).toggle(as_interaction(interaction))
    assert_no_pings(interaction.response.messages[0])

    other = FakeInteraction(FakeUser(999))
    await Paginator([discord.Embed(title="page")], 42).first_button.callback(
        as_interaction(other)
    )
    assert_no_pings(other.response.messages[0])
