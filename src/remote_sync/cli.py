from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import uvicorn

from remote_sync.server import create_app
from remote_sync.syncer import SyncClient


def _load_source_env() -> None:
    for directory in Path(__file__).resolve().parents:
        env_path = directory / ".env"
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remote-sync", description="Simple staged workspace sync over HTTP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    server_parser = subparsers.add_parser("server", help="Run the FastAPI sync server")
    server_parser.add_argument("--host", default="0.0.0.0")
    server_parser.add_argument("--port", type=int, default=8000)
    server_parser.add_argument(
        "--storage",
        default="./remote-sync-data",
        help="Directory where server workspaces and sync sessions are stored",
    )

    push_parser = subparsers.add_parser("push", help="Push a local directory to a server workspace")
    push_parser.add_argument("--server", default=None, help="Server base URL (or set REMOTE_SYNC_SERVER env var)")
    push_parser.add_argument("--workspace", required=True, help="Workspace name on the server")
    push_parser.add_argument("--source", required=True, help="Local source directory to upload")
    push_parser.add_argument("--token", default=None, help="Bearer token (or set REMOTE_SYNC_TOKEN env var)")
    push_parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")

    pull_parser = subparsers.add_parser("pull", help="Pull a workspace from the server to a local directory")
    pull_parser.add_argument("--server", default=None, help="Server base URL (or set REMOTE_SYNC_SERVER env var)")
    pull_parser.add_argument("--workspace", required=True, help="Workspace name on the server")
    pull_parser.add_argument("--dest", required=True, help="Local destination directory")
    pull_parser.add_argument("--token", default=None, help="Bearer token (or set REMOTE_SYNC_TOKEN env var)")
    pull_parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")

    return parser


def _resolve_server(args: argparse.Namespace) -> str:
    server = args.server or os.environ.get("REMOTE_SYNC_SERVER")
    if not server:
        raise SystemExit("error: --server is required (or set REMOTE_SYNC_SERVER env var)")
    return server


def _resolve_token(args: argparse.Namespace) -> str | None:
    return args.token or os.environ.get("REMOTE_SYNC_TOKEN") or None


def main() -> None:
    _load_source_env()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "server":
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
        logging.getLogger("remote_sync").setLevel(logging.INFO)
        app = create_app(Path(args.storage))
        uvicorn.run(app, host=args.host, port=args.port)
        return

    if args.command == "push":
        server = _resolve_server(args)
        token = _resolve_token(args)
        client = SyncClient(server_url=server, timeout=args.timeout, token=token)
        summary = client.sync_directory(workspace=args.workspace, source_dir=args.source)
        print(
            f"workspace={summary.workspace} session={summary.session_id} "
            f"directories={summary.directories_sent} files={summary.files_sent}"
        )
        return

    if args.command == "pull":
        server = _resolve_server(args)
        token = _resolve_token(args)
        client = SyncClient(server_url=server, timeout=args.timeout, token=token)
        summary = client.pull_workspace(workspace=args.workspace, dest_dir=args.dest)
        print(
            f"workspace={summary.workspace} "
            f"directories={summary.directories_written} files={summary.files_written}"
        )
        return

    parser.error(f"unknown command: {args.command}")
