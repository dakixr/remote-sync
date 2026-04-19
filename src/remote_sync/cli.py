from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from remote_sync.server import create_app
from remote_sync.syncer import SyncClient


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

    sync_parser = subparsers.add_parser("sync", help="Sync a local directory to a server workspace")
    sync_parser.add_argument("--server", required=True, help="Server base URL, for example http://127.0.0.1:8000")
    sync_parser.add_argument("--workspace", required=True, help="Workspace name on the server")
    sync_parser.add_argument("--source", required=True, help="Local source directory to upload")
    sync_parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "server":
        app = create_app(Path(args.storage))
        uvicorn.run(app, host=args.host, port=args.port)
        return

    if args.command == "sync":
        client = SyncClient(server_url=args.server, timeout=args.timeout)
        summary = client.sync_directory(workspace=args.workspace, source_dir=args.source)
        print(
            f"workspace={summary.workspace} session={summary.session_id} "
            f"directories={summary.directories_sent} files={summary.files_sent}"
        )
        return

    parser.error(f"unknown command: {args.command}")
