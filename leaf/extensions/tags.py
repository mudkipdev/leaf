from bot import LeafBot
from utils import Paginator
from discord.ext import commands
from discord import app_commands
import discord
import asyncio
import pytz
from fuzzywuzzy import process, fuzz
from cachetools import LRUCache
from typing import Optional, List


@app_commands.guild_only()
class TagsCog(commands.GroupCog, name="Tags", group_name="tags"):
    def __init__(self, bot: LeafBot) -> None:
        self.bot = bot
        # Cache upu to 1000 items and automatically discard the least recently used items.
        self.tag_cache = LRUCache(maxsize=1000)
        self.autocomplete_cache = LRUCache(maxsize=10000)

    async def check_permissions(
        self, tag_record: int, interaction: discord.Interaction
    ) -> bool:
        return (
            tag_record == interaction.user.id
            or interaction.user.guild_permissions.manage_guild
            or await self.bot.is_owner(interaction.user)
        )

    # Possible additional performance optimizations:
    # 1) Paginate records into batches and fetch them in chunks of 50.
    # 2) Timeout for database queries.
    async def tag_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        # Check if the autocomplete results are already in the cache
        cache_key = f"{interaction.guild.id}:{current.lower()}"
        if cache_key in self.autocomplete_cache:
            tag_records = self.autocomplete_cache[cache_key]
        else:
            # Fetch tag records from the cache or database
            prefix = current.lower()
            if (
                interaction.guild.id in self.tag_cache
                and prefix in self.tag_cache[interaction.guild.id]
            ):
                tag_records = self.tag_cache[interaction.guild.id][prefix]
            else:
                tag_records = await self.bot.database.fetch(
                    "SELECT * FROM tags WHERE guild_id = $1 AND name ILIKE $2 AND deleted = FALSE ORDER BY name ASC",
                    interaction.guild.id,
                    f"{prefix}%",
                )
                # Cache the tag records
                if interaction.guild.id not in self.tag_cache:
                    self.tag_cache[interaction.guild.id] = {}
                self.tag_cache[interaction.guild.id][prefix] = tag_records

            # Cache the autocomplete results
            self.autocomplete_cache[cache_key] = tag_records

        return [
            app_commands.Choice(name=tag["name"], value=tag["name"])
            for tag in tag_records
        ]

    @app_commands.describe(
        user="Optional filter for tags by a specific user.",
        starting_page="The page to start on.",
        silent="Whether the response should only be visible to you.",
    )
    @app_commands.command(name="list", description="Lists all the tags in the server.")
    async def list_tags(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        starting_page: Optional[int] = 1,
        silent: Optional[bool] = False,
    ) -> None:
        if user is not None:
            query = "SELECT * FROM tags WHERE guild_id = $1 AND owner_id = $2 AND deleted = FALSE ORDER BY name ASC"
            tags = await self.bot.database.fetch(query, interaction.guild.id, user.id)
        else:
            query = "SELECT * FROM tags WHERE guild_id = $1 AND deleted = FALSE ORDER BY name ASC"
            tags = await self.bot.database.fetch(query, interaction.guild.id)

        embeds = []
        if not tags:
            embeds.append(
                discord.Embed(
                    description=f"There are no tags in this server."
                    if user is None
                    else f"{user.name} does not have any tags in this server.",
                    color=discord.Color.dark_embed(),
                )
            )
        else:
            chunks = list(discord.utils.as_chunks(tags, 15))
            for index, chunk in enumerate(chunks):
                embed = discord.Embed(
                    description="\n".join(
                        [f"• **{tag['name']}** (Uses: {tag['uses']})" for tag in chunk]
                    ),
                    color=discord.Color.dark_embed(),
                )
                embed.set_footer(text=f"Page {index + 1} / {len(chunks)}")
                embeds.append(embed)

        if not 0 <= (starting_page - 1) < len(embeds):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="That page does not exist.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=silent,
            )
            return

        if tags:
            paginator = Paginator(
                embeds=embeds, index=starting_page - 1, author=interaction.user
            )
            await paginator.start(interaction, ephemeral=silent)
        else:
            await interaction.response.send_message(embed=embeds[0])

    @app_commands.describe(
        tag="The name of the tag to search.",
        silent="Whether the response should only be visible to you.",
    )
    @app_commands.command(name="search", description="Searches for the requested tag.")
    async def search_tag(
        self,
        interaction: discord.Interaction,
        tag: str,
        silent: Optional[bool] = False,
    ) -> None:
        tag_records = await self.bot.database.fetch(
            "SELECT * FROM tags WHERE guild_id = $1 AND deleted = FALSE",
            interaction.guild.id,
        )

        if tag_records:
            tag_names = [tag_record["name"] for tag_record in tag_records]
            matches: List[tuple[str, int]] = process.extract(tag, tag_names, limit=15)

            similar_tags = [
                match[0] for match in matches if match[1] >= 85
            ]  # Similarity threshold currently set to 85%.

            if similar_tags:
                tag_records = await self.bot.database.fetch(
                    "SELECT * FROM tags WHERE name = ANY($1::text[]) AND guild_id = $2 AND deleted = FALSE",
                    tuple(similar_tags),
                    interaction.guild.id,
                )
                for tag_record in tag_records:
                    embed = discord.Embed(
                        description="\n".join(
                            [
                                f"• **{tag_record['name']}**"
                                for tag_record in tag_records
                            ]
                        ),
                        color=discord.Color.dark_embed(),
                    )
                await interaction.response.send_message(embed=embed, ephemeral=silent)
            else:
                await interaction.response.send_message(
                    f"No similar tags found for '{tag}'.", ephemeral=silent
                )
        else:
            await interaction.response.send_message(
                f"No tags found for '{tag}'.", ephemeral=silent
            )

    @app_commands.describe(
        tag="The name of the tag to view.",
        raw="Whether the Markdown in this tag should be escaped or not.",
        silent="Whether the response should only be visible to you.",
    )
    @app_commands.command(name="view", description="Sends the content of a tag.")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def view_tag(
        self,
        interaction: discord.Interaction,
        tag: str,
        raw: Optional[bool] = False,
        silent: Optional[bool] = False,
    ) -> None:
        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE",
                tag,
                interaction.guild.id,
            )

            if tag_record:
                embed = discord.Embed(
                    title=tag_record["name"],
                    description=tag_record["content"],
                    color=discord.Color.dark_embed(),
                )
                if raw:
                    embed.description = discord.utils.escape_markdown(
                        tag_record["content"]
                    )
                await interaction.response.send_message(embed=embed, ephemeral=silent)
                await self.bot.database.execute(
                    "UPDATE tags SET uses = $1 WHERE name = $2 and guild_id = $3;",
                    tag_record["uses"] + 1,
                    tag,
                    interaction.guild.id,
                )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="That tag does not exist.",
                        color=discord.Color.dark_embed(),
                    ),
                    ephemeral=silent,
                )

    @app_commands.describe(name="The tag of the newly created tag.")
    @app_commands.command(name="create", description="Creates a new tag.")
    async def create_tag(self, interaction: discord.Interaction, name: str) -> None:
        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                name,
                interaction.guild.id,
            )

            if not tag_record:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="Please reply to this message with your tag content within 5 minutes.",
                        color=discord.Color.dark_embed(),
                    )
                )
                message = await interaction.original_response()

                def check(message):
                    return (
                        message.channel == interaction.channel
                        and message.author == interaction.user
                    )

                try:
                    message = await self.bot.wait_for(
                        "message", timeout=300, check=check
                    )
                except asyncio.TimeoutError:
                    await interaction.channel.send(
                        interaction.user.mention,
                        embed=discord.Embed(
                            description="You took too long to provide the tag content.",
                            color=discord.Color.dark_embed(),
                        ),
                    )
                    return

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
                        description="The tag has successfully been created.",
                        color=discord.Color.dark_embed(),
                    )
                )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="That tag already exists.",
                        color=discord.Color.dark_embed(),
                    )
                )

    @app_commands.describe(
        tag="The name of the tag to rename.", new_name="The new name of the tag."
    )
    @app_commands.autocomplete(tag=tag_autocomplete)
    @app_commands.command(name="rename", description="Changes the name of a tag.")
    async def rename_tag(
        self, interaction: discord.Interaction, tag: str, new_name: str
    ) -> None:
        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )

            if not tag_record:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="That tag does not exist.",
                        color=discord.Color.dark_embed(),
                    )
                )
                return

            if await self.check_permissions(tag_record["owner_id"], interaction):
                new_name_tag_record = await self.bot.database.fetchrow(
                    "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                    tag,
                    interaction.guild.id,
                )

                if new_name_tag_record:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            description=f"A tag named {new_name} already exists.",
                            color=discord.Color.dark_embed(),
                        )
                    )
                    return

                await self.bot.database.execute(
                    "UPDATE tags SET name = $1, last_edited_at = NOW() AT TIME ZONE 'utc' WHERE name = $2 and guild_id = $3;",
                    new_name,
                    tag,
                    interaction.guild.id,
                )
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="The tag has successfully been renamed.",
                        color=discord.Color.dark_embed(),
                    )
                )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="You do not have permission to rename that tag.",
                        color=discord.Color.dark_embed(),
                    )
                )

    @app_commands.describe(tag="The name of the tag to edit.")
    @app_commands.command(name="edit", description="Edits the content of a tag.")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def edit_tag(self, interaction: discord.Interaction, tag: str) -> None:
        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )

            if not tag_record:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="That tag does not exist.",
                        color=discord.Color.dark_embed(),
                    )
                )
                return

            if await self.check_permissions(tag_record["owner_id"], interaction):
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

                try:
                    message = await self.bot.wait_for(
                        "message", timeout=300, check=check
                    )
                except asyncio.TimeoutError:
                    await interaction.channel.send(
                        interaction.user.mention,
                        embed=discord.Embed(
                            description="You took too long to provide the new tag content.",
                            color=discord.Color.dark_embed(),
                        ),
                    )
                    return

                await self.bot.database.execute(
                    "UPDATE tags SET content = $1, last_edited_at = NOW() AT TIME ZONE 'utc' WHERE name = $2 and guild_id = $3;",
                    message.content,
                    tag,
                    interaction.guild.id,
                )

                await message.reply(
                    embed=discord.Embed(
                        description="The tag has successfully been edited.",
                        color=discord.Color.dark_embed(),
                    )
                )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="You do not have permission to edit that tag.",
                        color=discord.Color.dark_embed(),
                    )
                )

    @app_commands.describe(
        tag="The name of the tag to delete.",
        silent="Whether the response should only be visible to you.",
    )
    @app_commands.command(name="delete", description="Deletes a tag from the server.")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def delete_tag(
        self, interaction: discord.Interaction, tag: str, silent: Optional[bool] = False
    ) -> None:
        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )

            if not tag_record:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="That tag does not exist.",
                        color=discord.Color.dark_embed(),
                    ),
                    ephemeral=silent,
                )
                return

            # Check for tags with the same name and guild_id that have already been deleted.
            duplicate_tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = TRUE;",
                tag,
                interaction.guild.id,
            )

            # Hard delete if there is a duplicate. Otherwise, we would need to rethink the DB structure
            if duplicate_tag_record:
                await self.bot.database.execute(
                    "DELETE FROM Tags WHERE name = $1 AND guild_id = $2;",
                    tag,
                    interaction.guild.id,
                )

            if await self.check_permissions(tag_record["owner_id"], interaction):
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
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="You do not have permission to delete that tag.",
                        color=discord.Color.dark_embed(),
                    ),
                    ephemeral=silent,
                )

    @app_commands.describe(
        tag="A deleted tag that you wish to restore.",
        silent="Whether the response should only be visible to you.",
    )
    @app_commands.command(
        name="restore", description="Recovers a previously deleted tag."
    )
    @app_commands.checks.has_permissions(manage_guild=False)
    async def tag_restore(
        self, interaction: discord.Interaction, tag: str, silent: Optional[bool] = False
    ) -> None:
        tag_record = await self.bot.database.fetchrow(
            "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = TRUE;",
            tag,
            interaction.guild.id,
        )
        if not tag_record:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="That tag does not exist.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=silent,
            )
            return

        # Check for duplicate tag names
        duplicate_tag_record = await self.bot.database.fetchrow(
            "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
            tag,
            interaction.guild.id,
        )
        if duplicate_tag_record:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="A non-deleted tag with that name already exists. Please reply with a new name for the tag.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=silent,
            )

            def check(message):
                return (
                    message.channel == interaction.channel
                    and message.author == interaction.user
                )

            try:
                message = await self.bot.wait_for("message", timeout=300, check=check)
            except asyncio.TimeoutError:
                await interaction.followup.send("You took too long to respond.")
                return

            new_tag_name = message.content

            if not new_tag_name:
                await message.reply(
                    embed=discord.Embed(
                        description="Invalid tag name. Please try again.",
                        color=discord.Color.dark_embed(),
                    )
                )
                return
            elif await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                new_tag_name,
                interaction.guild.id,
            ):
                await message.reply(
                    embed=discord.Embed(
                        description="That tag name is already taken. Please try again.",
                        color=discord.Color.dark_embed(),
                    ),
                )
                return

            await self.bot.database.execute(
                "UPDATE tags SET name = $1, deleted = FALSE WHERE name = $2 AND guild_id = $3 AND deleted = TRUE",
                new_tag_name,
                tag,
                interaction.guild.id,
            )
            await message.reply(
                embed=discord.Embed(
                    description=f"The tag: {tag} has been renamed to {new_tag_name} and restored.",
                    color=discord.Color.dark_embed(),
                ),
            )
        else:
            await self.bot.database.execute(
                "UPDATE tags SET deleted = FALSE WHERE name = $1 AND guild_id = $2",
                tag,
                interaction.guild.id,
            )
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"The tag: {tag} has been restored.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=silent,
            )

    @app_commands.describe(
        tag="The tag to view info for.",
        silent="Whether the response should only be visible to you.",
    )
    @app_commands.command(name="info", description="Sends the info and stats of a tag.")
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def tag_info(
        self, interaction: discord.Interaction, tag: str, silent: Optional[bool] = False
    ) -> None:
        tag_record = await self.bot.database.fetchrow(
            "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
            tag,
            interaction.guild.id,
        )

        if tag_record:
            owner = await self.bot.try_user(tag_record["owner_id"])
            embed = discord.Embed(
                title=f"Info for tag \"{tag_record['name']}\"",
                color=discord.Color.dark_embed(),
            )
            embed.add_field(name="Owner", value=owner.mention)
            embed.add_field(
                name="Created At",
                value=discord.utils.format_dt(
                    pytz.UTC.localize(tag_record["created_at"], "D")
                ),
                inline=False,
            )
            if tag_record["last_edited_at"] != tag_record["created_at"]:
                embed.add_field(
                    name="Updated At",
                    value=discord.utils.format_dt(
                        pytz.UTC.localize(tag_record["last_edited_at"], "D")
                    ),
                    inline=False,
                )
            embed.add_field(name="Uses", value=str(tag_record["uses"]), inline=False)
            embed.set_thumbnail(url=owner.avatar.url)

            await interaction.response.send_message(embed=embed, ephemeral=silent)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="That tag does not exist.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=silent,
            )

    @app_commands.describe(
        tag="The tag to transfer to the new user.",
        user="The user to transfer the tag to.",
    )
    @app_commands.command(
        name="transfer", description="Transfers a tag to a different owner."
    )
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def transfer_tag(
        self, interaction: discord.Interaction, tag: str, user: discord.Member
    ) -> None:
        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )

            if tag_record:
                if await self.check_permissions(tag_record["owner_id"], interaction):
                    if user.bot:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                description="You cannot transfer tags to bots.",
                                color=discord.Color.dark_embed(),
                            )
                        )
                        return

                    await self.bot.database.execute(
                        "UPDATE tags SET owner_id = $1 WHERE name = $2 AND guild_id = $3",
                        user.id,
                        tag,
                        interaction.guild.id,
                    )
                    await interaction.response.send_message(
                        user.mention,
                        embed=discord.Embed(
                            description=f"The tag has successfully been transferred to {user.mention}.",
                            color=discord.Color.dark_embed(),
                        ),
                    )
                else:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            description="You do not have permission to edit that tag.",
                            color=discord.Color.dark_embed(),
                        )
                    )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="That tag does not exist.",
                        color=discord.Color.dark_embed(),
                    )
                )

    @app_commands.describe(tag="The tag you wish to claim.")
    @app_commands.command(
        name="claim",
        description="Claims an unclaimed tag. An unclaimed tag is a tag with no owner "
        "because they have left the server.",
    )
    @app_commands.autocomplete(tag=tag_autocomplete)
    async def claim_tag(
        self, interaction: discord.Interaction, tag: str, silent: Optional[bool] = False
    ) -> None:
        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )

            if tag_record:
                try:
                    member = await self.bot.try_member(
                        tag_record["owner_id"], guild=interaction.guild
                    )
                    if member is not None:
                        await interaction.response.send_message(
                            embed=discord.Embed(
                                description=f'The owner of the tag "{tag}" is still present in the server.',
                                color=discord.Color.dark_embed(),
                            ),
                            ephemeral=silent,
                        )
                except discord.NotFound:
                    await self.bot.database.execute(
                        "UPDATE tags SET owner_id = $1 WHERE name = $2",
                        interaction.user.id,
                        tag,
                    )

                    await interaction.response.send_message(
                        embed=discord.Embed(
                            description=f'The tag "{tag}" has successfully been claimed by {interaction.user}.',
                            color=discord.Color.dark_embed(),
                        ),
                        ephemeral=silent,
                    )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f'A tag named "{tag}" does not exist',
                        color=discord.Color.dark_embed(),
                    ),
                    ephemeral=silent,
                )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TagsCog(bot))
