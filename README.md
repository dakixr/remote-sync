# remote-sync

`remote-sync` is a small Python client/server tool for mirroring a local code directory to a remote machine over HTTP.

It is intentionally simple:

- The server exposes a FastAPI API.
- The client performs a full rescan on every run.
- Files are uploaded one by one with `POST /upload`.
- Empty directories are preserved.
- The server always makes the workspace match the client exactly.

## Protocol

The API uses a single endpoint:

- `POST /upload`

The client sends four operation types:

- `begin`: create a temporary staging area for a workspace sync session
- `mkdir`: create an empty directory in the staging area
- `file`: upload a single file into the staging area
- `finish`: atomically replace the live workspace with the staging area

This staged approach mirrors deletions automatically because the final `finish` swaps the old workspace out for the newly uploaded one.

## Install

```bash
uv sync
```

## Run the server

```bash
uv run remote-sync server --host 0.0.0.0 --port 8000 --storage ./remote-sync-data
```

The server stores synchronized workspaces under:

```text
./remote-sync-data/workspaces/<workspace-name>
```

## Expose the server through Cloudflare Tunnel

Start the API locally first:

```bash
uv run remote-sync server --host 127.0.0.1 --port 8000 --storage ./remote-sync-data
```

In a second terminal, start a quick Cloudflare tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

`cloudflared` will print a public `https://<random-name>.trycloudflare.com` URL. You can verify the API is reachable through the tunnel with:

```bash
curl https://<random-name>.trycloudflare.com/health
```

Expected response:

```json
{"status":"ok"}
```

Then point the client at the public tunnel URL:

```bash
uv run remote-sync sync \
  --server https://<random-name>.trycloudflare.com \
  --workspace my-project \
  --source /path/to/local/project
```

For production use, prefer a named Cloudflare tunnel instead of a temporary quick tunnel.

## Run a sync

```bash
uv run remote-sync sync \
  --server http://127.0.0.1:8000 \
  --workspace my-project \
  --source /path/to/local/project
```

## Notes

- Workspace names cannot contain path separators.
- Relative file paths are preserved exactly under the workspace root.
- The implementation works for text files and other file bytes as well, even though the original use case is code sync.
