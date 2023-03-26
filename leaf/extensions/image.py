import enum
import io
from typing import Optional

from bot import LeafBot
from utils import Paginator
import aiohttp
import discord
from PIL import Image, ImageFilter, ImageOps
from discord import app_commands
from discord.ext import commands


class FilterChoices(enum.Enum):
    BLUR = ImageFilter.BLUR
    CONTOUR = ImageFilter.CONTOUR
    DETAIL = ImageFilter.DETAIL
    EDGE_ENHANCE = ImageFilter.EDGE_ENHANCE
    EDGE_ENHANCE_MORE = ImageFilter.EDGE_ENHANCE_MORE
    EMBOSS = ImageFilter.EMBOSS
    FIND_EDGES = ImageFilter.FIND_EDGES
    SHARPEN = ImageFilter.SHARPEN
    SMOOTH = ImageFilter.SMOOTH
    SMOOTH_MORE = ImageFilter.SMOOTH_MORE

    @property
    def filter(self):
        return self.value


class FilterButton(discord.ui.Button):
    def __init__(
        self, label: str, choice: FilterChoices, author: Optional[discord.User] = None
    ) -> None:
        super().__init__(
            style=discord.ButtonStyle.secondary, label=label.title().replace("_", " ")
        )
        self.choice = choice
        self.author = author

    @discord.ui.button()
    async def callback(self, interaction: discord.Interaction) -> None:
        assert isinstance(self.view, FilterView)
        if self.disabled:
            return

        if self.author and interaction.user != self.author:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You do not have permission to interact with this menu.",
                    color=discord.Color.dark_embed(),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        self.view.choice = self.choice

        await self.view.update_view(interaction)


class FilterView(discord.ui.View):
    def __init__(
        self,
        image: Image.Image,
        author: Optional[discord.User],
        interaction: Optional[discord.Interaction],
    ) -> None:
        super().__init__(timeout=5)
        self.choice = None
        self.image = image
        self.author = author
        self.interaction = interaction

        for choice in FilterChoices:
            button = FilterButton(label=choice.name.lower(), choice=choice)
            self.add_item(button)

    async def update_view(self, interaction: discord.Interaction) -> None:
        assert self.choice is not None

        img = self.image.filter(self.choice.filter)
        buffer = io.BytesIO()
        img = img.convert("RGB")
        img.save(buffer, format="JPEG")
        buffer.seek(0)

        file = discord.File(buffer, filename="processed_image.jpg")

        await self.interaction.edit_original_response(
            attachments=[file],
            view=FilterView(
                image=self.image, author=self.author, interaction=interaction
            ),
        )

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, FilterButton):
                child.disabled = True
        await self.interaction.edit_original_response(view=self)
        super().stop()


@app_commands.guild_only()
class ImageCog(commands.GroupCog, name="Image", group_name="image"):
    def __init__(self, bot: LeafBot) -> None:
        self.bot = bot

    @staticmethod
    async def read_image(image: discord.Attachment) -> Image.Image:
        async with aiohttp.ClientSession() as session:
            async with session.get(image.url) as response:
                buffer = io.BytesIO(await response.read())
        return Image.open(buffer)

    @app_commands.describe(
        image="The image you wish to manipulate.",
    )
    @app_commands.command(
        name="filter", description="Apply a filter to the provided image."
    )
    async def filter_image(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
    ) -> None:
        await interaction.response.defer()

        img = await self.read_image(image)

        view = FilterView(image=img, author=interaction.user, interaction=interaction)

        buffer = io.BytesIO()
        img = img.convert("RGB")
        img.save(buffer, format="JPEG")
        buffer.seek(0)

        file = discord.File(buffer, filename="processed_image.jpg")

        await interaction.followup.send(file=file, view=view)

    @app_commands.describe(
        image1="First image to blend.",
        image2="Second image to blend",
        alpha="The interpolation alpha factor. If alpha is 0.0, a copy of the first image is returned. If alpha is "
        "1.0, a copy of the second image is returned. There are no restrictions on the alpha value. If "
        "necessary, the result is clipped to fit into the allowed output range.",
    )
    @app_commands.command(
        name="blend",
        description="Creates a new image by interpolating between two input images, using a constant alpha:",
    )
    async def blend_image(
        self,
        interaction: discord.Interaction,
        image1: discord.Attachment,
        image2: discord.Attachment,
        alpha: float,
    ) -> None:
        img1 = await self.read_image(image1)
        img2 = await self.read_image(image2)

        if image1.size != image2.size:
            img2 = img2.resize((img1.width, img1.height))

        img_blend = Image.blend(img1, img2, alpha)

        buffer = io.BytesIO()
        img_blend.save(buffer, format="JPEG")
        buffer.seek(0)

        file = discord.File(buffer, filename="blended_image.jpg")

        await interaction.response.send_message(files=[file])

    @app_commands.describe(image="Image to process")
    @app_commands.command(
        name="colors", description="Returns a list of colors used in this image."
    )
    async def image_colors(
        self, interaction: discord.Interaction, image: discord.Attachment
    ) -> None:
        img = await self.read_image(image)
        img = img.convert("P", palette=Image.ADAPTIVE, colors=256)
        image_colors = img.getcolors()
        palette = img.getpalette()
        hex_palette = [
            f"#{palette[idx]:02x}{palette[idx + 1]:02x}{palette[idx + 2]:02x} (Count: {count})"
            for count, idx in image_colors
        ]

        embeds = []

        chunks = list(discord.utils.as_chunks(hex_palette, 15))
        for index, chunk in enumerate(chunks):
            embed = discord.Embed(
                description="\n".join(chunk), color=discord.Color.dark_embed()
            )
            embed.set_footer(text=f"Page {index + 1} / {len(chunks)}")
            embeds.append(embed)

        if hex_palette:
            paginator = Paginator(embeds=embeds, index=0, author=interaction.user)
            await paginator.start(interaction)
        else:
            await interaction.response.send_message(embed=embeds[0])

    @app_commands.describe(image="Convert image to grayscale.")
    @app_commands.command(
        name="grayscale", description="Convert the image to grayscale."
    )
    async def grayscale_image(
        self, interaction: discord.Interaction, image: discord.Attachment
    ) -> None:
        img = await self.read_image(image)
        img = ImageOps.grayscale(img)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        buffer.seek(0)

        file = discord.File(buffer, filename="grayscale_image.jpg")
        await interaction.response.send_message(files=[file])

    @app_commands.describe(
        image="Image to solarize.",
        threshold="All pixels above this greyscale level are inverted.",
    )
    @app_commands.command(
        name="solarize", description="Invert all pixel values above a threshold."
    )
    async def solarize_image(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        threshold: int,
    ) -> None:
        img = await self.read_image(image)
        img = ImageOps.solarize(img, threshold)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        buffer.seek(0)

        file = discord.File(buffer, filename="solarize_image.jpg")
        await interaction.response.send_message(files=[file])


async def setup(bot: LeafBot) -> None:
    await bot.add_cog(ImageCog(bot))
