from collections.abc import Awaitable, Callable
from typing import final, override

import discord

from . import queries
from .constants import DEFAULT_QUOTE_EMOJI_NAME
from .db import get_session
from .models import Quote, QuotedMessage, User

type QuoteModalHandler = Callable[
    [discord.Interaction, str | None, str], Awaitable[None]
]
type ReportModalHandler = Callable[[discord.Interaction, str | None], Awaitable[None]]
type ButtonAction = Callable[[discord.Interaction], Awaitable[None]]

NO_MENTIONS = discord.AllowedMentions.none()
EMBED_COLOR = 0x5865F2
MAX_EMBED_DESCRIPTION = 4096


def safe_text(content: str | None) -> str | None:
    """Neutralize @everyone/@here in user-controlled message content."""
    return None if content is None else discord.utils.escape_mentions(content)


async def respond(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
) -> None:
    embed = embed or discord.Embed(description=safe_text(content) or "")
    if view is None:
        await interaction.response.send_message(
            embed=embed, ephemeral=ephemeral, allowed_mentions=NO_MENTIONS
        )
    else:
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=ephemeral,
            allowed_mentions=NO_MENTIONS,
        )


async def send_reply(
    message: discord.Message,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    mention_author: bool = False,
) -> discord.Message:
    embed = embed or discord.Embed(description=safe_text(content) or "")
    if view is None:
        return await message.reply(
            embed=embed,
            mention_author=mention_author,
            allowed_mentions=NO_MENTIONS,
        )
    return await message.reply(
        embed=embed,
        view=view,
        mention_author=mention_author,
        allowed_mentions=NO_MENTIONS,
    )


def emoji_key(raw: str) -> str:
    """Canonical stored/compared form of an emoji string."""
    return str(discord.PartialEmoji.from_str(raw))


def emoji_matches(emoji: discord.PartialEmoji, configured: list[str]) -> bool:
    name = (emoji.name or "").lower()
    key = str(emoji).lower()
    if configured:
        options = {c.lower() for c in configured}
        return key in options or name in options
    return name == DEFAULT_QUOTE_EMOJI_NAME


def message_jump_url(quoted: QuotedMessage) -> str:
    return (
        f"https://discord.com/channels/{quoted.guild_id}/"
        f"{quoted.channel_id}/{quoted.message_id}"
    )


def quote_embed(
    quote: Quote,
    display: str,
    source: QuotedMessage | None = None,
    avatar_url: str | None = None,
) -> discord.Embed:
    text = safe_text(quote.text) or ""
    line = f"-# [[Message]]({message_jump_url(source)})" if source else ""
    if line:
        # Reserve the line plus its leading newline, keeping every other character.
        text = text[: MAX_EMBED_DESCRIPTION - len(line) - 1]
        line = f"\n{line}"
    else:
        text = text[:MAX_EMBED_DESCRIPTION]
    embed = discord.Embed(description=text + line, color=EMBED_COLOR)
    embed.set_footer(text=f"- {display} | ID: {quote.id}")
    if avatar_url is not None:
        embed.set_thumbnail(url=avatar_url)
    return embed


