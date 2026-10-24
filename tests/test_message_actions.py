from hypothesis import given, settings
from hypothesis import strategies as st

from lequ import queries
from lequ.cogs.quote import QuoteCog
from lequ.db import get_session
from lequ.models import Quote, QuotedMessage
from lequ.ui import MAX_EMBED_DESCRIPTION, quote_embed
from tests.commands import command, dispatch_prefix, invoke
from tests.conftest import reset_db
from tests.fakes import (
    FakeBot,
    FakeChannel,
    FakeGuild,
    FakeInteraction,
    FakeMessage,
    FakeReference,
    FakeUser,
    as_bot,
    as_interaction,
    as_message,
)
from tests.helpers import assert_no_pings, quote_count, seed_base, sent_text


@st.composite
def command_text(draw: st.DrawFn) -> str:
    prefix = draw(st.sampled_from(["$", "!", "$$", "%"]))
    rest = draw(st.text(max_size=60))
    kind = draw(st.integers(0, 5))
    if kind == 0:
        return f"noise{rest}"
    if kind == 1:
        return f"{prefix}q{rest}"
    if kind == 2:
        return f"{prefix}quote {rest}"
    if kind == 3:
        return f"{prefix}q all {rest}"
    if kind == 4:
        return f"{prefix}q {rest} all"
    return f"{prefix}q {rest}"


async def run_message(
    content: str,
    *,
    author: FakeUser | None = None,
    reference: FakeReference | None = None,
    mentions: tuple[FakeUser, ...] = (),
    channel: FakeChannel | None = None,
    prefix: str = "$",
    bot: FakeBot | None = None,
) -> FakeMessage:
    guild = FakeGuild()
    message = FakeMessage(
        content,
        author or FakeUser(42, "Tester"),
        guild,
        reference=reference,
        mentions=mentions,
        channel=channel,
    )
    cog = QuoteCog(as_bot(bot or FakeBot()))
    await dispatch_prefix(cog, message, prefix)
    return message


@settings(max_examples=60, deadline=None)
@given(content=command_text())
async def test_message_commands_always_answer_or_ignore(content: str) -> None:
    await reset_db()
    await seed_base()
    assert await queries.cached_prefix(1) == "$"
    message = await run_message(content)
    words = content.split(maxsplit=1)
    if not words or words[0].lower() not in {"$q", "$quote"}:
        assert message.replies == []
        return
    assert len(message.replies) == 1
    assert_no_pings(message.replies[0])


async def test_empty_server_random_quote_gets_error() -> None:
    await reset_db()
    message = await run_message("$q")
    assert sent_text(message.replies[0]) == "There are no quotes on this server yet."


async def test_unknown_user_gets_error() -> None:
    await reset_db()
    message = await run_message("$q nobody")
    assert sent_text(message.replies[0]) == "nobody doesn't have any quotes."
    message = await run_message("$q all nobody")
    assert sent_text(message.replies[0]) == "nobody doesn't have any quotes."


async def test_numeric_token_shows_quote_by_id() -> None:
    await reset_db()
    await seed_base()
    async with get_session() as session:
        author = await queries.get_or_create_discord_user(session, 123)
        quotes = await queries.get_quotes_by_author(session, author.id, 1)
        quote_id = quotes[0].id
    assert quote_id is not None

    message = await run_message(f"$q {quote_id}")
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.footer.text is not None
    assert f"ID: {quote_id}" in embed.footer.text
    assert embed.thumbnail.url == "https://cdn.discordapp.com/avatars/123.png"

    message = await run_message("$q 999999")
    assert sent_text(message.replies[0]) == "No quote with that ID on this server."


async def test_all_without_user_shows_quote_stats() -> None:
    await reset_db()
    await seed_base()
    async with get_session() as session:
        tester = await queries.get_or_create_discord_user(session, 42)
        author = await queries.get_or_create_discord_user(session, 123)
        quotes = await queries.get_quotes_by_author(session, author.id, 1)
        await queries.add_favorite(session, tester.id, quotes[0].id)
    message = await run_message("$q all")
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.title == "All Quotes Stats"
    fields = {field.name: field.value for field in embed.fields}
    assert fields["Total Quotes"] == "3"
    assert fields["Total Names"] == "3"
    assert fields["Favorited"] == "1 / 3 (33.3%)"


