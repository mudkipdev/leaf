# Requirements
## What you will need
- [Python/Pip](https://python.org)
- [Git](https://git-scm.com/)
- [Poetry](https://pypi.org/project/poetry/)
- [PostgreSQL](https://www.postgresql.org/download/) (optionally [pgAdmin](https://www.pgadmin.org/) to view your database with a UI)

If you do not have Poetry already installed, run the following command:
```
$ pip install poetry
```

# Installation
1. Clone the repository to a local directory.
```sh
$ git clone https://github.com/mudkipdev/leaf
$ cd leaf
```
2. Install all the dependencies using Poetry. If `poetry` is not recognized, make sure you have selected "add to PATH" when installing Python.
```sh
$ poetry install
```
That's it! You have completed the installation. Now move on to the Running and Contributing sections.

# Running
1. Once you have completed the installation, make sure you enter Poetry's virtual environment.
```sh
$ poetry shell
```
2. Now you can run the bot. Make sure the database is running as well.
```sh
$ python leaf
```

# Contributing
Create a new fork of the repository, clone it, make your changes, run `black <directory you have edited>`, and commit your changes to Git. Once you are done, create a pull request. **Do not make pull requests without opening an issue first!**