def help_embed(prefix: str, max_length: int) -> discord.Embed:
    safe_prefix = discord.utils.escape_mentions(prefix)
    embed = discord.Embed(
        title="Lequ help",
        description="Store and retrieve quotes.",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Quotes",
        value=(
            f"`{safe_prefix}q` — random quote\n"
            f"`{safe_prefix}q <id>` — show that quote\n"
            f"`{safe_prefix}q <user>` — random quote from a user\n"
            f"`{safe_prefix}q all` — quote stats\n"
            f"`{safe_prefix}q all <user>` / `{safe_prefix}q <user> all` — list quotes\n"
            f"`{safe_prefix}q <user> <text>` — add a quote\n"
            f"`{safe_prefix}q` as a reply — quote the replied message\n"
            f"`{safe_prefix}quote` — alias for `{safe_prefix}q`\n"
            "`<user>` — mention, name, or alias (numeric ID when listing or adding)"
        ),
        inline=False,
    )
    embed.add_field(
        name="Aliases",
        value="`/alias add <name> <alias>` — add\n`/alias remove <alias>` — remove",
        inline=False,
    )
    embed.add_field(
        name="Admin (Manage Server)",
        value=(
            f"`/admin prefix [{safe_prefix}]` — change the prefix\n"
            "`/admin max-quote-length [value]` — quote length limit\n"
            "`/admin emojis add|remove|list` — quote reaction emojis\n"
            "`/admin reports` — review reported quotes"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Prefix: {safe_prefix} · Max length: {max_length}")
    return embed


def quote_choice_name(quote: Quote) -> str:
    """One-line autocomplete label, guaranteed to fit Discord's 100 character limit."""
    suffix = f" [{quote.id}]"
    text = " ".join(quote.text.split())
    return text[: 100 - len(suffix)] + suffix


async def user_profile(bot: discord.Client, user: User) -> tuple[str, str | None]:
    """Current username and avatar URL; named users have no avatar."""
    if user.discord_id is None:
        return user.name or "unknown", None
    found = bot.get_user(user.discord_id)
    if found is None:
        try:
            found = await bot.fetch_user(user.discord_id)
        except discord.HTTPException:
            return str(user.discord_id), None
    return found.name, found.display_avatar.url


def paginate[T](items: list[T], per_page: int) -> list[list[T]]:
    return [items[i : i + per_page] for i in range(0, len(items), per_page)]


@final
class ActionButton(discord.ui.Button["discord.ui.View"]):
    """Button that runs a caller-provided coroutine function."""

    def __init__(
        self,
        label: str,
        style: discord.ButtonStyle,
        action: ButtonAction,
        *,
        row: int | None = None,
    ) -> None:
        super().__init__(label=label, style=style, row=row)
        self._action: ButtonAction = action

    @override
    async def callback(self, interaction: discord.Interaction) -> None:
        await self._action(interaction)


@final
class QuoteModal(discord.ui.Modal):
    def __init__(
        self,
        handler: QuoteModalHandler,
        *,
        name: str | None,
        text: str | None,
        ask_name: bool,
        max_length: int,
    ) -> None:
        super().__init__(title="Add Quote")
        self._handler: QuoteModalHandler = handler
        self._name: str | None = name
        self._text: str | None = text
        self.name_input: discord.ui.TextInput[QuoteModal] | None = None
        self.text_input: discord.ui.TextInput[QuoteModal] | None = None
        if ask_name:
            self.name_input = discord.ui.TextInput(
                label="Name",
                placeholder="Name or Discord user (if not selected above)",
                required=True,
                max_length=100,
            )
            self.add_item(self.name_input)
        if text is None:
            self.text_input = discord.ui.TextInput(
                label="Quote",
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=max_length,
            )
            self.add_item(self.text_input)

    @override
    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name_input.value if self.name_input is not None else self._name
        text = self.text_input.value if self.text_input is not None else self._text
        await self._handler(interaction, name, text or "")


@final
class ReportModal(discord.ui.Modal):
    def __init__(self, handler: ReportModalHandler) -> None:
        super().__init__(title="Report Quote")
        self._handler: ReportModalHandler = handler
        self.reason_input: discord.ui.TextInput[ReportModal] = discord.ui.TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
        )
        self.add_item(self.reason_input)

    @override
    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = self.reason_input.value.strip()
        await self._handler(interaction, reason or None)


@final
class Paginator(discord.ui.View):
    def __init__(
        self, pages: list[discord.Embed], owner_id: int, timeout: float = 180.0
    ) -> None:
        super().__init__(timeout=timeout)
        if not pages:
            raise ValueError("pages must not be empty")
        self.pages: list[discord.Embed] = pages
        self.owner_id: int = owner_id
        self.index: int = 0
        self.message: discord.Message | None = None
        self.first_button = ActionButton(
            "⏮", discord.ButtonStyle.secondary, self._first
        )
        self.prev_button = ActionButton("◀", discord.ButtonStyle.secondary, self._prev)
        self.next_button = ActionButton("▶", discord.ButtonStyle.secondary, self._next)
        self.last_button = ActionButton("⏭", discord.ButtonStyle.secondary, self._last)
        self.close_button = ActionButton("✖", discord.ButtonStyle.danger, self._close)
        self.nav_buttons: list[ActionButton] = [
            self.first_button,
            self.prev_button,
            self.next_button,
            self.last_button,
        ]
        self.action_buttons: list[ActionButton] = [self.close_button]
        for button in [*self.nav_buttons, *self.action_buttons]:
            self.add_item(button)
        self._sync_nav()

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await respond(interaction, "This menu isn't for you.", ephemeral=True)
            return False
        return True

    def _sync_nav(self) -> None:
        at_start = self.index == 0
        at_end = self.index == len(self.pages) - 1
        self.first_button.disabled = at_start
        self.prev_button.disabled = at_start
        self.next_button.disabled = at_end
        self.last_button.disabled = at_end

    async def _show(self, interaction: discord.Interaction, index: int) -> None:
        self.index = index
        self._sync_nav()
        await interaction.response.edit_message(embed=self.pages[index], view=self)

    async def _first(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, 0)

    async def _prev(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, max(self.index - 1, 0))

    async def _next(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, min(self.index + 1, len(self.pages) - 1))

    async def _last(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, len(self.pages) - 1)

    async def _close(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        self.stop()
        await interaction.response.defer()
        if self.message is not None:
            await self.message.delete()

    @override
    async def on_timeout(self) -> None:
        for button in [*self.nav_buttons, *self.action_buttons]:
            button.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


@final
class FavoriteView(discord.ui.View):
    """Star toggle attached to public quote messages; not owner locked."""

    def __init__(self, quote_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.quote_id: int = quote_id
        self.add_item(
            ActionButton("⭐ Favorite", discord.ButtonStyle.secondary, self.toggle)
        )

    async def toggle(self, interaction: discord.Interaction) -> None:
        async with get_session() as session:
            user = await queries.get_or_create_discord_user(
                session, interaction.user.id
            )
            now_favorite = await queries.toggle_favorite(
                session, user.id, self.quote_id
            )
        text = (
            "Added to your favorites."
            if now_favorite
            else "Removed from your favorites."
        )
        await respond(interaction, text, ephemeral=True)
