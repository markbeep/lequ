from dataclasses import dataclass

import discord

from lequ import queries
from lequ.constants import ERROR_COLOR
from lequ.db import get_session
from tests.fakes import SentMessage


@dataclass(frozen=True)
class Seeded:
    tester_id: int
    alice_id: int
    bob_id: int
    discord_id: int


async def seed_base(guild_id: int = 1) -> Seeded:
    async with get_session() as session:
        tester = await queries.get_or_create_discord_user(session, 42)
        alice = await queries.get_or_create_named_user(session, "alice")
        bob = await queries.get_or_create_named_user(session, "bob")
        discord = await queries.get_or_create_discord_user(session, 123)
        await queries.add_quote(
            session,
            text="alice quote",
            author_id=alice.id,
            added_by_id=tester.id,
            guild_id=guild_id,
        )
        await queries.add_quote(
            session,
            text="bob quote",
            author_id=bob.id,
            added_by_id=tester.id,
            guild_id=guild_id,
        )
        await queries.add_quote(
            session,
            text="discord quote",
            author_id=discord.id,
            added_by_id=tester.id,
            guild_id=guild_id,
        )
        await queries.add_alias(session, "bob", "bobby")
        return Seeded(tester.id, alice.id, bob.id, discord.id)


async def quote_count(author_id: int, guild_id: int = 1) -> int:
    async with get_session() as session:
        return len(await queries.get_quotes_by_author(session, author_id, guild_id))


def sent_text(sent: SentMessage) -> str:
    assert sent.content is None
    assert sent.embed is not None
    return sent.embed.description or ""


def assert_error(sent: SentMessage, text: str) -> None:
    assert sent.embed is not None
    assert sent.embed.color is not None
    assert sent.embed.color.value == ERROR_COLOR
    assert sent_text(sent) == text


def assert_embed_limits(embed: discord.Embed) -> None:
    """Discord rejects embeds over these bounds; a user must never reach them."""
    limits = {
        "title": (embed.title, 256),
        "description": (embed.description, 4096),
        "footer": (embed.footer.text, 2048),
    }
    for label, (value, limit) in limits.items():
        if value is not None:
            assert len(value) <= limit, f"{label} is {len(value)} > {limit}"
    assert len(embed.fields) <= 25
    for field in embed.fields:
        assert field.name is not None and len(field.name) <= 256
        assert field.value is not None and len(field.value) <= 1024


def assert_no_pings(sent: SentMessage) -> None:
    assert sent.content is None
    assert sent.embed is not None
    assert sent.allowed_mentions is not None
    assert not sent.allowed_mentions.everyone
    assert not sent.allowed_mentions.users
    assert not sent.allowed_mentions.roles
    assert not sent.allowed_mentions.replied_user
    texts = [sent.embed.description, sent.embed.title]
    texts.extend(field.value for field in sent.embed.fields)
    texts.extend(field.name for field in sent.embed.fields)
    for text in texts:
        if text is not None:
            assert "@everyone" not in text
            assert "@here" not in text
