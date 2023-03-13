from bot import LeafBot
from utils import Paginator
from discord.ext import commands
from discord import app_commands
import discord

from typing import Optional


@app_commands.guild_only()
class TagsCog(commands.GroupCog, name="Tags", group_name="tags"):
    def __init__(self, bot: LeafBot) -> None:
        self.bot = bot

    @app_commands.describe(starting_page = "The page to start on.")
    @app_commands.command(name = "list", description = "Lists all the tags in the server.")
    async def list_tags(
        self,
        interaction: discord.Interaction,
        starting_page: Optional[int] = 0,
        silent: Optional[bool] = False
    ):
        tags = await self.bot.database.fetch("SELECT * FROM tags WHERE guild_id = $1", interaction.guild.id)
        embeds = []

        if not tags:
            embeds.append(discord.Embed(
                description = "There are no tags in this server.",
                color = discord.Color.dark_embed())
            )
        else:
            chunks = discord.utils.as_chunks(tags, 25)
            for chunk in chunks:
                embeds.append(discord.Embed(
                    description = "\n".join([f"• **{tag['name']}** (Uses: {tag['uses']})" for tag in chunk]),
                    color = discord.Color.dark_embed()
                ))
        
        paginator = Paginator(embeds = embeds, index = starting_page)
        await paginator.start(interaction, ephemeral = silent)

    @app_commands.describe(tag="The name of the tag to view.")
    @app_commands.command(name="view", description="Sends the content of a tag.")
    async def view_tag(
        self,
        interaction: discord.Interaction,
        tag: str,
        silent: Optional[bool] = False
    ) -> None:
        tag = await self.bot.database.fetchrow(
            "SELECT content FROM tags WHERE name = $1 AND guild_id = $2", tag, interaction.guild.id
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                description=tag["content"], color=discord.Color.dark_embed()
            ),
            ephemeral=silent,
        )

    @app_commands.describe(name="The tag of the newly created tag.")
    @app_commands.command(name="create", description="Creates a new tag.")
    async def create_tag(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        await interaction.response.send_message(
            embed=discord.Embed(
                description="Please reply to this message with your new tag content within 5 minutes.",
                color=discord.Color.dark_embed(),
            )
        )
        message = await interaction.original_response()

        def check(message):
            return (
                message.channel == interaction.channel
                and message.author == interaction.user
            )

        message = await self.bot.wait_for("message", timeout=300, check=check)

        await self.bot.database.execute(
            """
            INSERT INTO tags(name, guild_id, owner_id, content, created_at, last_edited_at, uses)
            VALUES ($1, $2, $3, $4, DEFAULT, DEFAULT, DEFAULT);
            """,
            name,
            interaction.guild.id,
            interaction.user.id,
            message.content,
        )
        await message.reply(
            embed=discord.Embed(
                description="Your tag has successfully been created.",
                color=discord.Color.dark_embed(),
            )
        )

    @app_commands.describe(tag="The name of the tag to delete.")
    @app_commands.command(name="delete", description="Deletes a tag from the server.")
    async def delete_tag(
        self,
        interaction: discord.Interaction,
        tag: str,
        silent: Optional[bool] = False
    ) -> None:
        owner_id = await self.bot.database.fetchval(
            "SELECT owner_id FROM Tags WHERE name = $1 AND guild_id = $2;", tag, interaction.guild.id
        )

        if (
            owner_id == interaction.user.id
            or interaction.user.guild_permissions.manage_guild
        ):
            await self.bot.database.execute(
                "UPDATE Tags SET deleted = true WHERE name = $1;", tag
            )
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="The tag has successfully been deleted.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=silent,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TagsCog(bot))
