__all__ = ("LeafBot",)

from discord.ext import commands
import discord
import asyncpg

intents = discord.Intents.default()
intents.message_content = True


class LeafBot(commands.Bot):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.database = None

        super().__init__(
            intents=intents,
            command_prefix=commands.when_mentioned,
            case_insenstiive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False),
        )

    async def setup_hook(self) -> None:
        for extension in self.config["extensions"]:
            await self.load_extension(extension)

        self.database = await asyncpg.connect(self.config["database"]["connection_uri"])

    @tasks.loop(minutes=1.0)
    async def update_activity(self) -> None:
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} server"
                + ("s" if len(self.guilds) != 1 else ""),
            )
        )

    async def on_ready(self) -> None:
        self.update_activity.start()

    async def close(self) -> None:
        if self.database:
            await self.database.close()

        await super().close()

    async def try_user(self, id: int, /) -> discord.User:
        return self.get_user(id) or await self.fetch_user(id)

    async def try_member(self, id: int, /, *, guild: discord.Guild) -> discord.Member:
        return guild.get_member(id) or await guild.fetch_member(id)
