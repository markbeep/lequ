from typing import TYPE_CHECKING, final, override

import discord
from discord import app_commands
from discord.ext import commands

from .. import queries
from ..constants import MAX_QUOTE_LENGTH
from ..db import get_session
from ..models import Quote, User
from ..ui import (
    FavoriteView,
    Paginator,
    QuoteModal,
    QuoteModalHandler,
    ReportModal,
    ReportModalHandler,
    emoji_matches,
    paginate,
    quote_choice_name,
    quote_embed,
    user_display,
)

if TYPE_CHECKING:
    from .. import LequBot

QUOTES_PER_PAGE = 8
PREVIEW_LENGTH = 350


@final
class CommandError(Exception):
    """User-facing error raised while adding a quote."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _quote_pages(quotes: list[Quote], title: str) -> list[discord.Embed]:
    pages: list[discord.Embed] = []
    chunks = paginate(quotes, QUOTES_PER_PAGE)
    total = len(chunks)
    index = 0
    for page_number, chunk in enumerate(chunks, start=1):
        lines: list[str] = []
        for quote in chunk:
            index += 1
            text = quote.text
            if len(text) > PREVIEW_LENGTH:
                text = text[:PREVIEW_LENGTH] + "[...]"
            lines.append(f"**#{index}** `[{quote.id}]`\n{text}")
        embed = discord.Embed(
            title=title, description="\n\n".join(lines), color=0x404648
        )
        embed.set_footer(text=f"Page {page_number}/{total}")
        pages.append(embed)
    return pages


async def quote_search_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if interaction.guild_id is None or not current.strip():
        return []
    async with get_session() as session:
        quotes = await queries.search_quotes(session, interaction.guild_id, current, 25)
    return [
        app_commands.Choice(name=quote_choice_name(q), value=str(q.id)) for q in quotes
    ]


@final
class QuoteCog(commands.Cog):
    def __init__(self, bot: LequBot) -> None:
        self.bot: LequBot = bot
        self.add_quote_menu: app_commands.ContextMenu | None = None

    @override
    async def cog_load(self) -> None:
        # CogMeta does not collect ContextMenu instances, so register it manually.
        self.add_quote_menu = app_commands.ContextMenu(
            name="Add Quote",
            callback=self.context_add,
            type=discord.AppCommandType.message,
            allowed_contexts=app_commands.AppCommandContext(
                guild=True, dm_channel=False, private_channel=False
            ),
        )
        self.bot.tree.add_command(self.add_quote_menu)

    async def _added_by(self, user_id: int) -> User:
        async with get_session() as session:
            return await queries.get_or_create_discord_user(session, user_id)

    async def _add(
        self,
        *,
        guild_id: int,
        added_by: User,
        member: discord.abc.User | None,
        name: str | None,
        text: str,
        channel_id: int | None = None,
        message_id: int | None = None,
    ) -> tuple[Quote, str]:
        text = text.strip()
        if not text:
            raise CommandError("The quote text is empty.")
        if len(text) > MAX_QUOTE_LENGTH:
            raise CommandError(f"Quotes are limited to {MAX_QUOTE_LENGTH} characters.")
        if member is not None and added_by.discord_id == member.id:
            raise CommandError("You can't quote yourself.")
        async with get_session() as session:
            if member is not None:
                author = await queries.get_or_create_discord_user(session, member.id)
                display = member.display_name
            else:
                cleaned = (name or "").strip()
                if not cleaned:
                    raise CommandError("No name or user given.")
                author = await queries.get_or_create_named_user(session, cleaned)
                display = author.name or cleaned
            quote = await queries.add_quote(
                session,
                text=text,
                author_id=queries.row_pk(author),
                added_by_id=queries.row_pk(added_by),
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
            )
        return quote, display

    def _modal_handler(
        self, guild_id: int, added_by: User, member: discord.Member | None
    ) -> QuoteModalHandler:
        async def handler(
            interaction: discord.Interaction, modal_name: str | None, modal_text: str
        ) -> None:
            try:
                quote, display = await self._add(
                    guild_id=guild_id,
                    added_by=added_by,
                    member=member,
                    name=modal_name,
                    text=modal_text,
                )
            except queries.AlreadyQuoted:
                await interaction.response.send_message(
                    "That message has already been quoted.", ephemeral=True
                )
                return
            except CommandError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await interaction.response.send_message(embed=quote_embed(quote, display))

        return handler

    def _report_handler(self, added_by: User, quote_id: int) -> ReportModalHandler:
        async def handler(interaction: discord.Interaction, reason: str | None) -> None:
            async with get_session() as session:
                try:
                    await queries.create_report(
                        session, quote_id, queries.row_pk(added_by), reason
                    )
                except queries.DuplicateReport:
                    await interaction.response.send_message(
                        "That quote has already been reported.", ephemeral=True
                    )
                    return
            await interaction.response.send_message(
                f"Reported quote {quote_id} for deletion.", ephemeral=True
            )

        return handler

    @app_commands.command(name="add", description="Add a quote")
    @app_commands.guild_only()
    @app_commands.describe(
        member="Discord user to quote",
        name="Name to quote (non-Discord)",
        text="The quote text",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
        name: str | None = None,
        text: str | None = None,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if member is not None and name is not None:
            await interaction.response.send_message(
                "Give either a user or a name, not both.", ephemeral=True
            )
            return
        added_by = await self._added_by(interaction.user.id)
        if text is None or (member is None and name is None):
            modal = QuoteModal(
                self._modal_handler(interaction.guild_id, added_by, member),
                name=name,
                text=text,
                ask_name=member is None and name is None,
            )
            await interaction.response.send_modal(modal)
            return
        try:
            quote, display = await self._add(
                guild_id=interaction.guild_id,
                added_by=added_by,
                member=member,
                name=name,
                text=text,
            )
        except CommandError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        except queries.AlreadyQuoted:
            await interaction.response.send_message(
                "That message has already been quoted.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=quote_embed(quote, display))

    @app_commands.command(name="quote", description="Show a quote")
    @app_commands.guild_only()
    @app_commands.describe(quote_id="ID of the quote to show (omit for a random quote)")
    async def quote(
        self, interaction: discord.Interaction, quote_id: int | None = None
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            if quote_id is None:
                quote = await queries.get_random_quote(session, interaction.guild_id)
            else:
                quote = await queries.get_quote(session, quote_id, interaction.guild_id)
            if quote is None:
                message = (
                    "There are no quotes on this server yet."
                    if quote_id is None
                    else "No quote with that ID on this server."
                )
                await interaction.response.send_message(message, ephemeral=True)
                return
            author = await queries.get_user(session, quote.author)
        display = user_display(author) if author is not None else "unknown"
        await interaction.response.send_message(
            embed=quote_embed(quote, display),
            view=FavoriteView(queries.row_pk(quote)),
        )

    @app_commands.command(name="quotes", description="List quotes")
    @app_commands.guild_only()
    @app_commands.describe(
        user="User whose quotes to show (default: you)",
        ephemeral="Only show the result to you",
    )
    async def quotes(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
        ephemeral: bool = False,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        target = user or interaction.user
        async with get_session() as session:
            db_user = await queries.get_or_create_discord_user(session, target.id)
            items = await queries.get_quotes_by_author(
                session, queries.row_pk(db_user), interaction.guild_id
            )
        if not items:
            await interaction.response.send_message(
                "No quotes found for this user.", ephemeral=True
            )
            return
        pages = _quote_pages(items, f"Quotes from {target.display_name}")
        view = Paginator(pages, interaction.user.id)
        await interaction.response.send_message(
            embed=pages[0], view=view, ephemeral=ephemeral
        )
        view.message = await interaction.original_response()

    @app_commands.command(name="search", description="Search for a quote")
    @app_commands.guild_only()
    @app_commands.describe(query="Text to search for")
    @app_commands.autocomplete(query=quote_search_autocomplete)
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            quote: Quote | None = None
            if query.strip().isdigit():
                quote = await queries.get_quote(
                    session, int(query), interaction.guild_id
                )
            if quote is None:
                hits = await queries.search_quotes(
                    session, interaction.guild_id, query, 1
                )
                quote = hits[0] if hits else None
            if quote is None:
                await interaction.response.send_message(
                    "No matching quote found.", ephemeral=True
                )
                return
            author = await queries.get_user(session, quote.author)
        display = user_display(author) if author is not None else "unknown"
        await interaction.response.send_message(
            embed=quote_embed(quote, display), view=FavoriteView(queries.row_pk(quote))
        )

    favorites = app_commands.Group(
        name="favorites", description="Your favorite quotes", guild_only=True
    )

    @favorites.command(name="list", description="List your favorite quotes")
    @app_commands.guild_only()
    async def favorites_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            db_user = await queries.get_or_create_discord_user(
                session, interaction.user.id
            )
            items = await queries.get_favorites(
                session, queries.row_pk(db_user), interaction.guild_id
            )
        if not items:
            await interaction.response.send_message(
                "You don't have any favorite quotes yet.", ephemeral=True
            )
            return
        pages = _quote_pages(items, "Your favorite quotes")
        view = Paginator(pages, interaction.user.id)
        await interaction.response.send_message(
            embed=pages[0], view=view, ephemeral=True
        )
        view.message = await interaction.original_response()

    @favorites.command(name="add", description="Add a quote to your favorites")
    @app_commands.guild_only()
    @app_commands.describe(quote_id="ID of the quote to favorite")
    async def favorites_add(
        self, interaction: discord.Interaction, quote_id: int
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            quote = await queries.get_quote(session, quote_id, interaction.guild_id)
            if quote is None:
                await interaction.response.send_message(
                    "No quote with that ID on this server.", ephemeral=True
                )
                return
            db_user = await queries.get_or_create_discord_user(
                session, interaction.user.id
            )
            added = await queries.add_favorite(
                session, queries.row_pk(db_user), quote_id
            )
        if added:
            await interaction.response.send_message(
                f"Added quote {quote_id} to your favorites.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "That quote is already in your favorites.", ephemeral=True
            )

    @favorites.command(name="remove", description="Remove a quote from your favorites")
    @app_commands.guild_only()
    @app_commands.describe(quote_id="ID of the quote to unfavorite")
    async def favorites_remove(
        self, interaction: discord.Interaction, quote_id: int
    ) -> None:
        async with get_session() as session:
            db_user = await queries.get_or_create_discord_user(
                session, interaction.user.id
            )
            removed = await queries.remove_favorite(
                session, queries.row_pk(db_user), quote_id
            )
        if removed:
            await interaction.response.send_message(
                f"Removed quote {quote_id} from your favorites.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "That quote is not in your favorites.", ephemeral=True
            )

    @app_commands.command(name="report", description="Report a quote for deletion")
    @app_commands.guild_only()
    @app_commands.describe(quote_id="ID of the quote to report")
    async def report(self, interaction: discord.Interaction, quote_id: int) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            quote = await queries.get_quote(session, quote_id, interaction.guild_id)
            if quote is None:
                await interaction.response.send_message(
                    "No quote with that ID on this server.", ephemeral=True
                )
                return
            existing = await queries.get_report(session, quote_id)
            added_by = await queries.get_or_create_discord_user(
                session, interaction.user.id
            )
        if existing is not None:
            await interaction.response.send_message(
                "That quote has already been reported.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            ReportModal(self._report_handler(added_by, quote_id))
        )

    async def context_add(
        self, interaction: discord.Interaction, message: discord.Message
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if message.author.bot or not message.content.strip():
            await interaction.response.send_message(
                "Can't quote that message.", ephemeral=True
            )
            return
        added_by = await self._added_by(interaction.user.id)
        try:
            quote, display = await self._add(
                guild_id=interaction.guild_id,
                added_by=added_by,
                member=message.author,
                name=None,
                text=message.content,
                channel_id=message.channel.id,
                message_id=message.id,
            )
        except queries.AlreadyQuoted:
            await interaction.response.send_message(
                "That message has already been quoted.", ephemeral=True
            )
            return
        except CommandError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=quote_embed(quote, display), ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """`<prefix>q` / `<prefix>quote` as a reply to a message quotes that message."""
        if message.author.bot or message.guild is None:
            return
        prefix = await queries.cached_prefix(message.guild.id)
        tokens = message.content.split()
        if not tokens or tokens[0].lower() not in {f"{prefix}q", f"{prefix}quote"}:
            return
        reference = message.reference
        if reference is None or reference.message_id is None:
            async with get_session() as session:
                quote = await queries.get_random_quote(session, message.guild.id)
                if quote is None:
                    await message.reply("There are no quotes on this server yet.")
                    return
                author = await queries.get_user(session, quote.author)
            display = user_display(author) if author is not None else "unknown"
            await message.reply(
                embed=quote_embed(quote, display),
                view=FavoriteView(queries.row_pk(quote)),
                mention_author=False,
            )
            return
        target = reference.cached_message
        if target is None:
            try:
                target = await message.channel.fetch_message(reference.message_id)
            except discord.HTTPException:
                await message.reply("Could not find the replied message.")
                return
        if target.author.bot or not target.content.strip():
            await message.reply("Can't quote that message.")
            return
        added_by = await self._added_by(message.author.id)
        try:
            quote, display = await self._add(
                guild_id=message.guild.id,
                added_by=added_by,
                member=target.author,
                name=None,
                text=target.content,
                channel_id=target.channel.id,
                message_id=target.id,
            )
        except queries.AlreadyQuoted:
            await message.reply("That message has already been quoted.")
            return
        except CommandError as exc:
            await message.reply(str(exc))
            return
        await message.reply(embed=quote_embed(quote, display), mention_author=False)

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self, payload: discord.RawReactionActionEvent
    ) -> None:
        if payload.guild_id is None:
            return
        configured = await queries.cached_emojis(payload.guild_id)
        if not emoji_matches(payload.emoji, configured):
            return
        member = payload.member
        if member is None:
            guild = self.bot.get_guild(payload.guild_id)
            if guild is None:
                return
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return
        if member.bot:
            return
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)
            except discord.HTTPException:
                return
        if not isinstance(channel, discord.abc.Messageable):
            return
        if (
            isinstance(channel, discord.abc.GuildChannel)
            and channel.type is discord.ChannelType.news
        ):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        if message.author.bot or not message.content.strip():
            return
        try:
            await self._add(
                guild_id=payload.guild_id,
                added_by=await self._added_by(member.id),
                member=message.author,
                name=None,
                text=message.content,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
            )
        except queries.AlreadyQuoted, CommandError:
            return
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass


async def setup(bot: LequBot) -> None:
    await bot.add_cog(QuoteCog(bot))
