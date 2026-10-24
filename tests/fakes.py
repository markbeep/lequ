from dataclasses import dataclass
from itertools import count
from typing import cast, override

import aiohttp
import discord
from discord.ext import commands

from lequ import LequBot


class FakeAsset:
    url: str

    def __init__(self, url: str) -> None:
        self.url = url


class FakeUser:
    id: int
    display_name: str
    name: str
    bot: bool

    def __init__(self, user_id: int, name: str = "user", *, bot: bool = False) -> None:
        self.id = user_id
        self.display_name = name
        self.name = name
        self.bot = bot

    @property
    def display_avatar(self) -> FakeAsset:
        return FakeAsset(f"https://cdn.discordapp.com/avatars/{self.id}.png")

    @property
    def guild_permissions(self) -> discord.Permissions:
        return discord.Permissions(manage_guild=True)


class FakeGuild:
    id: int
    members: dict[int, FakeUser]

    def __init__(self, guild_id: int = 1) -> None:
        self.id = guild_id
        self.members = {}

    def get_member(self, user_id: int) -> FakeUser | None:
        return self.members.get(user_id)

    async def fetch_member(self, user_id: int) -> FakeUser:
        return self.members[user_id]


@dataclass
class SentMessage:
    content: str | None
    embed: discord.Embed | None
    view: discord.ui.View | None
    ephemeral: bool = False
    allowed_mentions: discord.AllowedMentions | None = None


