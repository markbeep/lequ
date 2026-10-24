from typing import cast

from hypothesis import given, settings
from hypothesis import strategies as st

from lequ.cogs.quote import QuoteCog, quote_search_autocomplete
from lequ.ui import QuoteModal
from tests.commands import command, group, invoke, subcommand
from tests.conftest import reset_db
from tests.fakes import FakeBot, FakeInteraction, FakeUser, as_bot, as_interaction
from tests.helpers import seed_base


def assert_single_response(interaction: FakeInteraction) -> None:
    total = len(interaction.response.messages) + len(interaction.response.modals)
    assert total == 1, interaction.response.messages
    if interaction.response.messages:
        message = interaction.response.messages[0]
        assert message.content is None
        assert message.embed is not None


@settings(max_examples=40, deadline=None)
@given(quote_id=st.one_of(st.none(), st.integers(-(10**6), 10**6)))
async def test_quote_command_always_responds(quote_id: int | None) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    await invoke(command(cog, "quote"), cog, interaction, quote_id)
    assert_single_response(interaction)


@settings(max_examples=30, deadline=None)
@given(
    user_id=st.one_of(st.none(), st.integers(-(10**6), 10**6)),
    ephemeral=st.booleans(),
)
async def test_quotes_command_always_responds(
    user_id: int | None, ephemeral: bool
) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    user = FakeUser(user_id) if user_id is not None else None
    await invoke(command(cog, "quotes"), cog, interaction, user, ephemeral)
    assert_single_response(interaction)


async def test_quotes_command_lists_existing_quotes() -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    await invoke(command(cog, "quotes"), cog, interaction, FakeUser(123), False)
    assert_single_response(interaction)
    assert interaction.response.messages[0].embed is not None
    assert interaction.response.messages[0].content is None


@settings(max_examples=40, deadline=None)
@given(query=st.text(max_size=40))
async def test_search_command_always_responds(query: str) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    await invoke(command(cog, "search"), cog, interaction, query)
    assert_single_response(interaction)


@settings(max_examples=30, deadline=None)
@given(current=st.text(max_size=40))
async def test_search_autocomplete_never_raises(current: str) -> None:
    await reset_db()
    await seed_base()
    interaction = FakeInteraction()
    choices = await quote_search_autocomplete(as_interaction(interaction), current)
    assert isinstance(choices, list)
    for choice in choices:
        assert choice.name
        assert choice.value


@settings(max_examples=30, deadline=None)
@given(quote_id=st.integers(-(10**6), 10**6))
async def test_favorites_commands_always_respond(quote_id: int) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    favorites = group(cog, "favorites")
    for name in ("add", "remove"):
        interaction = FakeInteraction()
        await invoke(subcommand(favorites, name), cog, interaction, quote_id)
        assert_single_response(interaction)


async def test_favorites_list_responds() -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    await invoke(subcommand(group(cog, "favorites"), "list"), cog, interaction)
    assert_single_response(interaction)


@settings(max_examples=30, deadline=None)
@given(quote_id=st.integers(-(10**6), 10**6))
async def test_report_command_always_responds(quote_id: int) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    await invoke(command(cog, "report"), cog, interaction, quote_id)
    assert_single_response(interaction)


@settings(max_examples=40, deadline=None)
@given(
    member_id=st.one_of(st.none(), st.integers(-(10**6), 10**6)),
    name=st.one_of(st.none(), st.text(max_size=20)),
    text=st.one_of(st.none(), st.text(max_size=60)),
)
async def test_add_command_always_responds(
    member_id: int | None, name: str | None, text: str | None
) -> None:
    await reset_db()
    await seed_base()
    cog = QuoteCog(as_bot(FakeBot()))
    interaction = FakeInteraction()
    member = FakeUser(member_id) if member_id is not None else None
    await invoke(
        command(cog, "add"),
        cog,
        interaction,
        member=member,
        name=name,
        text=text,
    )
    assert_single_response(interaction)
    if interaction.response.modals:
        modal = cast(QuoteModal, interaction.response.modals[0])
        if modal.text_input is not None:
            max_length = modal.text_input.max_length
            assert max_length is not None
            assert 1 <= max_length <= 4000
