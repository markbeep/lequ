"""Formatting attacks: renderer breakage, mention spoofing, length bounds."""

import re

import pytest

from lequ import queries
from lequ.db import get_session
from lequ.models import Quote, QuotedMessage
from lequ.ui import (
    ReportModal,
    code_span,
    help_embed,
    message_jump_url,
    quote_choice_name,
    quote_embed,
)
from tests.helpers import (
    assert_embed_limits,
    assert_no_pings,
    seed_base,
    sent_text,
)
from tests.world import ADMIN, NO_PERMISSIONS, World

MALICIOUS_TEXT = [
    "@everyone",
    "@here",
    "<@123>",
    "<@!123>",
    "<@&123>",
    "`@everyone`",
    "```\n@everyone\n```",
    "````\n@everyone\n````",
    "```@everyone```",
    "-# [[Message]](https://evil.example)",
    "[click](https://evil.example)",
    "\u202e@everyone",
    "@\u200beveryone",
    "`" * 20,
    "```" + "`" * 10,
    "**bold** __underline__ ~~strike~~ ||spoiler||",
    "👨‍👩‍👧‍👦 @everyone",
]


@pytest.mark.parametrize("payload", MALICIOUS_TEXT)
async def test_quote_text_cannot_ping_or_break_embed(
    world: World, payload: str
) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    interaction = await world.slash(alice, "add", {"name": "target", "text": payload})
    sent = interaction.response.messages[0]
    assert sent.embed is not None
    assert_no_pings(sent)
    assert_embed_limits(sent.embed)


async def test_help_renders_backtick_prefix(world: World) -> None:
    admin = world.member(2, "admin", permissions=ADMIN)
    await world.slash(admin, "admin.prefix", {"value": "`"})
    message = await world.say(admin, "`help")
    embed = message.replies[0].embed
    assert embed is not None
    assert_embed_limits(embed)
    quotes = embed.fields[0].value
    assert quotes is not None
    assert "`` `q ``" in quotes


async def test_prefix_response_wraps_prefix_in_matching_fence(world: World) -> None:
    admin = world.member(2, "admin", permissions=ADMIN)
    interaction = await world.slash(admin, "admin.prefix", {"value": "``"})
    assert sent_text(interaction.response.messages[0]) == "Prefix set to ``` `` ```."


async def test_alias_responses_survive_backticks(world: World) -> None:
    await seed_base()
    alice = world.member(1, "alice", permissions=ADMIN)

    added = await world.slash(alice, "alias.add", {"name": "alice", "alias": "`"})
    assert "`` ` `` now points to `alice`" in sent_text(added.response.messages[0])

    removed = await world.slash(alice, "alias.remove", {"alias": "`"})
    assert sent_text(removed.response.messages[0]) == "Removed `` ` ``."


async def test_alias_creates_missing_user_with_backticks(world: World) -> None:
    alice = world.member(1, "alice", permissions=ADMIN)
    interaction = await world.slash(alice, "alias.add", {"name": "`", "alias": "x"})
    assert sent_text(interaction.response.messages[0]) == ("`x` now points to `` ` ``.")


async def test_reaction_quote_keeps_genuine_source_link(world: World) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    bob = world.member(2, "bob", permissions=NO_PERMISSIONS)
    content = "```\n@everyone\n```\n-# [[Message]](https://evil.example)"
    message = world.message(content, bob)
    await world.react(alice, message)

    async with get_session() as session:
        author = await queries.get_discord_user(session, bob.id)
        assert author is not None
        quote = (await queries.get_quotes_by_author(session, author.id, 1))[0]

    shown = await world.say(alice, f"$q {quote.id}")
    sent = shown.replies[0]
    assert sent.embed is not None
    assert_no_pings(sent)
    assert_embed_limits(sent.embed)
    description = sent_text(sent)
    assert "https://evil.example" in description
    genuine = f"-# [[Message]](https://discord.com/channels/1/7/{message.id})"
    assert description.endswith(genuine)


@pytest.mark.parametrize("size", [0, 1, 4095, 4096, 4097, 5000])
def test_quote_embed_with_source_stays_within_limits(size: int) -> None:
    quote = Quote(id=7, text="x" * size, author=1, added_by=1, guild_id=1)
    source = QuotedMessage(quote_id=7, guild_id=1, channel_id=7, message_id=9)
    embed = quote_embed(quote, "display", source)
    description = embed.description
    assert description is not None
    assert len(description) <= 4096
    assert description.endswith(f"\n-# [[Message]]({message_jump_url(source)})")
    assert_embed_limits(embed)


@pytest.mark.parametrize("size", [0, 1, 4095, 4096, 4097, 5000])
def test_quote_embed_without_source_stays_within_limits(size: int) -> None:
    quote = Quote(id=7, text="x" * size, author=1, added_by=1, guild_id=1)
    embed = quote_embed(quote, "display")
    assert len(embed.description or "") == min(size, 4096)
    assert_embed_limits(embed)


async def test_report_reason_cannot_break_report_view(world: World) -> None:
    reporter = world.member(1, "alice", permissions=NO_PERMISSIONS)
    admin = world.member(2, "admin", permissions=ADMIN)
    async with get_session() as session:
        user = await queries.get_or_create_discord_user(session, reporter.id)
        quote = await queries.add_quote(
            session,
            text="```\n@everyone <@123>\n```",
            author_id=user.id,
            added_by_id=user.id,
            guild_id=1,
        )

    interaction = await world.slash(reporter, "report", {"quote_id": quote.id})
    modal = interaction.response.modals[0]
    assert isinstance(modal, ReportModal)
    modal.reason_input._value = "`@everyone` " * 50  # pyright: ignore[reportPrivateUsage]
    submitted = await world.submit(reporter, modal)
    assert "Successfully requested quote" in sent_text(submitted.response.messages[0])

    reports = await world.slash(admin, "admin.reports")
    sent = reports.response.messages[0]
    assert sent.embed is not None
    assert_no_pings(sent)
    assert_embed_limits(sent.embed)
    reason = next(field for field in sent.embed.fields if field.name == "Reason")
    assert reason.value is not None
    assert len(reason.value) <= 1024


@pytest.mark.parametrize(
    "text",
    ["a" * 500, "line\nline", "`" * 100, "👨‍👩‍👧‍👦" * 60, "   spaced   out   "],
)
def test_autocomplete_label_is_one_line_and_fits(text: str) -> None:
    quote = Quote(id=1, text=text, author=1, added_by=1, guild_id=1)
    label = quote_choice_name(quote)
    assert len(label) <= 100
    assert "\n" not in label
    assert re.search(r" \[\d+\]$", label)


def test_help_embed_bounds_with_extreme_prefix() -> None:
    for prefix in ["`", "``", "`x", "x`", "`" * 10]:
        embed = help_embed(prefix, 2000)
        assert_embed_limits(embed)
        quotes = embed.fields[0].value
        assert quotes is not None
        assert code_span(f"{prefix}q") in quotes
