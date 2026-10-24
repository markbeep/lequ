from dataclasses import dataclass

from tests.fakes import SentMessage
from lequ import queries
from lequ.db import get_session


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
