from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from remote_sync.server import create_app
from remote_sync.syncer import SyncClient


class SyncTests(unittest.TestCase):
    def test_sync_replaces_workspace_and_keeps_empty_directories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            storage_root = tmp_path / "server-storage"
            app = create_app(storage_root)
            source_one = tmp_path / "source-one"
            source_two = tmp_path / "source-two"

            (source_one / "nested").mkdir(parents=True)
            (source_one / "empty-dir").mkdir()
            (source_one / "main.py").write_text("print('one')\n", encoding="utf-8")
            (source_one / "nested" / "util.py").write_text("value = 1\n", encoding="utf-8")

            (source_two / "nested").mkdir(parents=True)
            (source_two / "main.py").write_text("print('two')\n", encoding="utf-8")

            with TestClient(app) as test_client:
                sync_client = SyncClient(
                    server_url=str(test_client.base_url),
                    timeout=5.0,
                    http_client=test_client,
                )
                sync_client.sync_directory("project-alpha", source_one)

                workspace_root = storage_root / "workspaces" / "project-alpha"
                self.assertEqual((workspace_root / "main.py").read_text(encoding="utf-8"), "print('one')\n")
                self.assertEqual((workspace_root / "nested" / "util.py").read_text(encoding="utf-8"), "value = 1\n")
                self.assertTrue((workspace_root / "empty-dir").is_dir())

                sync_client.sync_directory("project-alpha", source_two)

                self.assertEqual((workspace_root / "main.py").read_text(encoding="utf-8"), "print('two')\n")
                self.assertFalse((workspace_root / "nested" / "util.py").exists())
                self.assertFalse((workspace_root / "empty-dir").exists())

    def test_sync_rejects_invalid_workspace_name(self) -> None:
        with TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            storage_root = tmp_path / "server-storage"
            app = create_app(storage_root)
            source = tmp_path / "source"
            source.mkdir()
            (source / "ok.py").write_text("print('ok')\n", encoding="utf-8")

            with TestClient(app) as test_client:
                sync_client = SyncClient(
                    server_url=str(test_client.base_url),
                    timeout=5.0,
                    http_client=test_client,
                )

                with self.assertRaises(ValueError):
                    sync_client.sync_directory("../bad", source)


if __name__ == "__main__":
    unittest.main()
