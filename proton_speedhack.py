#!/usr/bin/env python3
# Proton SpeedHack configuration resolution.
#
# Resolves the user facing SpeedHack configuration (environment variables and
# JSON files) into the internal PROTON_SPEEDHACK_* variables consumed by
# Proton's steam.exe helper (see steam_helper/steam.c).
#
# Lookup order, the first valid value found for each setting wins:
#   1. SPEEDHACK_SPEED / SPEEDHACK_TOGGLE / SPEEDHACK_KEYS environment variables
#   2. ~/.speedhack/<SteamGameId>.json
#   3. ~/.speedhack/speedhack.json
#   4. <proton install dir>/speedhack.json
#   5. built-in defaults (2.5x, hold mode, Page Up)

import json
import os

DEFAULT_SPEED = 2.5
DEFAULT_TOGGLE = False
DEFAULT_KEYS = "page_up"

MIN_SPEED = 0.01
MAX_SPEED = 100.0
MAX_KEYS = 4

# Key names to Windows virtual key codes.
KEYCODES = {
    "back": 0x08, "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "control": 0x11, "ctrl": 0x11, "alt": 0x12, "pause": 0x13,
    "caps_lock": 0x14, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "page_up": 0x21, "page_down": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
    "left_win": 0x5B, "right_win": 0x5C,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64,
    "num5": 0x65, "num6": 0x66, "num7": 0x67, "num8": 0x68, "num9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "separator": 0x6C, "subtract": 0x6D,
    "decimal": 0x6E, "divide": 0x6F,
    "numlock": 0x90, "scroll_lock": 0x91,
    "left_shift": 0xA0, "right_shift": 0xA1, "left_control": 0xA2,
    "right_control": 0xA3, "left_alt": 0xA4, "right_alt": 0xA5,
    "semicolon": 0xBA, "plus": 0xBB, "comma": 0xBC, "minus": 0xBD,
    "period": 0xBE, "forward_slash": 0xBF, "tilde": 0xC0,
    "left_bracket": 0xDB, "back_slash": 0xDC, "right_bracket": 0xDD,
    "quote": 0xDE,
}
KEYCODES.update({str(i): 0x30 + i for i in range(10)})
KEYCODES.update({chr(ord("a") + i): 0x41 + i for i in range(26)})
KEYCODES.update({"f" + str(i): 0x6F + i for i in range(1, 25)})


def parse_speed(value):
    if isinstance(value, bool):
        return None
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return None
    if not MIN_SPEED <= speed <= MAX_SPEED:
        return None
    return speed


def parse_toggle(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("0", "1", "true", "false"):
        return value.strip().lower() in ("1", "true")
    return None


def parse_keys(value):
    """Returns a list of virtual key codes, an empty list to disable the hotkey,
    or None if the value is invalid."""
    if isinstance(value, list):
        names = value
    elif isinstance(value, str):
        names = value.split(",")
    else:
        return None
    names = [str(n).strip().lower() for n in names if str(n).strip()]
    if len(names) > MAX_KEYS:
        return None
    codes = []
    for name in names:
        if name in KEYCODES:
            codes.append(KEYCODES[name])
            continue
        try:
            # plain decimal first: int(x, 0) rejects leading zeros such as "08"
            code = int(name, 10) if name.isdigit() else int(name, 0)
        except ValueError:
            return None
        if not 0 < code < 0xFF:
            return None
        codes.append(code)
    return codes


PARSERS = {"speed": parse_speed, "toggle": parse_toggle, "keys": parse_keys}


def read_config_file(path, log):
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        log("SpeedHack: failed to read " + path + ": " + str(e))
        return {}
    if not isinstance(data, dict):
        log("SpeedHack: ignoring " + path + ": not a JSON object")
        return {}
    # The original Proton SpeedHack documented "keys" but read "key".
    if "keys" not in data and "key" in data:
        data["keys"] = data["key"]
    return {k: data[k] for k in PARSERS if k in data}


def resolve_config(env, install_dir, log=lambda msg: None):
    sources = []
    env_config = {}
    for name in PARSERS:
        var = "SPEEDHACK_" + name.upper()
        if var in env:
            env_config[name] = env[var]
    sources.append(("environment", env_config))

    home = "~/.speedhack/"
    game_id = env.get("SteamGameId")
    if game_id:
        sources.append((home + game_id + ".json", read_config_file(home + game_id + ".json", log)))
    sources.append((home + "speedhack.json", read_config_file(home + "speedhack.json", log)))
    if install_dir:
        path = os.path.join(install_dir, "speedhack.json")
        sources.append((path, read_config_file(path, log)))

    result = {"speed": DEFAULT_SPEED, "toggle": DEFAULT_TOGGLE, "keys": parse_keys(DEFAULT_KEYS)}
    for name, parser in PARSERS.items():
        for source, config in sources:
            if name not in config:
                continue
            value = parser(config[name])
            if value is None:
                log("SpeedHack: ignoring invalid " + name + " " + repr(config[name]) + " from " + source)
                continue
            result[name] = value
            log("SpeedHack: using " + name + " from " + source)
            break
    return result


def speedhack_env(env, install_dir, log=lambda msg: None):
    """Returns the PROTON_SPEEDHACK_* variables for steam.exe."""
    config = resolve_config(env, install_dir, log)
    keys = ",".join("0x%02x" % k for k in config["keys"])
    out = {
        "PROTON_SPEEDHACK_MULTIPLIER": str(int(round(config["speed"] * 1000))),
        "PROTON_SPEEDHACK_TOGGLE": "1" if config["toggle"] else "0",
        "PROTON_SPEEDHACK_KEYS": keys,
    }
    log("SpeedHack: speed " + str(config["speed"]) + ", " +
        ("toggle" if config["toggle"] else "hold") + " mode, keys " + (keys or "(disabled)"))
    return out


if __name__ == "__main__":
    import sys
    for k, v in speedhack_env(os.environ, os.path.dirname(os.path.abspath(sys.argv[0])),
                              lambda msg: print(msg, file=sys.stderr)).items():
        print(k + "=" + v)
