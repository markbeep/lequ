from typing import TYPE_CHECKING, final, override

import discord
from discord import app_commands
from discord.ext import commands

from .. import queries
from ..db import get_session
from ..models import Quote, Report, User
from ..ui import ActionButton, emoji_key

if TYPE_CHECKING:
    from .. import LequBot

QUOTE_PREVIEW_LENGTH = 500


@final
class ReportsView(discord.ui.View):
    def __init__(
        self,
        entries: list[tuple[Report, Quote, User]],
        guild_id: int,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.entries: list[tuple[Report, Quote, User]] = entries
        self.guild_id: int = guild_id
        self.index: int = 0
        self.message: discord.Message | None = None
        self.first_button = ActionButton(
            "⏮", discord.ButtonStyle.secondary, self._first, row=0
        )
        self.prev_button = ActionButton(
            "◀", discord.ButtonStyle.secondary, self._prev, row=0
        )
        self.next_button = ActionButton(
            "▶", discord.ButtonStyle.secondary, self._next, row=0
        )
        self.last_button = ActionButton(
            "⏭", discord.ButtonStyle.secondary, self._last, row=0
        )
        self.delete_button = ActionButton(
            "Delete quote", discord.ButtonStyle.danger, self._delete, row=1
        )
        self.dismiss_button = ActionButton(
            "Dismiss", discord.ButtonStyle.secondary, self._dismiss, row=1
        )
        self.close_button = ActionButton(
            "✖", discord.ButtonStyle.danger, self._close, row=1
        )
        self.nav_buttons: list[ActionButton] = [
            self.first_button,
            self.prev_button,
            self.next_button,
            self.last_button,
        ]
        self.action_buttons: list[ActionButton] = [
            self.delete_button,
            self.dismiss_button,
            self.close_button,
        ]
        for button in [*self.nav_buttons, *self.action_buttons]:
            self.add_item(button)
        self._sync_nav()

    def embed(self) -> discord.Embed:
        report, quote, reporter = self.entries[self.index]
        embed = discord.Embed(title=f"Quote {quote.id}", color=0x00003F)
        embed.add_field(
            name="Reported by", value=f"<@{reporter.discord_id}>", inline=False
        )
        embed.add_field(
            name="Quote", value=quote.text[:QUOTE_PREVIEW_LENGTH], inline=False
        )
        embed.add_field(
            name="Reason", value=report.reason or "*No reason given.*", inline=False
        )
        embed.set_footer(text=f"Page {self.index + 1}/{len(self.entries)}")
        return embed

    async def _check(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        if (
            not isinstance(user, discord.Member)
            or not user.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "You need the Manage Server permission.", ephemeral=True
            )
            return False
        return True

    def _sync_nav(self) -> None:
        at_start = self.index == 0
        at_end = self.index == len(self.entries) - 1
        self.first_button.disabled = at_start
        self.prev_button.disabled = at_start
        self.next_button.disabled = at_end
        self.last_button.disabled = at_end

    async def _show(self, interaction: discord.Interaction, index: int) -> None:
        self.index = index
        self._sync_nav()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _first(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, 0)

    async def _prev(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, max(self.index - 1, 0))

    async def _next(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, min(self.index + 1, len(self.entries) - 1))

    async def _last(self, interaction: discord.Interaction) -> None:
        if await self._check(interaction):
            await self._show(interaction, len(self.entries) - 1)

    async def _drop_current(self, interaction: discord.Interaction) -> None:
        self.entries.pop(self.index)
        if not self.entries:
            self.stop()
            await interaction.response.edit_message(
                content="There are no outstanding reports.", embed=None, view=None
            )
            return
        self.index = min(self.index, len(self.entries) - 1)
        self._sync_nav()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def _delete(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        _, quote, _ = self.entries[self.index]
        async with get_session() as session:
            await queries.delete_quote(session, queries.row_pk(quote), self.guild_id)
        await self._drop_current(interaction)

    async def _dismiss(self, interaction: discord.Interaction) -> None:
        if not await self._check(interaction):
            return
        _, quote, _ = self.entries[self.index]
        async with get_session() as session:
            await queries.delete_report(session, queries.row_pk(quote))
        await self._drop_current(interaction)

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
class AdminCog(commands.Cog):
    def __init__(self, bot: LequBot) -> None:
        self.bot: LequBot = bot

    config = app_commands.Group(
        name="config",
        description="Configure the quote bot",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )
    emojis = app_commands.Group(
        name="emojis",
        description="Quote emojis",
        parent=config,
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @config.command(name="prefix", description="Set the command prefix")
    @app_commands.describe(value="New prefix; leave empty to reset to `$`")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def config_prefix(
        self, interaction: discord.Interaction, value: str | None = None
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        if value is not None and (
            not 1 <= len(value) <= 10 or any(c.isspace() for c in value)
        ):
            await interaction.response.send_message(
                "The prefix must be 1 to 10 characters without whitespace.",
                ephemeral=True,
            )
            return
        async with get_session() as session:
            stored = await queries.set_prefix(session, interaction.guild_id, value)
        if value is None:
            await interaction.response.send_message(
                "Prefix reset to `$`.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Prefix set to `{stored}`.", ephemeral=True
            )

    @emojis.command(name="add", description="Allow an emoji to add quotes")
    @app_commands.describe(emote="The emoji to allow")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def emojis_add(self, interaction: discord.Interaction, emote: str) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        partial = discord.PartialEmoji.from_str(emote)
        if partial.id is None and not partial.is_unicode_emoji():
            await interaction.response.send_message(
                "That is not a valid emoji.", ephemeral=True
            )
            return
        async with get_session() as session:
            added = await queries.add_emoji(
                session, interaction.guild_id, emoji_key(emote)
            )
        if added:
            await interaction.response.send_message("Added.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "That emoji is already configured.", ephemeral=True
            )

    @emojis.command(name="remove", description="Disallow an emoji from adding quotes")
    @app_commands.describe(emote="The emoji to disallow")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def emojis_remove(self, interaction: discord.Interaction, emote: str) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            removed = await queries.remove_emoji(
                session, interaction.guild_id, emoji_key(emote)
            )
        if removed:
            await interaction.response.send_message("Removed.", ephemeral=True)
        else:
            await interaction.response.send_message(
                "That emoji is not configured.", ephemeral=True
            )

    @emojis.command(name="list", description="List the quote emojis for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def emojis_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            configured = await queries.get_emojis(session, interaction.guild_id)
        if not configured:
            await interaction.response.send_message(
                "No emojis configured. The custom emoji named 'AddQuote' is used by default.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("\n".join(configured), ephemeral=True)

    @app_commands.command(name="reports", description="View outstanding quote reports")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def reports(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return
        async with get_session() as session:
            entries = await queries.get_reports(session, interaction.guild_id)
        if not entries:
            await interaction.response.send_message(
                "There are no outstanding reports.", ephemeral=True
            )
            return
        view = ReportsView(entries, interaction.guild_id)
        await interaction.response.send_message(
            embed=view.embed(), view=view, ephemeral=True
        )
        view.message = await interaction.original_response()


async def setup(bot: LequBot) -> None:
    await bot.add_cog(AdminCog(bot))