async def test_add_stores_quote_and_reports_success() -> None:
    await reset_db()
    seeded = await seed_base()
    message = await run_message("$q alice brand new quote")
    assert message.replies[0].embed is not None
    assert await quote_count(seeded.alice_id) == 2


@settings(max_examples=30, deadline=None)
@given(text=st.text(min_size=1, max_size=80))
async def test_add_various_text_never_crashes(text: str) -> None:
    await reset_db()
    await seed_base()
    message = await run_message(f"$q alice {text}")
    assert len(message.replies) == 1
    assert_no_pings(message.replies[0])


async def test_too_long_quote_gets_error() -> None:
    await reset_db()
    await seed_base()
    async with get_session() as session:
        await queries.set_max_quote_length(session, 1, 5)
    message = await run_message("$q alice 123456")
    assert sent_text(message.replies[0]) == "Quotes are limited to 5 characters."


async def test_duplicate_quote_gets_error() -> None:
    await reset_db()
    await seed_base()
    message = await run_message("$q alice alice quote")
    assert sent_text(message.replies[0]) == "That message has already been quoted."


async def test_self_quote_gets_error() -> None:
    await reset_db()
    await seed_base()
    message = await run_message("$q <@42> hello")
    assert sent_text(message.replies[0]) == "You can't quote yourself."
    message = await run_message("$q 42 hello again")
    assert sent_text(message.replies[0]) == "You can't quote yourself."


async def test_alias_routes_to_canonical_named_user() -> None:
    await reset_db()
    seeded = await seed_base()
    message = await run_message("$q bobby alias quote")
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.footer.text is not None
    assert embed.footer.text.startswith("- bob | ID: ")
    assert embed.thumbnail.url is None
    assert await quote_count(seeded.bob_id) == 2


async def test_mention_and_numeric_id_add_quotes() -> None:
    await reset_db()
    seeded = await seed_base()
    guild = FakeGuild()
    member = FakeUser(123, "Mentioned")
    message = FakeMessage(
        "$q <@123> mention quote",
        FakeUser(42, "Tester"),
        guild,
        mentions=(member,),
    )
    bot = FakeBot()
    await dispatch_prefix(QuoteCog(as_bot(bot)), message)
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.footer.text is not None
    assert embed.footer.text.startswith("- Fetched123 | ID: ")
    assert embed.thumbnail.url == "https://cdn.discordapp.com/avatars/123.png"
    assert embed.color is not None
    assert bot.fetches == 1
    assert await quote_count(seeded.discord_id) == 2

    async with get_session() as session:
        await queries.get_or_create_discord_user(session, 777)
    bot = FakeBot()
    message = FakeMessage("$q 777 id quote", FakeUser(42, "Tester"), guild)
    await dispatch_prefix(QuoteCog(as_bot(bot)), message)
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.footer.text is not None
    assert embed.footer.text.startswith("- Fetched777 | ID: ")
    assert embed.thumbnail.url == "https://cdn.discordapp.com/avatars/777.png"
    assert bot.fetches == 1


