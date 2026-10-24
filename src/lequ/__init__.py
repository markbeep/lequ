import traceback
from typing import override

import discord
from discord import app_commands
from discord.ext import commands

from . import queries
from .constants import DEFAULT_PREFIX
from .env import Settings

intents = discord.Intents.default()
intents.message_content = True


async def get_prefix(_bot: commands.Bot, message: discord.Message) -> str:
    if message.guild is None:
        return DEFAULT_PREFIX
    return await queries.cached_prefix(message.guild.id)


class LequBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=get_prefix, intents=intents)

    @override
    async def setup_hook(self) -> None:
        await self.load_extension("lequ.cogs.quote")
        await self.load_extension("lequ.cogs.admin")
        await self.tree.sync()


bot = LequBot()


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user}")


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        message = "You need the Manage Server permission."
    elif isinstance(error, app_commands.NoPrivateMessage):
        message = "This command can only be used in a server."
    else:
        traceback.print_exception(type(error), error, error.__traceback__)
        message = "Something went wrong."
    allowed_mentions = discord.AllowedMentions.none()
    embed = discord.Embed(description=message)
    if interaction.response.is_done():
        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=allowed_mentions
        )
    else:
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=allowed_mentions
        )


def main() -> None:
    token = Settings().discord_token
    if token is None:
        raise ValueError("Discord token is not set in the environment variables.")
    bot.run(token)
