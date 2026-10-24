"""Coded permission matrix: role x command x context. No LLM here."""

import discord
import pytest

from lequ import queries
from lequ.cogs.admin import ReportsView
from lequ.constants import ERROR_COLOR
from lequ.db import get_session
from tests.fakes import FakeInteraction
from tests.helpers import seed_base, sent_text
from tests.world import ADMIN, NO_PERMISSIONS, World

DENIED = "You need the Manage Server permission."
DM_DENIED = "This command can only be used in a server."

type Args = dict[str, object]

GATED_COMMANDS: list[tuple[str, Args]] = [
    ("admin.prefix", {"value": "!"}),
    ("admin.max-quote-length", {"value": 100}),
    ("admin.emote.add", {"emote": "👍"}),
    ("admin.emote.remove", {"emote": "👍"}),
    ("admin.emote.list", {}),
    ("admin.reports", {}),
    ("alias.add", {"name": "alice", "alias": "bobby"}),
    ("alias.remove", {"alias": "bobby"}),
]


def only_text(interaction: FakeInteraction) -> str:
    assert len(interaction.response.messages) == 1
    return sent_text(interaction.response.messages[0])


async def total_quotes(world: World) -> int:
    async with get_session() as session:
        total, _, _ = await queries.get_quote_stats(session, world.guild_id)
    return total


@pytest.mark.parametrize(("command", "args"), GATED_COMMANDS)
async def test_gated_commands_deny_plain_member(
    world: World, command: str, args: Args
) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    interaction = await world.slash(alice, command, args)
    assert only_text(interaction) == DENIED
    assert interaction.response.messages[0].embed is not None
    assert interaction.response.messages[0].embed.color is not None
    assert interaction.response.messages[0].embed.color.value == ERROR_COLOR


@pytest.mark.parametrize(("command", "args"), GATED_COMMANDS)
async def test_gated_commands_allow_manage_server(
    world: World, command: str, args: Args
) -> None:
    admin = world.member(2, "admin", permissions=ADMIN)
    interaction = await world.slash(admin, command, args)
    assert only_text(interaction) != DENIED


async def test_denied_prefix_change_leaves_settings_untouched(world: World) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    await world.slash(alice, "admin.prefix", {"value": "!"})
    assert await queries.cached_prefix(world.guild_id) == "$"


async def test_administrator_bit_grants_admin_commands(world: World) -> None:
    owner = world.member(2, "owner", permissions=discord.Permissions.all())
    interaction = await world.slash(owner, "admin.prefix", {"value": "!"})
    assert "Prefix set to" in only_text(interaction)


@pytest.mark.parametrize(
    ("command", "args"),
    [("admin.prefix", {"value": "!"}), ("admin.reports", {})],
)
async def test_admin_commands_reject_dm(world: World, command: str, args: Args) -> None:
    admin = world.member(2, "admin", permissions=ADMIN)
    interaction = await world.slash(admin, command, args, dm=True)
    assert only_text(interaction) == DM_DENIED


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("quote", {"quote_id": 1}),
        ("favorites.list", {}),
        ("report", {"quote_id": 1}),
        ("search", {"query": "anything"}),
        ("alias.list", {"name": "alice"}),
        ("help", {}),
    ],
)
async def test_normal_commands_open_to_plain_members(
    world: World, command: str, args: Args
) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    interaction = await world.slash(alice, command, args)
    assert only_text(interaction) != DENIED


async def test_reports_buttons_reject_plain_member(world: World) -> None:
    seeded = await seed_base()
    async with get_session() as session:
        quote = (await queries.get_quotes_by_author(session, seeded.alice_id, 1))[0]
        await queries.create_report(session, quote.id, seeded.tester_id, "spam")

    admin = world.member(2, "admin", permissions=ADMIN)
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    interaction = await world.slash(admin, "admin.reports")
    view = interaction.response.messages[0].view
    assert isinstance(view, ReportsView)

    denied = await world.click(alice, view.delete_button)
    assert only_text(denied) == DENIED
    async with get_session() as session:
        assert await queries.get_quote(session, quote.id, 1) is not None

    await world.click(admin, view.delete_button)
    async with get_session() as session:
        assert await queries.get_quote(session, quote.id, 1) is None


async def test_reports_buttons_reject_owner_without_permission(world: World) -> None:
    seeded = await seed_base()
    async with get_session() as session:
        quote = (await queries.get_quotes_by_author(session, seeded.alice_id, 1))[0]
        await queries.create_report(session, quote.id, seeded.tester_id, None)

    owner = world.member(3, "owner")
    admin = world.member(2, "admin", permissions=ADMIN)
    interaction = await world.slash(admin, "admin.reports")
    view = interaction.response.messages[0].view
    assert isinstance(view, ReportsView)

    denied = await world.click(owner, view.dismiss_button)
    assert only_text(denied) == DENIED


async def test_reaction_from_bot_is_ignored(world: World) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    lequ = world.member(2, "lequ", bot=True)
    message = world.message("bot reaction quote", alice)
    await world.react(lequ, message)
    assert await total_quotes(world) == 0
    assert message.reactions == []


async def test_reaction_in_news_channel_is_ignored(world: World) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    bob = world.member(2, "bob", permissions=NO_PERMISSIONS)
    news = world.channel_of_type(discord.ChannelType.news)
    message = world.message("news quote", bob, channel=news)
    await world.react(alice, message, channel=news)
    assert await total_quotes(world) == 0


async def test_reaction_from_member_adds_quote(world: World) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    bob = world.member(2, "bob", permissions=NO_PERMISSIONS)
    message = world.message("reaction quote", bob)
    await world.react(alice, message)
    assert message.reactions == ["✅"]
    assert await total_quotes(world) == 1


async def test_prefix_help_works_in_dm(world: World) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    message = await world.say(alice, "$help", dm=True)
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.title == "Lequ help"


async def test_prefix_quote_is_silent_in_dm(world: World) -> None:
    alice = world.member(1, "alice", permissions=NO_PERMISSIONS)
    message = await world.say(alice, "$q", dm=True)
    assert message.replies == []