class FakeResponse:
    messages: list[SentMessage]
    modals: list[discord.ui.Modal]
    edits: list[tuple[str | None, discord.Embed | None]]
    deferred: bool
    _done: bool

    def __init__(self) -> None:
        self.messages = []
        self.modals = []
        self.edits = []
        self.deferred = False
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def send_message(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        ephemeral: bool = False,
        allowed_mentions: discord.AllowedMentions | None = None,
    ) -> None:
        self.messages.append(
            SentMessage(content, embed, view, ephemeral, allowed_mentions)
        )
        self._done = True

    async def send_modal(self, modal: discord.ui.Modal) -> None:
        self.modals.append(modal)
        self._done = True

    async def edit_message(
        self,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        del view
        self.edits.append((content, embed))
        self._done = True

    async def defer(self) -> None:
        self.deferred = True
        self._done = True


class FakeInteraction:
    user: FakeUser
    guild_id: int
    response: FakeResponse
    _original: "FakeMessage"

    def __init__(self, user: FakeUser | None = None, guild_id: int = 1) -> None:
        self.user = user or FakeUser(42, "Tester")
        self.guild_id = guild_id
        self.response = FakeResponse()
        self._original = FakeMessage("", self.user, FakeGuild(guild_id))

    async def original_response(self) -> "FakeMessage":
        return self._original


class FakeHTTPResponse:
    status: int
    reason: str

    def __init__(self) -> None:
        self.status = 404
        self.reason = "Not Found"


class FakeNotFound(discord.NotFound):
    def __init__(self) -> None:
        response = cast("aiohttp.ClientResponse", cast(object, FakeHTTPResponse()))
        super().__init__(response, "missing")


class FakeChannel(discord.abc.Messageable):
    id: int
    messages: dict[int, "FakeMessage"]

    def __init__(self, channel_id: int = 7) -> None:
        self.id = channel_id
        self.messages = {}

    @override
    async def fetch_message(self, message_id: int) -> discord.Message:
        if message_id not in self.messages:
            raise FakeNotFound
        return cast(discord.Message, cast(object, self.messages[message_id]))


class FakeReference:
    message_id: int
    cached_message: "FakeMessage | None"

    def __init__(
        self, message_id: int, cached_message: "FakeMessage | None" = None
    ) -> None:
        self.message_id = message_id
        self.cached_message = cached_message


_ids = count(1000)


class FakeMessage:
    id: int
    content: str
    author: FakeUser
    guild: FakeGuild
    channel: FakeChannel
    reference: FakeReference | None
    mentions: list[FakeUser]
    replies: list[SentMessage]
    reactions: list[str]
    deleted: bool

    def __init__(
        self,
        content: str,
        author: FakeUser,
        guild: FakeGuild,
        *,
        channel: FakeChannel | None = None,
        reference: FakeReference | None = None,
        mentions: tuple[FakeUser, ...] = (),
        message_id: int | None = None,
    ) -> None:
        self.id = message_id if message_id is not None else next(_ids)
        self.content = content
        self.author = author
        self.guild = guild
        self.channel = channel or FakeChannel()
        self.reference = reference
        self.mentions = list(mentions)
        self.replies = []
        self.reactions = []
        self.deleted = False

    async def reply(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
        mention_author: bool = True,
        allowed_mentions: discord.AllowedMentions | None = None,
    ) -> "FakeMessage":
        del mention_author
        self.replies.append(SentMessage(content, embed, view, False, allowed_mentions))
        return self

    async def add_reaction(self, emoji: str) -> None:
        self.reactions.append(str(emoji))

    async def delete(self) -> None:
        self.deleted = True


class FakeContext:
    message: FakeMessage

    def __init__(self, message: FakeMessage) -> None:
        self.message = message

    @property
    def guild(self) -> FakeGuild:
        return self.message.guild

    @property
    def author(self) -> FakeUser:
        return self.message.author


class _FakePayload:
    guild_id: int
    channel_id: int
    message_id: int
    user_id: int
    emoji: discord.PartialEmoji
    member: FakeUser | None

    def __init__(
        self,
        *,
        guild_id: int = 1,
        channel_id: int = 7,
        message_id: int = 1,
        user_id: int = 42,
        emoji: discord.PartialEmoji | None = None,
        member: FakeUser | None = None,
    ) -> None:
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.user_id = user_id
        self.emoji = emoji or discord.PartialEmoji(name="AddQuote")
        self.member = member


def FakePayload(
    *,
    guild_id: int = 1,
    channel_id: int = 7,
    message_id: int = 1,
    user_id: int = 42,
    emoji: discord.PartialEmoji | None = None,
    member: FakeUser | None = None,
) -> discord.RawReactionActionEvent:
    return cast(
        discord.RawReactionActionEvent,
        cast(
            object,
            _FakePayload(
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
                user_id=user_id,
                emoji=emoji,
                member=member,
            ),
        ),
    )


class FakeBot:
    guilds: dict[int, FakeGuild]
    channels: dict[int, FakeChannel]
    fetches: int
    fail_fetch: bool
    latency: float

    def __init__(self, *, fail_fetch: bool = False) -> None:
        self.guilds = {}
        self.channels = {}
        self.fetches = 0
        self.fail_fetch = fail_fetch
        self.latency = 0.123

    def get_guild(self, guild_id: int) -> FakeGuild | None:
        return self.guilds.get(guild_id)

    def get_channel(self, channel_id: int) -> FakeChannel | None:
        return self.channels.get(channel_id)

    def get_user(self, _user_id: int) -> discord.User | None:
        return None

    async def fetch_channel(self, channel_id: int) -> FakeChannel:
        return self.channels[channel_id]

    async def fetch_user(self, user_id: int) -> discord.User:
        self.fetches += 1
        if self.fail_fetch:
            raise AssertionError("discord user fetch should not happen")
        return cast(discord.User, cast(object, FakeUser(user_id, f"Fetched{user_id}")))


def as_bot(fake: FakeBot) -> LequBot:
    return cast(LequBot, cast(object, fake))


def as_message(fake: FakeMessage) -> discord.Message:
    return cast(discord.Message, cast(object, fake))


def as_interaction(fake: FakeInteraction) -> discord.Interaction[discord.Client]:
    return cast(discord.Interaction[discord.Client], cast(object, fake))


def as_context(fake: FakeContext) -> commands.Context[LequBot]:
    return cast(commands.Context[LequBot], cast(object, fake))
