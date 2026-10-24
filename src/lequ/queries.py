import difflib
import logging

from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .constants import DEFAULT_MAX_QUOTE_LENGTH, DEFAULT_PREFIX
from .db import get_session
from .models import (
    Aliases,
    FavoriteQuote,
    GuildEmoji,
    GuildSettings,
    Quote,
    QuotedMessage,
    Report,
    User,
)


class AlreadyQuoted(Exception):
    """The source message of a quote has already been quoted."""


class DuplicateReport(Exception):
    """The quote already has an outstanding report."""


class NotNamedUser(Exception):
    """Aliases can only be assigned to named users."""


class AliasShadowed(Exception):
    """The alias is already the name of another named user."""


logger = logging.getLogger(__name__)

_prefix_cache: dict[int, str] = {}
_emoji_cache: dict[int, list[str]] = {}


async def get_or_create_discord_user(session: AsyncSession, discord_id: int) -> User:
    result = await session.exec(select(User).where(col(User.discord_id) == discord_id))
    user = result.first()
    if user is not None:
        return user
    logger.info("creating discord user row for discord_id=%s", discord_id)
    user = User(user_type="discord", discord_id=discord_id)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.exec(
            select(User).where(col(User.discord_id) == discord_id)
        )
        return result.one()
    return user


async def get_or_create_named_user(session: AsyncSession, name: str) -> User:
    result = await session.exec(select(User).where(col(User.name) == name))
    user = result.first()
    if user is not None:
        return user
    logger.info("creating named user row for name=%r", name)
    user = User(user_type="named", name=name)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        result = await session.exec(select(User).where(col(User.name) == name))
        return result.one()
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_discord_user(session: AsyncSession, discord_id: int) -> User | None:
    result = await session.exec(select(User).where(col(User.discord_id) == discord_id))
    return result.first()


async def get_named_user(session: AsyncSession, name: str) -> User | None:
    result = await session.exec(select(User).where(col(User.name) == name))
    return result.first()


async def get_alias_user(session: AsyncSession, alias: str) -> User | None:
    result = await session.exec(
        select(User)
        .join(Aliases, col(Aliases.user_id) == col(User.id))
        .where(col(Aliases.alias) == alias)
    )
    return result.first()


async def add_alias(session: AsyncSession, name: str, alias: str) -> bool:
    user = await get_named_user(session, name)
    if user is None:
        raise NotNamedUser
    shadow = await get_named_user(session, alias)
    if shadow is not None and shadow.id != user.id:
        logger.info("alias %r rejected: shadows named user %r", alias, alias)
        raise AliasShadowed
    logger.info("adding alias %r for named user %r", alias, name)
    session.add(Aliases(user_id=user.id, alias=alias))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return False
    return True


async def remove_alias(session: AsyncSession, alias: str) -> bool:
    result = await session.exec(delete(Aliases).where(col(Aliases.alias) == alias))
    await session.commit()
    logger.info("removed alias %r (removed=%s)", alias, result.rowcount > 0)
    return result.rowcount > 0


async def add_quote(
    session: AsyncSession,
    *,
    text: str,
    author_id: int,
    added_by_id: int,
    guild_id: int,
    channel_id: int | None = None,
    message_id: int | None = None,
) -> Quote:
    existing = await session.exec(
        select(Quote).where(
            col(Quote.guild_id) == guild_id,
            col(Quote.author) == author_id,
            col(Quote.text) == text,
        )
    )
    if existing.first() is not None:
        logger.info(
            "duplicate quote guild=%s author=%s text=%r",
            guild_id,
            author_id,
            text,
        )
        raise AlreadyQuoted from None
    logger.debug(
        "adding quote guild=%s author=%s added_by=%s text=%r",
        guild_id,
        author_id,
        added_by_id,
        text,
    )
    quote = Quote(text=text, author=author_id, added_by=added_by_id, guild_id=guild_id)
    session.add(quote)
    await session.flush()  # populates quote.id
    if message_id is not None:
        if channel_id is None:
            raise ValueError("channel_id is required when message_id is given")
        session.add(
            QuotedMessage(
                quote_id=quote.id,
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
            )
        )
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            logger.info(
                "message already quoted guild=%s channel=%s message=%s",
                guild_id,
                channel_id,
                message_id,
            )
            raise AlreadyQuoted from None
    await session.commit()
    logger.info(
        "quote added id=%s guild=%s author=%s message=%s",
        quote.id,
        guild_id,
        author_id,
        message_id,
    )
    return quote


async def get_quoted_message(
    session: AsyncSession, quote_id: int
) -> QuotedMessage | None:
    result = await session.exec(
        select(QuotedMessage).where(col(QuotedMessage.quote_id) == quote_id)
    )
    return result.first()


async def get_quoted_messages(
    session: AsyncSession, quote_ids: list[int]
) -> dict[int, QuotedMessage]:
    if not quote_ids:
        return {}
    result = await session.exec(
        select(QuotedMessage).where(col(QuotedMessage.quote_id).in_(quote_ids))
    )
    return {quoted.quote_id: quoted for quoted in result.all()}


