__all__ = ("LeafBot",)

from logging.handlers import RotatingFileHandler

from discord.ext import tasks
import discord
import asyncpg
import logging
from discord.ext import commands
from discord_logging.handler import DiscordHandler

intents = discord.Intents.default()
intents.message_content = True


class LeafBot(commands.Bot):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.database = None
        self.webhook_url = config["logging"]["webhook_url"]
        self.logger = logging.getLogger()

        super().__init__(
            intents=intents,
            command_prefix=commands.when_mentioned,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False),
        )

        self.discord_handler = self.setup_logging(self.webhook_url)

    async def send_guild_stats(self, e, guild):
        e.add_field(name="Name", value=guild.name)
        e.add_field(name="ID", value=guild.id)
        e.add_field(name="Shard ID", value=guild.shard_id or "N/A")
        e.add_field(name="Owner", value=f"{guild.owner} (ID: {guild.owner_id})")

        bots = sum(m.bot for m in guild.members)
        total = guild.member_count
        online = sum(m.status is discord.Status.online for m in guild.members)
        e.add_field(name="Members", value=str(total))
        e.add_field(name="Bots", value=f"{bots} ({bots/total:.2%})")
        e.add_field(name="Online", value=f"{online} ({online/total:.2%})")

        if guild.icon:
            e.set_thumbnail(url=guild.icon_url)

        if guild.me:
            e.timestamp = guild.me.joined_at

        hook = discord.Webhook.from_url(self.webhook_url, client=self)

        await hook.send(embed=e)

    async def setup_hook(self) -> None:
        for extension in self.config["extensions"]:
            await self.load_extension(extension)

        self.database = await asyncpg.connect(self.config["database"]["connection_uri"])

    def setup_logging(self, webhook_url: str):
        max_bytes = 32 * 1024 * 1024  # 32 MiB
        logging.getLogger('discord').setLevel(logging.INFO)
        logging.getLogger('discord.http').setLevel(logging.WARNING)

        handler = RotatingFileHandler(filename='leaf.log', encoding='utf-8', mode='w', maxBytes=max_bytes,
                                      backupCount=5)
        dt_fmt = '%Y-%m-%d %H:%M:%S'
        fmt = logging.Formatter('[{asctime}] [{levelname:<7}] {name}: {message}', dt_fmt, style='{')
        handler.setFormatter(fmt)

        self.logger.addHandler(handler)

        discord_handler = DiscordHandler(
            service_name=self.config["logging"]["bot_name"], webhook_url=webhook_url
        )
        discord_handler.setFormatter(fmt)

        self.logger.setLevel(self.config["logging"]["logging_level"])
        self.logger.addHandler(discord_handler)

        return discord_handler

    @tasks.loop(minutes=1.0)
    async def update_activity(self) -> None:
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} server"
                + ("s" if len(self.guilds) != 1 else ""),
            )
        )

    async def on_guild_join(self, guild):
        e = discord.Embed(colour=0x53DDA4, title="New Guild")
        await self.send_guild_stats(e, guild)

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
