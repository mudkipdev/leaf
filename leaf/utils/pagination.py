from __future__ import annotations

from disnake.ext import commands
import disnake
import asyncio

from typing import Optional, List

__all__ = ("Paginator",)


class Paginator:
    def __init__(
        self,
        embeds: List[disnake.Embed],
        *,
        index: int = 0,
        author: Optional[disnake.Member] = None
    ) -> None:
        self.embeds = embeds
        self.index = index
        self.author = author
        self.paginated_view = PaginatedView(self.embeds, author=self.author)

    async def start(
        self,
        messageable: disnake.abc.Messageable | disnake.Interaction,
        *args,
        **kwargs
    ) -> None:
        kwargs["embed"] = self.embeds[self.index]
        kwargs["view"] = self.paginated_view

        if isinstance(messageable, disnake.Interaction):
            await messageable.response.send_message(*args, **kwargs)
        elif isinstance(messageable, disnake.abc.Messageable):
            await messageable.send(*args, **kwargs)

        self.paginated_view.set_index(self.index)


class PaginatedView(disnake.ui.View):
    def __init__(
        self, embeds: List[disnake.Embed], *, author: Optional[disnake.Member] = None
    ) -> None:
        super().__init__(timeout=None)
        self.embeds = embeds
        self.index = 0
        self.author = author

    @disnake.ui.button(custom_id="previous", emoji="◀")
    async def previous(
        self, _: disnake.ui.Button[PaginatedView], interaction: disnake.MessageInteraction
    ) -> None:
        self.set_index(self.index - 1)
        await self.update(interaction)

    @disnake.ui.button(custom_id="page", emoji="🔢")
    async def page(
        self, _: disnake.ui.Button[PaginatedView], interaction: disnake.MessageInteraction
    ) -> None:
        if self.author and interaction.user != self.author:
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description="You do not have permission to interact with this menu.",
                    color=disnake.Color.dark_theme(),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(PageModal(self))

    @disnake.ui.button(custom_id="next", emoji="▶")
    async def next(
        self, _: disnake.ui.Button[PaginatedView], interaction: disnake.MessageInteraction
    ) -> None:
        self.set_index(self.index + 1)
        await self.update(interaction)

    async def update(self, interaction: disnake.Interaction) -> None:
        if self.author and interaction.user != self.author:
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description="You do not have permission to interact with this menu.",
                    color=disnake.Color.dark_theme(),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=self.embeds[self.index], view=self
        )

    def set_index(self, index: int) -> None:
        if not 0 <= index < len(self.embeds):
            return

        self.previous.disabled = index == 0
        self.next.disabled = index == len(self.embeds) - 1
        self.index = index


class PageModal(disnake.ui.Modal):
    page = disnake.ui.TextInput(label="Page", required=True, custom_id="page-1")

    def __init__(self, paginated_view: PaginatedView) -> None:
        super().__init__(title="Skip to Page", components=self.page)
        self.paginated_view = paginated_view

    async def on_submit(self, interaction: disnake.Interaction) -> None:
        assert self.page.value is not None

        if self.page.value.isdigit():
            self.paginated_view.set_index(int(self.page.value) - 1)
            await self.paginated_view.update(interaction)
        else:
            await interaction.response.send_message(
                embed=disnake.Embed(
                    description="That page number is invalid.",
                    color=disnake.Color.dark_theme(),
                ),
                ephemeral=True,
            )