async def test_reply_quotes_target_and_rejects_bad_targets() -> None:
    await reset_db()
    await seed_base()
    channel = FakeChannel()
    target = FakeMessage(
        "replied text", FakeUser(55, "Target"), FakeGuild(), channel=channel
    )
    channel.messages[target.id] = target
    message = await run_message(
        "$q", reference=FakeReference(target.id, target), channel=channel
    )
    assert message.replies[0].embed is not None

    message = await run_message(
        "$q", reference=FakeReference(target.id, target), channel=channel
    )
    assert sent_text(message.replies[0]) == "That message has already been quoted."

    empty = FakeMessage("   ", FakeUser(55, "Target"), FakeGuild(), channel=channel)
    channel.messages[empty.id] = empty
    message = await run_message(
        "$q", reference=FakeReference(empty.id, empty), channel=channel
    )
    assert sent_text(message.replies[0]) == "Can't quote that message."

    bot_target = FakeMessage(
        "bot text", FakeUser(55, "Bot", bot=True), FakeGuild(), channel=channel
    )
    channel.messages[bot_target.id] = bot_target
    message = await run_message(
        "$q", reference=FakeReference(bot_target.id, bot_target), channel=channel
    )
    assert sent_text(message.replies[0]) == "Can't quote that message."

    message = await run_message(
        "$q", reference=FakeReference(999999, None), channel=channel
    )
    assert sent_text(message.replies[0]) == "Could not find the replied message."


async def test_quoted_message_links_its_source() -> None:
    await reset_db()
    await seed_base()
    channel = FakeChannel()
    target = FakeMessage(
        "source text", FakeUser(55, "Target"), FakeGuild(), channel=channel
    )
    channel.messages[target.id] = target
    message = await run_message(
        "$q", reference=FakeReference(target.id, target), channel=channel
    )
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.description is not None
    url = f"https://discord.com/channels/1/{channel.id}/{target.id}"
    assert embed.description.endswith(f"-# [[Message]]({url})")

    async with get_session() as session:
        author = await queries.get_or_create_discord_user(session, 55)
        quotes = await queries.get_quotes_by_author(session, author.id, 1)
        quote_id = quotes[-1].id

    interaction = FakeInteraction()
    cog = QuoteCog(as_bot(FakeBot()))
    await invoke(command(cog, "quote"), cog, interaction, quote_id)
    quote_embed = interaction.response.messages[0].embed
    assert quote_embed is not None
    assert quote_embed.description is not None
    assert quote_embed.description.endswith(f"-# [[Message]]({url})")

    message = await run_message("$q all <@55>")
    listing = message.replies[0].embed
    assert listing is not None
    assert listing.description is not None
    assert url in listing.description


def test_quote_embed_truncates_text_for_message_link() -> None:
    quote = Quote(id=1, text="x" * 5000, author=1, added_by=1, guild_id=1)
    source = QuotedMessage(id=1, quote_id=1, guild_id=1, channel_id=2, message_id=3)
    embed = quote_embed(quote, "user", source)
    assert embed.description is not None
    line = "-# [[Message]](https://discord.com/channels/1/2/3)"
    kept = MAX_EMBED_DESCRIPTION - len(line) - 1
    assert embed.description == "x" * kept + f"\n{line}"
    assert len(embed.description) == MAX_EMBED_DESCRIPTION


async def test_bot_messages_and_wrong_prefix_are_ignored() -> None:
    await reset_db()
    message = await run_message("$q", author=FakeUser(42, "Tester", bot=True))
    assert message.replies == []
    message = await run_message("!q")
    assert message.replies == []
    message = await run_message("   ")
    assert message.replies == []


async def test_custom_prefix_is_used() -> None:
    await reset_db()
    await seed_base()
    async with get_session() as session:
        await queries.set_prefix(session, 1, "!")
    message = await run_message("!q all alice", prefix="!")
    assert message.replies[0].embed is not None
    message = await run_message("$q all alice", prefix="!")
    assert message.replies == []


@settings(max_examples=30, deadline=None)
@given(content=st.text(max_size=80), bot=st.booleans())
async def test_context_add_always_responds(content: str, bot: bool) -> None:
    await reset_db()
    await seed_base()
    guild = FakeGuild()
    message = FakeMessage(content, FakeUser(55, "Target", bot=bot), guild)
    interaction = FakeInteraction()
    await QuoteCog(as_bot(FakeBot())).context_add(
        as_interaction(interaction), as_message(message)
    )
    assert len(interaction.response.messages) == 1
    reply = interaction.response.messages[0]
    assert_no_pings(reply)
    assert reply.ephemeral
