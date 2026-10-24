import discord
from hypothesis import given, settings
from hypothesis import strategies as st

from lequ import queries
from lequ.cogs.quote import QuoteCog
from lequ.db import get_session
from tests.conftest import reset_db
from tests.fakes import (
    FakeBot,
    FakeChannel,
    FakeGuild,
    FakeMessage,
    FakePayload,
    FakeUser,
    as_bot,
)
from tests.helpers import quote_count, seed_base


@settings(max_examples=40, deadline=None)
@given(
    emoji_name=st.sampled_from(["AddQuote", "addquote", "ADDQUOTE", "nope", "⭐", ""]),
    content=st.text(max_size=60),
    bot=st.booleans(),
    duplicate=st.booleans(),
)
async def test_reaction_outcome_matches_eligibility(
    emoji_name: str, content: str, bot: bool, duplicate: bool
) -> None:
    await reset_db()
    await seed_base()
    author = FakeUser(55, "Author", bot=bot)
    message = FakeMessage(content, author, FakeGuild())
    channel = FakeChannel()
    channel.messages[message.id] = message

    if duplicate and content.strip():
        async with get_session() as session:
            db_author = await queries.get_or_create_discord_user(session, 55)
            adder = await queries.get_or_create_discord_user(session, 42)
            await queries.add_quote(
                session,
                text=content.strip(),
                author_id=db_author.id,
                added_by_id=adder.id,
                guild_id=1,
            )

    bot_client = FakeBot()
    bot_client.channels[channel.id] = channel
    payload = FakePayload(
        channel_id=channel.id,
        message_id=message.id,
        member=FakeUser(42, "Tester"),
        emoji=discord.PartialEmoji(name=emoji_name),
    )
    await QuoteCog(as_bot(bot_client)).on_raw_reaction_add(payload)

    eligible = (
        emoji_name.lower() == "addquote"
        and not bot
        and bool(content.strip())
        and not duplicate
    )
    assert message.reactions == (["✅"] if eligible else [])
    if eligible:
        async with get_session() as session:
            db_author = await queries.get_discord_user(session, 55)
            assert db_author is not None
            assert await quote_count(db_author.id) == 1


async def test_configured_emoji_matches_and_bot_is_ignored() -> None:
    await reset_db()
    await seed_base()
    async with get_session() as session:
        await queries.add_emoji(session, 1, "<:custom:123>")
    message = FakeMessage("custom emoji quote", FakeUser(55, "Author"), FakeGuild())
    channel = FakeChannel()
    channel.messages[message.id] = message
    bot_client = FakeBot()
    bot_client.channels[channel.id] = channel

    await QuoteCog(as_bot(bot_client)).on_raw_reaction_add(
        FakePayload(
            channel_id=channel.id,
            message_id=message.id,
            member=FakeUser(42, "Tester"),
            emoji=discord.PartialEmoji(name="custom", id=123),
        )
    )
    assert message.reactions == ["✅"]

    bot_message = FakeMessage("bot quote", FakeUser(56, "Bot", bot=True), FakeGuild())
    channel.messages[bot_message.id] = bot_message
    await QuoteCog(as_bot(bot_client)).on_raw_reaction_add(
        FakePayload(
            channel_id=channel.id,
            message_id=bot_message.id,
            member=FakeUser(42, "Tester"),
            emoji=discord.PartialEmoji(name="custom", id=123),
        )
    )
    assert bot_message.reactions == []


async def test_member_can_be_fetched_when_payload_has_none() -> None:
    await reset_db()
    await seed_base()
    message = FakeMessage("fetched member quote", FakeUser(55, "Author"), FakeGuild())
    channel = FakeChannel()
    channel.messages[message.id] = message
    guild = FakeGuild()
    guild.members[42] = FakeUser(42, "Tester")
    bot_client = FakeBot()
    bot_client.channels[channel.id] = channel
    bot_client.guilds[guild.id] = guild

    await QuoteCog(as_bot(bot_client)).on_raw_reaction_add(
        FakePayload(
            channel_id=channel.id,
            message_id=message.id,
            member=None,
        )
    )
    assert message.reactions == ["✅"]
