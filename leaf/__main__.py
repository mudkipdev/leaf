import tomllib
from bot import LeafBot


def main() -> None:
    with open("config.toml", "rb") as config_file:
        config = tomllib.load(config_file)

    bot = LeafBot(config)
    bot.run(config["token"])


if __name__ == "__main__":
    main()