async def get_quote(
    session: AsyncSession, quote_id: int, guild_id: int
) -> Quote | None:
    result = await session.exec(
        select(Quote).where(
            col(Quote.id) == quote_id,
            col(Quote.guild_id) == guild_id,
        )
    )
    return result.first()


async def get_quotes_by_author(
    session: AsyncSession, author_id: int, guild_id: int
) -> list[Quote]:
    result = await session.exec(
        select(Quote)
        .where(col(Quote.author) == author_id, col(Quote.guild_id) == guild_id)
        .order_by(col(Quote.id))
    )
    return list(result.all())


async def get_quote_stats(session: AsyncSession, guild_id: int) -> tuple[int, int, int]:
    """``(quotes, authors, favorited)`` counts for a guild."""
    quotes = (
        await session.exec(
            select(func.count())
            .select_from(Quote)
            .where(col(Quote.guild_id) == guild_id)
        )
    ).one()
    authors = (
        await session.exec(
            select(func.count(func.distinct(col(Quote.author)))).where(
                col(Quote.guild_id) == guild_id
            )
        )
    ).one()
    favorited = (
        await session.exec(
            select(func.count(func.distinct(col(FavoriteQuote.quote_id))))
            .join(Quote, col(FavoriteQuote.quote_id) == col(Quote.id))
            .where(col(Quote.guild_id) == guild_id)
        )
    ).one()
    return quotes, authors, favorited


async def get_random_quote(session: AsyncSession, guild_id: int) -> Quote | None:
    statement = select(Quote).where(col(Quote.guild_id) == guild_id)
    result = await session.exec(statement.order_by(func.random()).limit(1))
    return result.first()


async def get_random_quote_by_author(
    session: AsyncSession, author_id: int, guild_id: int
) -> Quote | None:
    statement = select(Quote).where(
        col(Quote.guild_id) == guild_id, col(Quote.author) == author_id
    )
    result = await session.exec(statement.order_by(func.random()).limit(1))
    return result.first()


async def search_quotes(
    session: AsyncSession, guild_id: int, query: str, limit: int = 25
) -> list[Quote]:
    # Ranks over every quote of the guild on each call (autocomplete fires per keystroke).
    # Fine at this scale; swap for a LIKE prefilter or an FTS index if a guild grows huge.
    needle = query.strip().lower()
    if not needle:
        return []
    result = await session.exec(select(Quote).where(col(Quote.guild_id) == guild_id))
    scored: list[tuple[float, int, Quote]] = []
    for quote in result.all():
        haystack = quote.text.lower()
        index = haystack.find(needle)
        if index != -1:
            score = 1000.0 - index
        else:
            ratio = difflib.SequenceMatcher(None, needle, haystack).ratio()
            # 0.5 keeps near-miss wordings ("never going" vs "never gonna give you up" = 0.53)
            # while unrelated text stays far below it.
            if ratio < 0.5:
                continue
            score = ratio * 100
        scored.append((score, quote.id or 0, quote))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [quote for _, _, quote in scored[:limit]]


async def delete_quote(session: AsyncSession, quote_id: int, guild_id: int) -> bool:
    result = await session.exec(
        delete(Quote).where(col(Quote.id) == quote_id, col(Quote.guild_id) == guild_id)
    )
    await session.commit()
    logger.info(
        "deleted quote id=%s guild=%s (deleted=%s)",
        quote_id,
        guild_id,
        result.rowcount > 0,
    )
    return result.rowcount > 0


async def create_report(
    session: AsyncSession, quote_id: int, reporter_id: int, reason: str | None
) -> Report:
    existing = await get_report(session, quote_id)
    if existing is not None:
        raise DuplicateReport
    logger.info(
        "creating report quote=%s reporter=%s reason=%r",
        quote_id,
        reporter_id,
        reason,
    )
    report = Report(quote_id=quote_id, reporter=reporter_id, reason=reason)
    session.add(report)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DuplicateReport from None
    return report


async def get_report(session: AsyncSession, quote_id: int) -> Report | None:
    result = await session.exec(select(Report).where(col(Report.quote_id) == quote_id))
    return result.first()


async def get_reports(
    session: AsyncSession, guild_id: int
) -> list[tuple[Report, Quote, User]]:
    result = await session.exec(
        select(Report, Quote, User)
        .join(Quote, col(Report.quote_id) == col(Quote.id))
        .join(User, col(Report.reporter) == col(User.id))
        .where(col(Quote.guild_id) == guild_id)
        .order_by(col(Report.id))
    )
    return [(row[0], row[1], row[2]) for row in result.all()]


async def delete_report(session: AsyncSession, quote_id: int) -> bool:
    result = await session.exec(delete(Report).where(col(Report.quote_id) == quote_id))
    await session.commit()
    logger.info("deleted report quote=%s (deleted=%s)", quote_id, result.rowcount > 0)
    return result.rowcount > 0


