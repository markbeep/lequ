from collections.abc import Awaitable, Callable
from typing import cast

from discord import app_commands
from discord.ext import commands

from tests.fakes import FakeInteraction, as_interaction

type Command = app_commands.Command[commands.Cog, ..., object]
type Callback = Callable[..., Awaitable[object]]


def group(cog: commands.Cog, name: str) -> app_commands.Group:
    for command in cog.get_app_commands():
        if isinstance(command, app_commands.Group) and command.name == name:
            return command
    raise AssertionError(f"group {name!r} not found")


def command(cog: commands.Cog, name: str) -> Command:
    for item in cog.get_app_commands():
        if isinstance(item, app_commands.Command) and item.name == name:
            return item
    raise AssertionError(f"command {name!r} not found")


def subgroup(parent: app_commands.Group, name: str) -> app_commands.Group:
    for item in parent.commands:
        if isinstance(item, app_commands.Group) and item.name == name:
            return item
    raise AssertionError(f"subgroup {name!r} not found")


def subcommand(parent: app_commands.Group, name: str) -> Command:
    for item in parent.commands:
        if isinstance(item, app_commands.Command) and item.name == name:
            return item
    raise AssertionError(f"subcommand {name!r} not found")


async def invoke(
    item: Command,
    cog: commands.Cog,
    interaction: FakeInteraction,
    *args: object,
    **kwargs: object,
) -> None:
    callback = cast(Callback, item.callback)
    await callback(cog, as_interaction(interaction), *args, **kwargs)
