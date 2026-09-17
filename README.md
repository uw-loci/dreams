# 🔬 DReAMS

**Data-Reactive Acquisition and Microscope Steering** — bringing AI to the microscope.

Smart microscopes adapt acquisition to the sample in real time: content-aware
illumination, ML-based denoising, adaptive optics, and event-driven capture that
adjusts focus, field of view, and frame rate on the fly. DReAMS exposes a real
microscope to an LLM agent over MCP, so the agent can observe, decide, and steer
the acquisition itself.

Two MCP servers ship here: one steers the microscope, one archives what it
captures to the lab FTP drive.

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Micro-Manager 2.0 running with the ZMQ server enabled (default port 4827);
  `pycromanager` bridges Python to its Java core
- An account on `ftp.microscopy.wisc.edu` for the FTP datasets server

## Setup

```
uv sync
```

For the FTP datasets server, copy `.env.example` to `.env` (gitignored) and fill
in `FTP_USER` and `FTP_PASSWORD`.

## Run

```
uv run servers/microscope/server.py     # http://127.0.0.1:4201/mcp
uv run servers/ftp/server.py            # http://127.0.0.1:4202/mcp
```

Both serve streamable-HTTP MCP. Each checks its backend at startup and prints
what went wrong instead of serving dead tools; pass `--no-scope` / `--no-connect`
to start anyway.

## Connect an agent

Point any MCP client at those URLs. A GitHub Copilot CLI config is included:

```
cd workers/copilot
./copilot-with-mcp.ps1
```

## MCP surface

### Microscope — `servers/microscope/server.py`

| Kind | Name | Signature |
|---|---|---|
| tool | `snap_image` | `() -> dict` |
| tool | `move_stage` | `(x, y, z: float) -> dict` — µm |
| tool | `get_stage_position` | `() -> dict` |
| tool | `wait` | `(seconds: float) -> dict` |
| resource | `microscope://latest_image` | PNG bytes |
| prompt | `tile_scan_xy` | `(x_positions, y_positions, z, delay_seconds=1.0)` |

`snap_image` writes a PNG to the system temp directory and returns the path in
its JSON result — image data never crosses the MCP envelope.

### FTP datasets — `servers/ftp/server.py`

| Kind | Name | Signature |
|---|---|---|
| tool | `get_entry` | `(path=".") -> dict` — type, size, mtime |
| tool | `list_children` | `(path=".") -> list[dict]` |
| tool | `download_file` | `(remote_path, local_path=None) -> dict` |
| tool | `upload_file` | `(local_path, parent_path=".", name=None) -> dict` |
| prompt | `archive_capture` | `(image_path, parent_path, name=None)` |

Same four actions as the Synapse datasets MCP it replaces, against an FTP drive
instead. Like `snap_image`, file bytes never cross the MCP envelope: downloads
land in the system temp directory (or `local_path`) and the tool returns the
path. Relative paths resolve against `FTP_ROOT`; absolute ones are used as
given. `upload_file` needs the remote directory to exist already.

Settings come from the environment (or `.env`), defaults shown:

| Variable | Default | |
|---|---|---|
| `FTP_USER` / `FTP_PASSWORD` | — | required |
| `FTP_HOST` | `ftp.microscopy.wisc.edu` | |
| `FTP_PORT` | `21` | |
| `FTP_ROOT` | `/` | relative paths resolve here |
| `FTP_TLS` | `1` | explicit FTPS (`AUTH TLS`), data channel encrypted |
| `FTP_PASSIVE` | `1` | |
| `FTP_TIMEOUT` | `30` | seconds |

`ftp.microscopy.wisc.edu` supports `AUTH TLS`, so credentials and data stay
encrypted by default; set `FTP_TLS=0` only for a server that cannot do FTPS.

## Layout

```
dreams/microscope/   backend: RealMicroscope (pycromanager) + PNG helpers
dreams/ftp/          backend: FtpStore (ftplib, FTPS by default)
servers/microscope/  MCP server (streamable HTTP, :4201)
servers/ftp/         MCP server (streamable HTTP, :4202)
workers/copilot/     Copilot CLI client config
```
