import time
from typing import ClassVar

from sqlalchemy import INTEGER, Column, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel


class BaseModel(SQLModel):
    pass


def _now() -> int:
    return int(time.time())


class GuildSettings(BaseModel, table=True):
    guild_id: int = Field(primary_key=True)
    prefix: str = Field(default="$")
    created_at: int = Field(
        default_factory=_now, sa_column=Column(INTEGER, nullable=False)
    )


class GuildEmoji(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    guild_id: int = Field(
        foreign_key="guildsettings.guild_id", ondelete="CASCADE", index=True
    )
    emoji: str
    __table_args__: ClassVar[tuple[UniqueConstraint, ...]] = (
        UniqueConstraint("guild_id", "emoji", name="uq_guildemoji_guild_emoji"),
    )


class User(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_type: str = Field(index=True)  # "discord" | "named"
    discord_id: int | None = Field(default=None, unique=True, index=True)
    name: str | None = Field(default=None, unique=True, index=True)


class Aliases(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    alias: str = Field(unique=True)


class Quote(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    text: str
    author: int = Field(foreign_key="user.id")
    added_by: int = Field(foreign_key="user.id")
    guild_id: int | None = Field(index=True)
    created_at: int = Field(
        default_factory=_now, sa_column=Column(INTEGER, nullable=False)
    )

    async def flatten(self, session: AsyncSession) -> dict[str, object]:
        author = await session.get_one(User, self.author)
        adder = await session.get_one(User, self.added_by)
        return {
            "id": self.id,
            "text": self.text,
            "author": author.model_dump(),
            "added_by": adder.model_dump(),
            "guild_id": self.guild_id,
            "created_at": self.created_at,
        }


class QuotedMessage(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id", ondelete="CASCADE", unique=True)
    guild_id: int = Field(index=True)
    channel_id: int
    message_id: int = Field(unique=True, index=True)


class Report(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    quote_id: int = Field(foreign_key="quote.id", ondelete="CASCADE", unique=True)
    reporter: int = Field(foreign_key="user.id")
    reason: str | None = Field(default=None)
    created_at: int = Field(
        default_factory=_now, sa_column=Column(INTEGER, nullable=False)
    )


class FavoriteQuote(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    quote_id: int = Field(foreign_key="quote.id", ondelete="CASCADE", index=True)
    __table_args__: ClassVar[tuple[UniqueConstraint, ...]] = (
        UniqueConstraint("user_id", "quote_id", name="uq_favoritequote_user_quote"),
    )
