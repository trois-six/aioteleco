# Contributing to aioteleco

Thanks for your interest! Bug reports from real installations, fixes and new device
support are all welcome.

## Development setup

The project uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/trois-six/aioteleco.git
cd aioteleco
uv sync                  # creates .venv with the dev dependencies
uvx prek install         # git hooks (or: pre-commit install)
```

Before pushing, run the same checks as the CI:

```bash
uv run pytest            # unit tests, no network
uv run ruff check        # lint
uv run ruff format       # format
uv run mypy              # strict type checking
```

The documentation site is built with MkDocs:

```bash
uv run --group docs mkdocs serve             # live preview on http://127.0.0.1:8000
uv run --group docs mkdocs build --strict    # what the CI runs
```

The API reference is generated from the docstrings, so document public classes and
methods there. `docs/protocol/` is an OKF v0.2 bundle: keep the YAML front matter of
each note and the index in `docs/protocol/index.md` up to date.

## Commits and pull requests

* Commit messages and pull request titles follow
  [Conventional Commits](https://www.conventionalcommits.org/): `feat: …`, `fix: …`,
  `docs: …`, `test: …`, `ci: …`, `chore: …`, with an optional scope such as
  `feat(timers): …`. Use `!` or a `BREAKING CHANGE:` footer for breaking changes.
* Keep pull requests focused, add or update tests, and update the documentation (README,
  docs, protocol notes) when behaviour changes.

## Testing safely

The SDK drives **motorised equipment and a real home-automation box**.

* **Never test destructive commands on a real installation**: unpairing or resetting
  remotes, deleting rooms, scenarios or timers, firmware updates, Wi-Fi or access-point
  changes, memory reads, box time changes… Exercise them against the fake cloud and the
  fake box of the test suite (`tests/conftest.py`) instead.
* When you do try a command on your own equipment, keep it in sight and start with
  harmless, reversible actions (stop, read status).
* Tests must not reach the network. Tests that talk to a real cloud or box are marked
  `live` and are deselected by default.

## What must never be committed

* Credentials, session ids, installation codes, real email addresses, real IP addresses
  or SSIDs: use `me@example.com` and documentation addresses (`192.0.2.0/24`) in
  examples and fixtures, and anonymise captured payloads before adding them to
  `tests/fixtures/`.
* `.env` files or any local configuration (`~/.config/aioteleco/config.toml`).
* Decompiled or disassembled sources of the official apps, APKs, or large excerpts of
  them. Describe behaviour in your own words in the protocol notes instead.

## Reporting bugs

Open an issue with the bug report template and attach the output of `teleco diagnose`
(anonymised). For security issues, see [SECURITY.md](SECURITY.md).
