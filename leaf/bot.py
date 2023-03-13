__all__ = ("LeafBot",)

from discord.ext import commands
import discord
import asyncpg


class LeafBot(commands.Bot):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.database = None

        super().__init__(
            intents=discord.Intents.default(),
            command_prefix=commands.when_mentioned,
            case_insenstiive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False),
        )

    async def setup_hook(self) -> None:
        for extension in self.config["extensions"]:
            await self.load_extension(extension)

        self.database = await asyncpg.connect(self.config["database"]["connection_uri"])

    async def close(self) -> None:
        if self.database:
            await self.database.close()

        await super().close()
