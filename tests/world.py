"""Simulated guild: drive every bot entrypoint the way Discord would.

The LLM actor layer (later) only needs `World` methods; the oracle helpers keep
assertions in code, never in the actor.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Literal, cast, override

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from discord.guild import GuildChannel

from lequ import LequBot, on_app_command_error
from lequ.cogs.admin import AdminCog
from lequ.cogs.quote import QuoteCog
from tests.fakes import (
    FakeBot,
    FakeChannel,
    FakeGuild,
    FakeInteraction,
    FakeMessage,
    FakePayload,
    FakeUser,
    as_interaction,
    as_message,
)

type Callback = Callable[..., Awaitable[object]]
type AppCommand = app_commands.Command[commands.Cog, ..., object]

NO_PERMISSIONS = discord.Permissions.none()
ADMIN = discord.Permissions(manage_guild=True)


class WorldBot(LequBot):
    """Real bot for prefix dispatch; guild, channel and user lookups stay offline."""

    def __init__(self, fake: FakeBot) -> None:
        super().__init__()
        self.fake: FakeBot = fake
        self._fake_user: FakeUser = FakeUser(999, "Lequ", bot=True)

    @property
    @override
    def user(self) -> discord.ClientUser | None:
        return cast("discord.ClientUser | None", cast(object, self._fake_user))

    @override
    def get_guild(self, id: int, /) -> discord.Guild | None:
        return cast("discord.Guild | None", self.fake.get_guild(id))

    @override
    def get_channel(
        self, id: int, /
    ) -> GuildChannel | discord.Thread | discord.abc.PrivateChannel | None:
        return cast(
            "GuildChannel | discord.Thread | discord.abc.PrivateChannel | None",
            self.fake.get_channel(id),
        )

    @override
    def get_user(self, id: int, /) -> discord.User | None:
        return self.fake.get_user(id)

    @override
    async def fetch_user(self, user_id: int, /) -> discord.User:
        return await self.fake.fetch_user(user_id)

    @override
    async def fetch_channel(
        self, channel_id: int, /
    ) -> GuildChannel | discord.abc.PrivateChannel | discord.Thread:
        return cast(
            "GuildChannel | discord.abc.PrivateChannel | discord.Thread",
            await self.fake.fetch_channel(channel_id),
        )


def walk_commands(
    items: Sequence[object], prefix: str = ""
) -> list[tuple[str, AppCommand | app_commands.Group]]:
    found: list[tuple[str, AppCommand | app_commands.Group]] = []
    for item in items:
        if isinstance(item, app_commands.Group):
            group = item
            name = f"{prefix}.{group.name}" if prefix else group.name
            found.append((name, group))
            found.extend(walk_commands(list(group.commands), name))
        elif isinstance(item, app_commands.Command):
            command = cast(AppCommand, item)
            name = f"{prefix}.{command.name}" if prefix else command.name
            found.append((name, command))
    return found


async def check_can_run(
    item: app_commands.Command[commands.Cog, ..., object] | app_commands.Group,
    interaction: FakeInteraction,
) -> None:
    """Apply the guild-only marker and command checks Discord would enforce."""
    current: object = item
    while isinstance(current, (app_commands.Command, app_commands.Group)):
        if getattr(current, "guild_only", False) and interaction.guild_id is None:
            raise app_commands.NoPrivateMessage()
        current = current.parent
    if isinstance(item, app_commands.Command):
        allowed = await item._check_can_run(  # pyright: ignore[reportPrivateUsage]
            cast("discord.Interaction[LequBot]", as_interaction(interaction))
        )
        if not allowed:
            raise app_commands.CheckFailure("check failed")


class World:
    def __init__(self, guild_id: int = 1) -> None:
        self.guild_id: int = guild_id
        self.fake_bot: FakeBot = FakeBot()
        self.guild: FakeGuild = FakeGuild(guild_id)
        self.channel: FakeChannel = FakeChannel(7)
        self.fake_bot.guilds[guild_id] = self.guild
        self.fake_bot.channels[self.channel.id] = self.channel
        self.bot: WorldBot = WorldBot(self.fake_bot)
        self.quote: QuoteCog = QuoteCog(self.bot)
        self.admin: AdminCog = AdminCog(self.bot)
        self.commands: dict[str, tuple[commands.Cog, AppCommand]] = {}

    @classmethod
    async def create(cls, guild_id: int = 1) -> World:
        world = cls(guild_id)
        await world.bot.add_cog(world.quote)
        await world.bot.add_cog(world.admin)
        for cog in (world.quote, world.admin):
            items = cast(
                "list[app_commands.Command[commands.Cog, ..., object] | app_commands.Group]",
                list(cog.get_app_commands()),
            )
            for name, item in walk_commands(items):
                if isinstance(item, app_commands.Command):
                    world.commands[name] = (cog, item)
        return world

    def member(
        self,
        user_id: int,
        name: str,
        *,
        permissions: discord.Permissions | None = None,
        bot: bool = False,
    ) -> FakeUser:
        user = FakeUser(user_id, name, bot=bot, permissions=permissions)
        self.guild.members[user_id] = user
        return user

    def channel_of_type(
        self,
        channel_type: Literal[discord.ChannelType.text, discord.ChannelType.news],
        channel_id: int = 8,
    ) -> FakeChannel:
        channel = FakeChannel(channel_id, channel_type=channel_type)
        self.fake_bot.channels[channel.id] = channel
        return channel

    def message(
        self,
        content: str,
        author: FakeUser,
        *,
        channel: FakeChannel | None = None,
    ) -> FakeMessage:
        channel = channel or self.channel
        message = FakeMessage(content, author, self.guild, channel=channel)
        channel.messages[message.id] = message
        self.fake_bot.channels[channel.id] = channel
        return message

    def interaction(self, user: FakeUser, *, dm: bool = False) -> FakeInteraction:
        return FakeInteraction(user, None if dm else self.guild_id)

    async def slash(
        self,
        user: FakeUser,
        command: str,
        args: dict[str, object] | None = None,
        *,
        dm: bool = False,
    ) -> FakeInteraction:
        cog, item = self.commands[command]
        interaction = self.interaction(user, dm=dm)
        try:
            await check_can_run(item, interaction)
        except app_commands.CheckFailure as exc:
            await on_app_command_error(
                cast("discord.Interaction[LequBot]", as_interaction(interaction)), exc
            )
            return interaction
        callback = cast(Callback, item.callback)
        await callback(cog, as_interaction(interaction), **(args or {}))
        return interaction

    async def say(
        self, user: FakeUser, content: str, *, dm: bool = False
    ) -> FakeMessage:
        message = FakeMessage(
            content, user, None if dm else self.guild, channel=self.channel
        )
        self.channel.messages[message.id] = message
        await self.bot.process_commands(as_message(message))
        return message

    async def react(
        self,
        user: FakeUser,
        message: FakeMessage,
        *,
        emoji: discord.PartialEmoji | None = None,
        reactor: FakeUser | None = None,
        channel: FakeChannel | None = None,
    ) -> FakeMessage:
        channel = channel or message.channel
        channel.messages[message.id] = message
        self.fake_bot.channels[channel.id] = channel
        await self.quote.on_raw_reaction_add(
            FakePayload(
                guild_id=self.guild_id,
                channel_id=channel.id,
                message_id=message.id,
                user_id=user.id,
                emoji=emoji,
                member=reactor if reactor is not None else user,
            )
        )
        return message

    async def click(
        self, user: FakeUser, button: discord.ui.Button[discord.ui.View]
    ) -> FakeInteraction:
        interaction = self.interaction(user)
        await button.callback(as_interaction(interaction))
        return interaction

    async def submit(self, user: FakeUser, modal: discord.ui.Modal) -> FakeInteraction:
        interaction = self.interaction(user)
        await modal.on_submit(as_interaction(interaction))
        return interaction
