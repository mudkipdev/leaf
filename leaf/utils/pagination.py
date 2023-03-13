from discord.ext import commands
import discord
import asyncio

from typing import List

__all__ = ("Paginator",)


class Paginator:
    def __init__(self, embeds: List[discord.Embed], index: int = 0) -> None:
        self.paginated_view = PaginatedView(embeds)
        self.embeds: List[discord.Embed] = embeds
        self.index: int = index

    async def start(
        self,
        messageable: discord.abc.Messageable | discord.Interaction,
        *args,
        **kwargs
    ) -> None:
        kwargs["embed"] = self.embeds[self.index]
        kwargs["view"] = self.paginated_view

        if isinstance(messageable, discord.Interaction):
            await messageable.response.send_message(*args, **kwargs)
        elif isinstance(messageable, discord.abc.Messageable):
            await messageable.send(*args, **kwargs)

        self.paginated_view.set_index(self.index)


class PaginatedView(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed]) -> None:
        super().__init__(timeout=None)
        self.embeds: List[discord.Embed] = embeds
        self.index: int = 0

    @discord.ui.button(custom_id="previous", emoji="◀")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.set_index(self.index - 1)
        await self.update(interaction)

    @discord.ui.button(custom_id="page", emoji="🔢")
    async def page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(PageModal(self))

    @discord.ui.button(custom_id="next", emoji="▶")
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.set_index(self.index + 1)
        await self.update(interaction)

    async def update(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self.embeds[self.index], view=self
        )

    def set_index(self, index: int) -> None:
        if not 0 <= index < len(self.embeds):
            return

        self.previous.disabled = index == 0
        self.next.disabled = index == len(self.embeds) - 1
        self.index = index


class PageModal(discord.ui.Modal, title="Skip to Page"):
    page = discord.ui.TextInput(label="Page", required=True)

    def __init__(self, paginated_view: PaginatedView) -> None:
        super().__init__()
        self.paginated_view = paginated_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.page.value.isdigit():
            self.paginated_view.set_index(int(self.page.value) - 1)
            await self.paginated_view.update(interaction)
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="That page number is invalid.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=True,
            )
