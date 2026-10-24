import discord
from hypothesis import given, settings
from hypothesis import strategies as st

from lequ import queries
from lequ.cogs.admin import ReportsView
from lequ.db import get_session
from lequ.ui import FavoriteView, Paginator
from tests.conftest import reset_db
from tests.fakes import (
    FakeGuild,
    FakeInteraction,
    FakeMessage,
    FakeUser,
    as_interaction,
    as_message,
)
from tests.helpers import seed_base, sent_text


@settings(max_examples=30, deadline=None)
@given(quote_id=st.integers(-(10**6), 10**6))
async def test_favorite_button_always_responds(quote_id: int) -> None:
    await reset_db()
    await seed_base()
    view = FavoriteView(quote_id)
    interaction = FakeInteraction()
    await view.toggle(as_interaction(interaction))
    assert len(interaction.response.messages) == 1
    assert sent_text(interaction.response.messages[0]) in {
        "Added to your favorites.",
        "Removed from your favorites.",
    }


@settings(max_examples=30, deadline=None)
@given(
    owner_id=st.integers(1, 10**6),
    clicker_id=st.integers(1, 10**6),
    button=st.sampled_from(["first", "prev", "next", "last"]),
)
async def test_paginator_buttons_always_respond(
    owner_id: int, clicker_id: int, button: str
) -> None:
    await reset_db()
    pages = [
        discord.Embed(title="page 1"),
        discord.Embed(title="page 2"),
    ]
    view = Paginator(pages, owner_id)
    interaction = FakeInteraction(FakeUser(clicker_id))
    buttons = {
        "first": view.first_button,
        "prev": view.prev_button,
        "next": view.next_button,
        "last": view.last_button,
    }
    await buttons[button].callback(as_interaction(interaction))
    total = len(interaction.response.messages) + len(interaction.response.edits)
    assert total == 1
    if clicker_id != owner_id:
        assert sent_text(interaction.response.messages[0]) == "This menu isn't for you."


async def test_reports_view_rejects_non_members() -> None:
    await reset_db()
    seeded = await seed_base()
    async with get_session() as session:
        quote = await queries.get_quote(session, 1, 1)
        assert quote is not None
        await queries.create_report(session, quote.id, seeded.tester_id, "bad quote")
        entries = await queries.get_reports(session, 1)
    view = ReportsView(entries, 1)
    interaction = FakeInteraction(FakeUser(999))
    await view.delete_button.callback(as_interaction(interaction))
    assert sent_text(interaction.response.messages[0]) == (
        "You need the Manage Server permission."
    )


async def test_paginator_close_deletes_owned_message() -> None:
    await reset_db()
    view = Paginator([discord.Embed(title="page")], 42)
    message = FakeMessage("", FakeUser(42), FakeGuild())
    view.message = as_message(message)
    interaction = FakeInteraction(FakeUser(42))
    await view.close_button.callback(as_interaction(interaction))
    assert interaction.response.deferred
    assert message.deleted
