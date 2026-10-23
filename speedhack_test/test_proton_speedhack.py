#!/usr/bin/env python3
# Unit tests for proton_speedhack.py (source-level, no Wine needed).
#   python3 speedhack_test/test_proton_speedhack.py

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import proton_speedhack as ps  # noqa: E402


class SpeedhackConfigTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.install = tempfile.TemporaryDirectory()
        os.mkdir(os.path.join(self.home.name, ".speedhack"))
        patcher = mock.patch.dict(os.environ, {"HOME": self.home.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.home.cleanup)
        self.addCleanup(self.install.cleanup)

    def write(self, path, data):
        with open(path, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def env(self, env):
        return ps.speedhack_env(env, self.install.name)

    def test_defaults(self):
        self.assertEqual(self.env({}), {
            "PROTON_SPEEDHACK_MULTIPLIER": "2500",
            "PROTON_SPEEDHACK_TOGGLE": "0",
            "PROTON_SPEEDHACK_KEYS": "0x21",
        })

    def test_environment(self):
        out = self.env({"SPEEDHACK_SPEED": "3", "SPEEDHACK_TOGGLE": "1",
                        "SPEEDHACK_KEYS": "ctrl, F12"})
        self.assertEqual(out["PROTON_SPEEDHACK_MULTIPLIER"], "3000")
        self.assertEqual(out["PROTON_SPEEDHACK_TOGGLE"], "1")
        self.assertEqual(out["PROTON_SPEEDHACK_KEYS"], "0x11,0x7b")

    def test_letters(self):
        # The original implementation mapped k..n to wrong codes.
        out = self.env({"SPEEDHACK_KEYS": "k,l,m,n"})
        self.assertEqual(out["PROTON_SPEEDHACK_KEYS"], "0x4b,0x4c,0x4d,0x4e")

    def test_numeric_keys_and_disable(self):
        self.assertEqual(self.env({"SPEEDHACK_KEYS": "0x70"})["PROTON_SPEEDHACK_KEYS"], "0x70")
        self.assertEqual(self.env({"SPEEDHACK_KEYS": "112"})["PROTON_SPEEDHACK_KEYS"], "0x70")
        self.assertEqual(self.env({"SPEEDHACK_KEYS": "08,010"})["PROTON_SPEEDHACK_KEYS"], "0x08,0x0a")
        self.assertEqual(self.env({"SPEEDHACK_KEYS": ""})["PROTON_SPEEDHACK_KEYS"], "")

    def test_invalid_values_fall_back(self):
        out = self.env({"SPEEDHACK_SPEED": "1000", "SPEEDHACK_TOGGLE": "maybe",
                        "SPEEDHACK_KEYS": "a,b,c,d,e"})
        self.assertEqual(out["PROTON_SPEEDHACK_MULTIPLIER"], "2500")
        self.assertEqual(out["PROTON_SPEEDHACK_TOGGLE"], "0")
        self.assertEqual(out["PROTON_SPEEDHACK_KEYS"], "0x21")
        self.assertEqual(self.env({"SPEEDHACK_KEYS": "nokey"})["PROTON_SPEEDHACK_KEYS"], "0x21")

    def test_file_precedence(self):
        d = os.path.join(self.home.name, ".speedhack")
        self.write(os.path.join(self.install.name, "speedhack.json"),
                   {"speed": 1.5, "toggle": 1, "keys": "home"})
        self.write(os.path.join(d, "speedhack.json"), {"speed": 2, "key": "end"})
        self.write(os.path.join(d, "123.json"), {"speed": 4})
        out = self.env({"SteamGameId": "123"})
        self.assertEqual(out["PROTON_SPEEDHACK_MULTIPLIER"], "4000")  # per game
        self.assertEqual(out["PROTON_SPEEDHACK_KEYS"], "0x23")        # global, "key" alias
        self.assertEqual(out["PROTON_SPEEDHACK_TOGGLE"], "1")         # install dir
        out = self.env({"SteamGameId": "123", "SPEEDHACK_SPEED": "0.5"})
        self.assertEqual(out["PROTON_SPEEDHACK_MULTIPLIER"], "500")

    def test_bad_json_ignored(self):
        self.write(os.path.join(self.home.name, ".speedhack", "speedhack.json"), "{not json")
        self.write(os.path.join(self.install.name, "speedhack.json"), "[1, 2]")
        self.assertEqual(self.env({})["PROTON_SPEEDHACK_MULTIPLIER"], "2500")

    def test_shipped_default_config(self):
        top = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        out = ps.speedhack_env({}, top)
        self.assertEqual(out["PROTON_SPEEDHACK_MULTIPLIER"], "2500")
        self.assertEqual(out["PROTON_SPEEDHACK_KEYS"], "0x21")


if __name__ == "__main__":
    unittest.main()