async def is_favorite(session: AsyncSession, user_id: int, quote_id: int) -> bool:
    result = await session.exec(
        select(FavoriteQuote).where(
            col(FavoriteQuote.user_id) == user_id,
            col(FavoriteQuote.quote_id) == quote_id,
        )
    )
    return result.first() is not None


async def add_favorite(session: AsyncSession, user_id: int, quote_id: int) -> bool:
    if await is_favorite(session, user_id, quote_id):
        return False
    logger.info("adding favorite user=%s quote=%s", user_id, quote_id)
    session.add(FavoriteQuote(user_id=user_id, quote_id=quote_id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return False
    return True


async def remove_favorite(session: AsyncSession, user_id: int, quote_id: int) -> bool:
    result = await session.exec(
        delete(FavoriteQuote).where(
            col(FavoriteQuote.user_id) == user_id,
            col(FavoriteQuote.quote_id) == quote_id,
        )
    )
    await session.commit()
    logger.info("removed favorite user=%s quote=%s", user_id, quote_id)
    return result.rowcount > 0


async def toggle_favorite(session: AsyncSession, user_id: int, quote_id: int) -> bool:
    """Toggle a favorite and return the new state (``True`` = favorited)."""
    if await is_favorite(session, user_id, quote_id):
        await remove_favorite(session, user_id, quote_id)
        return False
    await add_favorite(session, user_id, quote_id)
    return True


async def get_favorites(
    session: AsyncSession, user_id: int, guild_id: int
) -> list[Quote]:
    result = await session.exec(
        select(Quote)
        .join(FavoriteQuote, col(FavoriteQuote.quote_id) == col(Quote.id))
        .where(col(FavoriteQuote.user_id) == user_id, col(Quote.guild_id) == guild_id)
        .order_by(col(FavoriteQuote.id))
    )
    return list(result.all())


async def get_guild_settings(session: AsyncSession, guild_id: int) -> GuildSettings:
    settings = await session.get(GuildSettings, guild_id)
    if settings is not None:
        return settings
    settings = GuildSettings(guild_id=guild_id)
    session.add(settings)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        settings = await session.get_one(GuildSettings, guild_id)
    return settings


async def set_prefix(session: AsyncSession, guild_id: int, prefix: str | None) -> str:
    stored = prefix if prefix else DEFAULT_PREFIX
    settings = await get_guild_settings(session, guild_id)
    settings.prefix = stored
    session.add(settings)
    await session.commit()
    _prefix_cache[guild_id] = stored
    logger.info("prefix updated guild=%s prefix=%r", guild_id, stored)
    return stored


async def set_max_quote_length(
    session: AsyncSession, guild_id: int, value: int | None
) -> int:
    stored = value if value is not None else DEFAULT_MAX_QUOTE_LENGTH
    settings = await get_guild_settings(session, guild_id)
    settings.max_quote_length = stored
    session.add(settings)
    await session.commit()
    logger.info("max quote length updated guild=%s value=%s", guild_id, stored)
    return stored


async def get_emojis(session: AsyncSession, guild_id: int) -> list[str]:
    result = await session.exec(
        select(GuildEmoji)
        .where(col(GuildEmoji.guild_id) == guild_id)
        .order_by(col(GuildEmoji.id))
    )
    return [row.emoji for row in result.all()]


async def add_emoji(session: AsyncSession, guild_id: int, emoji: str) -> bool:
    await get_guild_settings(session, guild_id)  # FK target must exist
    if emoji in await get_emojis(session, guild_id):
        return False
    session.add(GuildEmoji(guild_id=guild_id, emoji=emoji))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return False
    _emoji_cache.pop(guild_id, None)
    logger.info("added quote emoji guild=%s emoji=%r", guild_id, emoji)
    return True


async def remove_emoji(session: AsyncSession, guild_id: int, emoji: str) -> bool:
    result = await session.exec(
        delete(GuildEmoji).where(
            col(GuildEmoji.guild_id) == guild_id, col(GuildEmoji.emoji) == emoji
        )
    )
    await session.commit()
    _emoji_cache.pop(guild_id, None)
    logger.info(
        "removed quote emoji guild=%s emoji=%r (removed=%s)",
        guild_id,
        emoji,
        result.rowcount > 0,
    )
    return result.rowcount > 0


async def cached_prefix(guild_id: int) -> str:
    cached = _prefix_cache.get(guild_id)
    if cached is not None:
        return cached
    async with get_session() as session:
        return (await get_guild_settings(session, guild_id)).prefix


async def cached_emojis(guild_id: int) -> list[str]:
    cached = _emoji_cache.get(guild_id)
    if cached is not None:
        return cached
    async with get_session() as session:
        emojis = await get_emojis(session, guild_id)
    _emoji_cache[guild_id] = emojis
    return emojis
