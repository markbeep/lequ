import logging
from typing import override

import discord
from discord import app_commands
from discord.ext import commands

from . import queries
from .constants import DEFAULT_PREFIX
from .env import Settings

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True


async def get_prefix(_bot: commands.Bot, message: discord.Message) -> str:
    if message.guild is None:
        return DEFAULT_PREFIX
    return await queries.cached_prefix(message.guild.id)


class LequBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)

    @override
    async def setup_hook(self) -> None:
        logger.info("loading cogs")
        await self.load_extension("lequ.cogs.quote")
        await self.load_extension("lequ.cogs.admin")
        synced = await self.tree.sync()
        logger.info("synced %s application commands", len(synced))


bot = LequBot()


@bot.event
async def on_ready() -> None:
    logger.info("logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else None)


@bot.event
async def on_command_error(
    ctx: commands.Context[LequBot], error: commands.CommandError
) -> None:
    if isinstance(error, commands.CommandNotFound):
        logger.debug("unknown prefix command: %s", ctx.message.content)
        return
    logger.exception("prefix command failed: %s", ctx.command, exc_info=error)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        message = "You need the Manage Server permission."
    elif isinstance(error, app_commands.NoPrivateMessage):
        message = "This command can only be used in a server."
    else:
        logger.exception("application command failed", exc_info=error)
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
    settings = Settings()
    discord.utils.setup_logging(level=logging.INFO)
    logger.info("starting lequ database=%s", settings.db.path)
    token = settings.discord_token
    if token is None:
        raise ValueError("Discord token is not set in the environment variables.")
    bot.run(token)
