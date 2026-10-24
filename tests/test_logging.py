import logging

import pytest

from tests.commands import dispatch_prefix, group, invoke, subcommand
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
from lequ.cogs.admin import AdminCog
from lequ.cogs.quote import QuoteCog


async def test_quote_actions_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    message = FakeMessage("$q alice logged quote", FakeUser(42, "Tester"), FakeGuild())
    with caplog.at_level(logging.INFO):
        await dispatch_prefix(cog, message)
    assert "quote command" in caplog.text
    assert "quote added" in caplog.text
    assert "logged quote" in caplog.text


async def test_admin_changes_are_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    await reset_db()
    cog = AdminCog(as_bot(FakeBot()))
    cmd = subcommand(group(cog, "admin"), "prefix")
    interaction = FakeInteraction()
    with caplog.at_level(logging.INFO):
        await invoke(cmd, cog, interaction, "!")
    assert "prefix updated" in caplog.text
