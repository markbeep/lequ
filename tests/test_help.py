from tests.commands import (
    command,
    dispatch_prefix,
    invoke,
    invoke_prefix,
    prefix_command,
)
from tests.conftest import reset_db
from tests.fakes import (
    FakeBot,
    FakeGuild,
    FakeInteraction,
    FakeMessage,
    FakeUser,
    as_bot,
)
from tests.helpers import seed_base
from lequ import LequBot
from lequ.cogs.quote import QuoteCog
from lequ.ui import EMBED_COLOR


async def test_prefix_commands_resolve_on_real_bot() -> None:
    bot = LequBot()
    await bot.add_cog(QuoteCog(bot))
    assert bot.get_command("q") is not None
    assert bot.get_command("quote") is not None
    assert bot.get_command("help") is not None


async def test_prefix_commands_are_registered() -> None:
    cog = QuoteCog(as_bot(FakeBot()))
    quote = prefix_command(cog, "q")
    assert "quote" in quote.aliases
    prefix_command(cog, "help")


async def test_quote_alias_dispatches_to_q() -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    message = FakeMessage("$quote all alice", FakeUser(42, "Tester"), FakeGuild())
    await dispatch_prefix(cog, message)
    assert message.replies
    assert message.replies[0].embed is not None


async def test_prefix_help_page() -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    message = FakeMessage("$help", FakeUser(42, "Tester"), FakeGuild())
    await invoke_prefix(cog, message, name="help")
    embed = message.replies[0].embed
    assert embed is not None
    assert embed.title == "Lequ help"
    assert embed.color is not None and embed.color.value == EMBED_COLOR
    names = [field.name for field in embed.fields]
    assert "Quotes" in names
    assert "Aliases" in names
    assert "Admin (Manage Server)" in names


async def test_slash_help_page() -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    await invoke(command(cog, "help"), cog, interaction)
    embed = interaction.response.messages[0].embed
    assert embed is not None
    assert embed.title == "Lequ help"
    assert len(embed.fields) == 3
