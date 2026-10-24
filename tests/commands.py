from collections.abc import Awaitable, Callable
from typing import cast

from discord import app_commands
from discord.ext import commands

from tests.fakes import (
    FakeContext,
    FakeInteraction,
    FakeMessage,
    as_context,
    as_interaction,
)

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


def prefix_command(
    cog: commands.Cog, name: str
) -> commands.Command[commands.Cog, ..., object]:
    for item in cog.get_commands():
        if item.name == name:
            return item
    raise AssertionError(f"prefix command {name!r} not found")


async def invoke_prefix(
    cog: commands.Cog,
    message: FakeMessage,
    args: str | None = None,
    *,
    name: str = "q",
) -> None:
    item = prefix_command(cog, name)
    callback = cast(Callback, item.callback)
    context = as_context(FakeContext(message))
    if args is None:
        await callback(cog, context)
    else:
        await callback(cog, context, args=args)


async def dispatch_prefix(
    cog: commands.Cog, message: FakeMessage, prefix: str = "$"
) -> None:
    if message.author.bot:
        return
    words = message.content.split(maxsplit=1)
    if not words:
        return
    if words[0].lower() not in {f"{prefix}q", f"{prefix}quote"}:
        return
    await invoke_prefix(cog, message, words[1] if len(words) > 1 else "")
