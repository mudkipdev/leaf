from bot import LeafBot
from discord.ext import commands
from discord import app_commands
import discord

from typing import Optional, Literal


class ModerationCog(commands.Cog, name="Moderation"):
    def __init__(self, bot: LeafBot) -> None:
        self.bot = bot

    @app_commands.describe(
        member="The member to kick.", reason="The reason for kicking the member."
    )
    @app_commands.command(description="Kicks a member from the server.")
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        if member == self.bot.user:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="I cannot kick myself.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=True,
            )
        elif member == interaction.user:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You cannot kick yourself.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=True,
            )

        await member.kick(reason=reason)
        await self.bot.database.execute(
            """
            INSERT INTO infractions(guild_id, member_id, moderator_id, type, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, (NOW() AT TIME ZONE 'utc'));
            """,
            interaction.guild.id,
            member.id,
            interaction.user.id,
            "kick",
            reason,
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{member.mention} has been kicked.",
                color=discord.Color.dark_embed(),
            ),
            ephemeral=True,
        )


async def setup(bot: LeafBot) -> None:
    await bot.add_cog(ModerationCog(bot))
