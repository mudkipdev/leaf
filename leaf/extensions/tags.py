import asyncio
import logging
from typing import Optional, List

import disnake
import pytz
from disnake.ext import commands
from fuzzywuzzy import process
from cachetools import LRUCache

from bot import LeafBot
from utils import Paginator


# noinspection PyUnresolvedReferences,PyTypeChecker
class TagsCog(commands.Cog):
    def __init__(self, bot: LeafBot) -> None:
        self.bot = bot
        # Cache upu to 1000 items and automatically discard the least recently used items.
        self.tag_cache = LRUCache(maxsize=1000)
        self.autocomplete_cache = LRUCache(maxsize=1000)
        self._reserved_tags_being_made = {}
        self.logger = logging.getLogger("leaf_logger")

    async def check_permissions(
        self, tag_record: int, interaction: disnake.GuildCommandInteraction
    ) -> bool:
        return (
            tag_record == interaction.user.id
            or interaction.author.guild_permissions.manage_guild
            or await self.bot.is_owner(interaction.user)
        )

    def is_tag_being_made(self, guild_id, name):
        try:
            being_made = self._reserved_tags_being_made[guild_id]
            self.logger.debug(f"Tag: {tags} is current reserved.")
        except KeyError as e:
            self.logger.critical("An error occurred in tag creation.", exc_info=e)
            return False
        else:
            return name.lower() in being_made

    def add_in_progress_tag(self, guild_id, name):
        tags = self._reserved_tags_being_made.setdefault(guild_id, set())
        tags.add(name.lower())
        self.logger.debug(f"Tag: {tags} is being reserved.")

    def remove_in_progress_tag(self, guild_id, name):
        try:
            being_made = self._reserved_tags_being_made[guild_id]
        except KeyError as e:
            self.logger.critical("An error occurred in tag removal.", exc_info=e)
            return

        being_made.discard(name.lower())
        if not being_made:
            del self._reserved_tags_being_made[guild_id]

    @commands.slash_command(name="tags")
    async def tags(self, inter: disnake.GuildCommandInteraction) -> None:
        ...

    @tags.sub_command(name="list")
    async def list_tags(
        self,
        interaction: disnake.GuildCommandInteraction,
        user: Optional[disnake.Member] = None,
        starting_page: int = 1,
        silent: bool = False,
    ) -> None:
        """
        Lists all the tags in the server.

        Parameters
        ----------
        user: Optional filter for tags by a specific user.
        starting_page: The page to start on.
        silent: Whether the response should only be visible to you.
        """

        if user is not None:
            query = "SELECT * FROM tags WHERE guild_id = $1 AND owner_id = $2 AND deleted = FALSE ORDER BY name ASC"
            tags = await self.bot.database.fetch(query, interaction.guild.id, user.id)

        else:
            query = "SELECT * FROM tags WHERE guild_id = $1 AND deleted = FALSE ORDER BY name ASC"
            tags = await self.bot.database.fetch(query, interaction.guild.id)

        self.logger.debug(tags)

        embeds = []
        if not tags:
            embeds.append(
                disnake.Embed(
                    description=f"There are no tags in this server."
                    if user is None
                    else f"{user.name} does not have any tags in this server.",
                    color=disnake.Color.dark_theme(),
                )
            )
        else:
            chunks = list(disnake.utils.as_chunks(iter(tags), 15))
            self.logger.info(f"Creating embed with {chunks} chunks.")
            for index, chunk in enumerate(chunks):
                embed = disnake.Embed(
                    description="\n".join(
                        [f"• **{tag['name']}** (Uses: {tag['uses']})" for tag in chunk]
                    ),
                    color=disnake.Color.dark_theme(),
                )
                embed.set_footer(text=f"Page {index + 1} / {len(chunks)}")
                embeds.append(embed)

        if not 0 <= (starting_page - 1) < len(embeds):
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description="That page does not exist.",
                    color=disnake.Color.dark_theme(),
                ),
                ephemeral=silent,
            )
            return

        if tags:
            paginator = Paginator(
                embeds=embeds, index=starting_page - 1, author=interaction.author
            )
            await paginator.start(interaction, ephemeral=silent)
        else:
            await interaction.response.send_message(embed=embeds[0])

    @tags.sub_command(name="search")
    async def search_tag(
        self,
        interaction: disnake.GuildCommandInteraction,
        tag: str,
        silent: bool = False,
    ) -> None:
        """
        Searches for the requested tag.

        Parameters
        ----------
        tag: The name of the tag to search.
        silent: Whether the response should only be visible to you.
        """

        tag_records = await self.bot.database.fetch(
            "SELECT * FROM tags WHERE guild_id = $1 AND deleted = FALSE",
            interaction.guild.id,
        )

        self.logger.debug(tag_records)

        if tag_records:
            tag_names = [tag_record["name"] for tag_record in tag_records]
            matches: List[tuple[str, int]] = process.extract(tag, tag_names, limit=15)  # type: ignore

            self.logger.debug(
                f"Discovered tag names: {tag_names}\n Possible matches: {matches}"
            )

            similar_tags = [
                match[0] for match in matches if match[1] >= 85
            ]  # Similarity threshold currently set to 85%.

            self.logger.debug(f"Similar tags: {similar_tags}")

            if similar_tags:
                tag_records = await self.bot.database.fetch(
                    "SELECT * FROM tags WHERE name = ANY($1::text[]) AND guild_id = $2 AND deleted = FALSE",
                    tuple(similar_tags),
                    interaction.guild.id,
                )
                self.logger.debug(tag_records)

                embed = disnake.Embed(
                    description="\n".join(
                        [f"• **{tag_record['name']}**" for tag_record in tag_records]
                    ),
                    color=disnake.Color.dark_theme(),
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

    @tags.sub_command(name="view")
    async def view_tag(
        self,
        interaction: disnake.GuildCommandInteraction,
        tag: str,
        raw: bool = False,
        silent: bool = False,
    ) -> None:
        """
        Sends the content of a tag.

        Parameters
        ----------
        tag: The name of the tag to view.
        raw: Whether the Markdown in this tag should be escaped or not.
        silent: Whether the response should only be visible to you.
        """

        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE",
                tag,
                interaction.guild.id,
            )
            self.logger.debug(tag_record)

            if tag_record:
                embed = disnake.Embed(
                    title=tag_record["name"],
                    description=tag_record["content"],
                    color=disnake.Color.dark_theme(),
                )
                if raw:
                    embed.description = disnake.utils.escape_markdown(
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
                    embed=disnake.Embed(
                        description="That tag does not exist.",
                        color=disnake.Color.dark_theme(),
                    ),
                    ephemeral=silent,
                )

    @tags.sub_command(name="create")
    async def create_tag(
        self, interaction: disnake.GuildCommandInteraction, name: str
    ) -> None:
        """
        Creates a new tag.

        Parameters
        ----------
        name: The tag of the newly created tag.
        """

        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                name,
                interaction.guild.id,
            )
            self.logger.debug(tag_record)

            if not tag_record and not self.is_tag_being_made(
                interaction.guild.id, name
            ):
                self.add_in_progress_tag(interaction.guild.id, name)
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="Please reply to this message with your tag content within 5 minutes.",
                        color=disnake.Color.dark_theme(),
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
                except asyncio.TimeoutError as e:
                    self.logger.info("Command timeout:", exc_info=e)
                    await interaction.channel.send(
                        interaction.user.mention,
                        embed=disnake.Embed(
                            description="You took too long to provide the tag content.",
                            color=disnake.Color.dark_theme(),
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
                self.remove_in_progress_tag(interaction.guild.id, name)
                await message.reply(
                    embed=disnake.Embed(
                        description="The tag has successfully been created.",
                        color=disnake.Color.dark_theme(),
                    )
                )
            else:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="That tag already exists.",
                        color=disnake.Color.dark_theme(),
                    )
                )

    @tags.sub_command(name="rename")
    async def rename_tag(
        self, interaction: disnake.GuildCommandInteraction, tag: str, new_name: str
    ) -> None:
        """
        Changes the name of a tag.

        Parameters
        ----------
        tag: The name of the tag to rename.
        new_name: The new name of the tag.
        """

        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )

            self.logger.debug(tag_record)

            if not tag_record:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="That tag does not exist.",
                        color=disnake.Color.dark_theme(),
                    )
                )
                return

            if await self.check_permissions(tag_record["owner_id"], interaction):
                new_name_tag_record = await self.bot.database.fetchrow(
                    "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                    tag,
                    interaction.guild.id,
                )
                self.logger.debug(new_name_tag_record)

                if new_name_tag_record and self.is_tag_being_made(
                    interaction.guild.id, new_name
                ):
                    await interaction.response.send_message(
                        embed=disnake.Embed(
                            description=f"A tag named {new_name} already exists.",
                            color=disnake.Color.dark_theme(),
                        )
                    )
                    return

                self.add_in_progress_tag(interaction.guild.id, new_name)

                await self.bot.database.execute(
                    "UPDATE tags SET name = $1, last_edited_at = NOW() AT TIME ZONE 'utc' WHERE name = $2 and guild_id = $3;",
                    new_name,
                    tag,
                    interaction.guild.id,
                )
                self.remove_in_progress_tag(interaction.guild.id, new_name)

                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="The tag has successfully been renamed.",
                        color=disnake.Color.dark_theme(),
                    )
                )
            else:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="You do not have permission to rename that tag.",
                        color=disnake.Color.dark_theme(),
                    )
                )

    @tags.sub_command(name="edit")
    async def edit_tag(
        self, interaction: disnake.GuildCommandInteraction, tag: str
    ) -> None:
        """
        Edits the content of a tag.

        Parameters
        ----------
        tag: The name of the tag to edit.
        """

        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )
            self.logger.debug(tag_record)

            if not tag_record:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="That tag does not exist.",
                        color=disnake.Color.dark_theme(),
                    )
                )
                return

            if await self.check_permissions(tag_record["owner_id"], interaction):  # type: ignore
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="Please reply to this message with your new tag content within 5 minutes.",
                        color=disnake.Color.dark_theme(),
                    )
                )
                message = await interaction.original_response()

                self.logger.debug(message)

                def check(message):
                    return (
                        message.channel == interaction.channel
                        and message.author == interaction.user
                    )

                try:
                    message = await self.bot.wait_for(
                        "message", timeout=300, check=check
                    )
                except asyncio.TimeoutError as e:
                    self.logger.info("Command timeout:", exc_info=e)
                    await interaction.channel.send(
                        interaction.user.mention,
                        embed=disnake.Embed(
                            description="You took too long to provide the new tag content.",
                            color=disnake.Color.dark_theme(),
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
                    embed=disnake.Embed(
                        description="The tag has successfully been edited.",
                        color=disnake.Color.dark_theme(),
                    )
                )
            else:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="You do not have permission to edit that tag.",
                        color=disnake.Color.dark_theme(),
                    )
                )

    @tags.sub_command(name="delete")
    async def delete_tag(
        self,
        interaction: disnake.GuildCommandInteraction,
        tag: str,
        silent: bool = False,
    ) -> None:
        """
        Deletes a tag from the server.

        Parameters
        ----------
        tag: The name of the tag to delete.
        silent: Whether the response should only be visible to you.
        """

        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )
            self.logger.debug(tag_record)

            if not tag_record:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="That tag does not exist.",
                        color=disnake.Color.dark_theme(),
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

            self.logger.debug(duplicate_tag_record)

            # Hard delete if there is a duplicate. Otherwise, we would need to rethink the DB structure
            if duplicate_tag_record:
                await self.bot.database.execute(
                    "DELETE FROM Tags WHERE name = $1 AND guild_id = $2;",
                    tag,
                    interaction.guild.id,
                )

            if await self.check_permissions(tag_record["owner_id"], interaction):  # type: ignore
                await self.bot.database.execute(
                    "UPDATE Tags SET deleted = true WHERE name = $1;", tag
                )
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="The tag has successfully been deleted.",
                        color=disnake.Color.dark_theme(),
                    ),
                    ephemeral=silent,
                )
            else:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="You do not have permission to delete that tag.",
                        color=disnake.Color.dark_theme(),
                    ),
                    ephemeral=silent,
                )

    @tags.sub_command(name="restore")
    @commands.has_permissions(manage_guild=True)
    async def restore_tag(
        self,
        interaction: disnake.GuildCommandInteraction,
        tag: str,
        silent: bool = False,
    ) -> None:
        """
        Recovers a previously deleted tag.

        Parameters
        ----------
        tag: The deleted tag that you wish to restore.
        silent: Whether the response should only be visible to you.
        """

        tag_record = await self.bot.database.fetchrow(
            "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = TRUE;",
            tag,
            interaction.guild.id,
        )
        self.logger.debug(tag_record)

        if not tag_record:
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description="That tag does not exist.",
                    color=disnake.Color.dark_theme(),
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
        self.logger.debug(duplicate_tag_record)

        if duplicate_tag_record:
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description="A non-deleted tag with that name already exists. Please reply with the new name for the tag.",
                    color=disnake.Color.dark_theme(),
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
            except asyncio.TimeoutError as e:
                self.logger.info("Timeout Error:", exc_info=e)
                await interaction.followup.send("You took too long to respond.")
                return

            new_tag_name = message.content

            if not new_tag_name:
                await message.reply(
                    embed=disnake.Embed(
                        description="Invalid tag name. Please try again.",
                        color=disnake.Color.dark_theme(),
                    )
                )
                return
            elif self.is_tag_being_made(interaction.guild_id, new_tag_name):
                await message.reply(
                    embed=disnake.Embed(
                        description="That tag name is already taken. Please try again.",
                        color=disnake.Color.dark_theme(),
                    )
                )
                return
            elif await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                new_tag_name,
                interaction.guild.id,
            ):
                await message.reply(
                    embed=disnake.Embed(
                        description="That tag name is already taken. Please try again.",
                        color=disnake.Color.dark_theme(),
                    ),
                )
                return
            # Add the tag to in progress list so it cant be used in other commands.
            self.add_in_progress_tag(interaction.guild_id, new_tag_name)
            await self.bot.database.execute(
                "UPDATE tags SET name = $1, deleted = FALSE WHERE name = $2 AND guild_id = $3 AND deleted = TRUE",
                new_tag_name,
                tag,
                interaction.guild.id,
            )
            # Remove tag after DB is finished
            self.remove_in_progress_tag(interaction.guild_id, new_tag_name)
            await message.reply(
                embed=disnake.Embed(
                    description=f'The tag "{tag}" has been renamed to {new_tag_name} and restored.',
                    color=disnake.Color.dark_theme(),
                ),
            )
        else:
            await self.bot.database.execute(
                "UPDATE tags SET deleted = FALSE WHERE name = $1 AND guild_id = $2",
                tag,
                interaction.guild.id,
            )
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description=f'The tag "{tag}" has been restored.',
                    color=disnake.Color.dark_theme(),
                ),
                ephemeral=silent,
            )

    @tags.sub_command(name="info")
    async def tag_info(
        self,
        interaction: disnake.GuildCommandInteraction,
        tag: str,
        silent: bool = False,
    ) -> None:
        """
        Sends the info and stats of a tag.

        Parameters
        ----------
        tag: The tag to view info for.
        silent: Whether the response should only be visible to you.
        """

        tag_record = await self.bot.database.fetchrow(
            "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
            tag,
            interaction.guild.id,
        )
        self.logger.debug(tag_record)

        if tag_record:
            owner = await self.bot.try_user(tag_record["owner_id"])  # type: ignore
            embed = disnake.Embed(
                title=f"Info for tag \"{tag_record['name']}\"",  # type: ignore
                color=disnake.Color.dark_theme(),
            )
            embed.add_field(name="Owner", value=owner.mention)
            embed.add_field(
                name="Created At",
                value=disnake.utils.format_dt(
                    pytz.UTC.localize(tag_record["created_at"], True)  # type: ignore
                ),
                inline=False,
            )
            if tag_record["last_edited_at"] != tag_record["created_at"]:  # type: ignore
                embed.add_field(
                    name="Updated At",
                    value=disnake.utils.format_dt(
                        pytz.UTC.localize(tag_record["last_edited_at"], True)  # type: ignore
                    ),
                    inline=False,
                )
            embed.add_field(name="Uses", value=str(tag_record["uses"]), inline=False)  # type: ignore
            owner_av = owner.avatar.url if owner.avatar else owner.display_avatar.url
            embed.set_thumbnail(url=owner_av)

            await interaction.response.send_message(embed=embed, ephemeral=silent)
        else:
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description="That tag does not exist.",
                    color=disnake.Color.dark_theme(),
                ),
                ephemeral=silent,
            )

    @tags.sub_command(name="transfer")
    async def transfer_tag(
        self,
        interaction: disnake.GuildCommandInteraction,
        tag: str,
        user: disnake.Member,
    ) -> None:
        """
        Transfers a tag to a different owner.

        Parameters
        ----------
        tag: The tag to transfer to the new user.
        user: The user to transfer the tag to.
        """

        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )

            self.logger.debug(tag_record)

            if tag_record:
                if await self.check_permissions(tag_record["owner_id"], interaction):  # type: ignore
                    if user.bot:
                        await interaction.response.send_message(
                            embed=disnake.Embed(
                                description="You cannot transfer tags to bots.",
                                color=disnake.Color.dark_theme(),
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
                        embed=disnake.Embed(
                            description=f"The tag has successfully been transferred to {user.mention}.",
                            color=disnake.Color.dark_theme(),
                        ),
                    )
                else:
                    await interaction.response.send_message(
                        embed=disnake.Embed(
                            description="You do not have permission to edit that tag.",
                            color=disnake.Color.dark_theme(),
                        )
                    )
            else:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description="That tag does not exist.",
                        color=disnake.Color.dark_theme(),
                    )
                )

    @tags.sub_command(name="claim")
    async def claim_tag(
        self,
        interaction: disnake.GuildCommandInteraction,
        tag: str,
        silent: bool = False,
    ) -> None:
        """
        Claims an unclaimed tag. An unclaimed tag is a tag with no owner because they have left the server.

        Parameters
        ----------
        tag: The tag you wish to claim.
        """

        async with self.bot.database.transaction():
            tag_record = await self.bot.database.fetchrow(
                "SELECT * FROM Tags WHERE name = $1 AND guild_id = $2 AND deleted = FALSE;",
                tag,
                interaction.guild.id,
            )
            self.logger.debug(tag_record)

            if tag_record:
                try:
                    member = await self.bot.try_member(
                        tag_record["owner_id"], guild=interaction.guild  # type: ignore
                    )
                    if member is not None:
                        await interaction.response.send_message(
                            embed=disnake.Embed(
                                description=f'The owner of the tag "{tag}" is still present in the server.',
                                color=disnake.Color.dark_theme(),
                            ),
                            ephemeral=silent,
                        )
                except disnake.NotFound:
                    self.logger.info(
                        f"Member is no longer in the server. Executing transfer..."
                    )
                    await self.bot.database.execute(
                        "UPDATE tags SET owner_id = $1 WHERE name = $2",
                        interaction.user.id,
                        tag,
                    )

                    await interaction.response.send_message(
                        embed=disnake.Embed(
                            description=f'The tag "{tag}" has successfully been claimed by {interaction.user}.',
                            color=disnake.Color.dark_theme(),
                        ),
                        ephemeral=silent,
                    )
            else:
                await interaction.response.send_message(
                    embed=disnake.Embed(
                        description=f'A tag named "{tag}" does not exist',
                        color=disnake.Color.dark_theme(),
                    ),
                    ephemeral=silent,
                )

        # Possible additional performance optimizations:

    # 1) Paginate records into batches and fetch them in chunks of 50.
    # 2) Timeout for database queries.
    @view_tag.autocomplete("tag")
    @rename_tag.autocomplete("tag")
    @edit_tag.autocomplete("tag")
    @delete_tag.autocomplete("tag")
    @tag_info.autocomplete("tag")
    @transfer_tag.autocomplete("tag")
    @claim_tag.autocomplete("tag")
    async def tag_autocomplete(
        self, interaction: disnake.GuildCommandInteraction, current: str
    ) -> str:
        # Check if the autocomplete results are already in the cache
        cache_key = f"{interaction.guild.id}:{current.lower()}"

        self.logger.debug(cache_key)

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

                self.logger.debug(tag_records)
            else:
                tag_records = await self.bot.database.fetch(
                    "SELECT * FROM tags WHERE guild_id = $1 AND name ILIKE $2 AND deleted = FALSE ORDER BY name ASC",
                    interaction.guild.id,
                    f"{prefix}%",
                )
                self.logger.debug(tag_records)
                # Cache the tag records
                if interaction.guild.id not in self.tag_cache:
                    self.tag_cache[interaction.guild.id] = {}
                self.tag_cache[interaction.guild.id][prefix] = tag_records

            # Cache the autocomplete results
            self.autocomplete_cache[cache_key] = tag_records

            self.logger.debug(self.autocomplete_cache)

        return [tag["name"] for tag in tag_records]  # type: ignore


def setup(bot: LeafBot) -> None:
    bot.add_cog(TagsCog(bot))
