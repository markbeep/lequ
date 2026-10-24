import unicodedata
from collections.abc import Awaitable, Callable
from typing import final, override

import discord

from . import queries
from .constants import DEFAULT_QUOTE_EMOJI_NAME, ERROR_COLOR
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


def code_span(text: str) -> str:
    """Wrap user-supplied text in a code span that backticks cannot break."""
    longest = run = 0
    for char in text:
        run = run + 1 if char == "`" else 0
        longest = max(longest, run)
    if longest == 0:
        return f"`{text}`"
    fence = "`" * (longest + 1)
    # CommonMark trims one padding space from multi-backtick spans.
    return f"{fence} {text} {fence}"


async def respond(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    color: int | None = None,
) -> None:
    embed = embed or discord.Embed(description=safe_text(content) or "", color=color)
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
    color: int | None = None,
) -> discord.Message:
    embed = embed or discord.Embed(description=safe_text(content) or "", color=color)
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


async def respond_error(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    ephemeral: bool = True,
) -> None:
    await respond(interaction, content, ephemeral=ephemeral, color=ERROR_COLOR)


async def send_error(
    message: discord.Message, content: str | None = None
) -> discord.Message:
    return await send_reply(message, content, color=ERROR_COLOR)


def emoji_key(raw: str) -> str:
    """Canonical stored/compared form of an emoji string."""
    return str(discord.PartialEmoji.from_str(raw))


_KEYCAP_BASES = frozenset("0123456789#*")


def is_emoji(raw: str) -> bool:
    """Best-effort emoji check; no Unicode emoji table is bundled."""
    text = raw.strip()
    if not text:
        return False
    if discord.PartialEmoji.from_str(text).id is not None:
        return True
    if len(text) in (2, 3) and text[-1] == "\u20e3":
        return text[0] in _KEYCAP_BASES and text[1:-1] in ("", "\ufe0f")
    has_symbol = False
    for index, char in enumerate(text):
        code = ord(char)
        if char == "\u200d" or 0xE0020 <= code <= 0xE007F:
            continue  # ZWJ sequence or flag tag characters
        category = unicodedata.category(char)
        if category in {"Mn", "Me", "Sk"}:
            continue  # variation selectors, keycap, skin tone
        if category == "So" or (
            category == "Sm" and text[index + 1 : index + 2] == "\ufe0f"
        ):
            has_symbol = True
            continue
        return False
    return has_symbol


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
    q = code_span(f"{safe_prefix}q")
    embed = discord.Embed(
        title="Lequ help",
        description="Store and retrieve quotes. The bot supports both text and slash commands, as well as message app actions (right-click a message > Apps > Add Quote).",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Quotes",
        value=(
            f"{q} — random quote\n"
            f"{q} <id> — show that quote\n"
            f"{q} <user> — random quote from a user\n"
            f"{q} all — quote stats\n"
            f"{q} all <user> / {q} <user> all — list quotes\n"
            f"{q} <user> <text> — add a quote\n"
            f"{q} as a reply — quote the replied message\n"
            f"{code_span(f'{safe_prefix}quote')} — alias for {q}\n"
            "`<user>` — mention, name, or alias (numeric ID when listing or adding)"
        ),
        inline=False,
    )
    embed.add_field(
        name="Slash commands",
        value=(
            "`/add [member] [name] [text]` — add a quote\n"
            "`/quote [id]` — show a quote (random if no id)\n"
            "`/quotes [user] [ephemeral]` — list a user's quotes\n"
            "`/search <query>` — search quotes\n"
            "`/favorites list|add|remove` — manage your favorites\n"
            "`/report <id>` — report a quote for deletion\n"
            "`/help` — show this page"
        ),
        inline=False,
    )
    embed.add_field(
        name="Aliases",
        value=(
            "`/alias add <name> <alias>` — add *(Manage Server)*\n"
            "`/alias remove <alias>` — remove *(Manage Server)*\n"
            "`/alias list <name>` — list aliases\n"
            "-# Aliases give a named user extra names: Given the alias 'albert' for the name 'einstein', quotes added as `albert` "
            "all count for `einstein`."
        ),
        inline=False,
    )
    embed.add_field(
        name="Admin (Manage Server)",
        value=(
            f"`/admin prefix [{safe_prefix}]` — change the prefix\n"
            "`/admin max-quote-length [value]` — quote length limit\n"
            "`/admin emote add|remove|list` — quote reaction emojis\n"
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
            await respond_error(interaction, "This menu isn't for you.")
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
