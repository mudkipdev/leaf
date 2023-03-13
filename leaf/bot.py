__all__ = ("LeafBot",)

from discord.ext import commands
import discord


class LeafBot(commands.Bot):
    async def __init__(self):
        super().__init__(
            intents=discord.Intents.default(),
            command_prefix=commands.when_mentioned,
            case_insenstiive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False),
        )
