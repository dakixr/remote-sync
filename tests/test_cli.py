from __future__ import annotations

import argparse
import os
import unittest
from unittest.mock import patch

from remote_sync.cli import _resolve_server, _resolve_token


class CliEnvTests(unittest.TestCase):
    def test_resolves_server_and_token_from_env(self) -> None:
        args = argparse.Namespace(server=None, token=None)

        with patch.dict(
            os.environ,
            {
                "REMOTE_SYNC_SERVER": "https://rsync.antoniapavel.com",
                "REMOTE_SYNC_TOKEN": "secret-token",
            },
            clear=True,
        ):
            self.assertEqual(_resolve_server(args), "https://rsync.antoniapavel.com")
            self.assertEqual(_resolve_token(args), "secret-token")

    def test_cli_flags_override_env(self) -> None:
        args = argparse.Namespace(server="https://override.example", token="override-token")

        with patch.dict(
            os.environ,
            {
                "REMOTE_SYNC_SERVER": "https://rsync.antoniapavel.com",
                "REMOTE_SYNC_TOKEN": "secret-token",
            },
            clear=True,
        ):
            self.assertEqual(_resolve_server(args), "https://override.example")
            self.assertEqual(_resolve_token(args), "override-token")


if __name__ == "__main__":
    unittest.main()
