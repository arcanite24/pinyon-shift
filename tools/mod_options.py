"""Mod options: choices a mod declares in its mod.toml and the player picks in the
launcher's Mods view, filled into the mod's database scripts (docs/MODDING.md,
"Options").

A mod declares each option as an [[option]] table, after its other keys:

    [[option]]
    key = "pace"
    title = "Career pace"
    description = "How fast credits, XP and wristbands come."
    default = "2"
    choices = [{ value = "0.5", label = "Half (harder)" }, { value = "2", label = "Double" }]

and writes {{pace}} where the chosen value goes in its db/*.sql. The choices are
kept in <state>/config/mod_options.json, a file only these tools read: the game
never sees options, and a mod without [[option]] tables is built exactly as
before, its scripts untouched.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")
# A choice's value is written into SQL, so it is kept to plain tokens: numbers,
# words and identifiers, never quotes, spaces or semicolons.
VALUE = re.compile(r"[A-Za-z0-9_.+-]{1,32}")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
OPTION_LIMIT = 8
CHOICE_LIMIT = 16
FILE = "mod_options.json"


class OptionError(ValueError):
    pass


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class Option:
    key: str
    title: str
    description: str
    default: str
    choices: tuple[Choice, ...]


def _text(table: dict, key: str, limit: int) -> str:
    value = table.get(key, "")
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def declared(manifest: dict) -> list[Option]:
    """The options a parsed mod.toml declares; [] when it has none. A malformed
    declaration raises OptionError with what is wrong."""
    tables = manifest.get("option", [])
    if tables == []:
        return []
    if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
        raise OptionError("options must be [[option]] tables")
    if len(tables) > OPTION_LIMIT:
        raise OptionError(f"a mod has at most {OPTION_LIMIT} options")
    options, keys = [], set()
    for table in tables:
        key = table.get("key")
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise OptionError("an option's key is lower-case letters, digits and _, starting with a letter")
        if key in keys:
            raise OptionError(f"option {key} is declared twice")
        keys.add(key)
        raw = table.get("choices")
        if not isinstance(raw, list) or not raw or len(raw) > CHOICE_LIMIT:
            raise OptionError(f"option {key} needs 1 to {CHOICE_LIMIT} choices")
        choices = []
        for entry in raw:
            value, label = (entry, entry) if isinstance(entry, str) else (
                (entry.get("value"), entry.get("label", entry.get("value")))
                if isinstance(entry, dict) else (None, None))
            if not isinstance(value, str) or not VALUE.fullmatch(value):
                raise OptionError(f"option {key} has a choice that is not a plain value "
                                  "(letters, digits, . _ + -)")
            if not isinstance(label, str) or not label.strip():
                label = value
            if any(c.value == value for c in choices):
                raise OptionError(f"option {key} lists {value} twice")
            choices.append(Choice(value, " ".join(label.split())[:60]))
        default = table.get("default", choices[0].value)
        if not any(c.value == default for c in choices):
            raise OptionError(f"option {key}'s default is not one of its choices")
        options.append(Option(key, _text(table, "title", 80) or key,
                              _text(table, "description", 400), default, tuple(choices)))
    return options


def read_declared(mod: Path) -> list[Option]:
    try:
        manifest = tomllib.loads((mod / "mod.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise OptionError(f"mod.toml cannot be read: {error}") from None
    return declared(manifest)


def _stored(state: Path) -> dict:
    path = state / "config" / FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def chosen(state: Path, mod: str, options: list[Option]) -> dict[str, str]:
    """Each option's value for the mod: the player's choice while it is still
    one the mod offers, otherwise the mod's default."""
    picked = _stored(state).get(mod, {})
    picked = picked if isinstance(picked, dict) else {}
    values = {}
    for option in options:
        value = picked.get(option.key)
        values[option.key] = value if any(c.value == value for c in option.choices) else option.default
    return values


def choose(state: Path, mod: str, options: list[Option], key: str, value: str) -> None:
    option = next((o for o in options if o.key == key), None)
    if option is None:
        raise OptionError(f"{mod} has no option {key}")
    if not any(c.value == value for c in option.choices):
        raise OptionError(f"{value} is not a choice of {mod}'s {option.title}")
    data = _stored(state)
    entry = data.get(mod) if isinstance(data.get(mod), dict) else {}
    entry[key] = value
    data[mod] = entry
    path = state / "config" / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def fill(text: str, values: dict[str, str], where: str) -> str:
    """The script with each {{key}} replaced by its value. A placeholder the mod
    does not declare is refused, so a typo cannot reach the database."""
    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise OptionError(f"{where} uses {{{{{key}}}}}, which is not one of the mod's options")
        return values[key]
    return PLACEHOLDER.sub(replace, text)
