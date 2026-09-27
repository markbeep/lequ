import time
from typing import final

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import INTEGER, Column, Field, SQLModel


class BaseModel(SQLModel):
    pass


class User(BaseModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_type: str = Field(index=True)

    __mapper_args__: dict[str, str] = {
        "polymorphic_on": "user_type",
        "polymorphic_identity": "user",
    }


@final
class DiscordUser(User):
    discord_id: int = Field(sa_column_kwargs={"nullable": True}, index=True)

    __mapper_args__ = {"polymorphic_identity": "discord"}


@final
class NamedUser(User):
    name: int = Field(sa_column_kwargs={"nullable": True})

    __mapper_args__ = {"polymorphic_identity": "named"}


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
        default_factory=lambda: int(time.time()),
        sa_column=Column(INTEGER, nullable=False),
    )

    async def flatten(self, session: AsyncSession) -> dict[str, object]:
        user = await session.get_one(User, self.author)
        adder = await session.get_one(User, self.added_by)

        def get_user_dict(user: User) -> dict[str, str] | None:
            match user:
                case NamedUser():
                    return user.model_dump()
                case DiscordUser():
                    return user.model_dump()
                case _:
                    raise ValueError(f"Unknown user type: {type(user)}")

        json_author = get_user_dict(user)
        json_adder = get_user_dict(adder)

        return {
            "id": self.id,
            "text": self.text,
            "author": json_author,
            "added_by": json_adder,
            "guild_id": self.guild_id,
            "created_at": self.created_at,
        }
