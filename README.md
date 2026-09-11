# 🔬 DReAMS

**Data-Reactive Acquisition and Microscope Steering** — bringing AI to the microscope.

Smart microscopes adapt acquisition to the sample in real time: content-aware
illumination, ML-based denoising, adaptive optics, and event-driven capture that
adjusts focus, field of view, and frame rate on the fly. DReAMS exposes a real
microscope to an LLM agent over MCP, so the agent can observe, decide, and steer
the acquisition itself.

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Micro-Manager 2.0 running with the ZMQ server enabled (default port 4827);
  `pycromanager` bridges Python to its Java core

## Setup

```
uv sync
```

## Run

```
uv run servers/microscope/server.py
```

Serves streamable-HTTP MCP at `http://127.0.0.1:4201/mcp`.

## Connect an agent

Point any MCP client at that URL. A GitHub Copilot CLI config is included:

```
cd workers/copilot
./copilot-with-mcp.ps1
```

## MCP surface

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

## Layout

```
dreams/microscope/   backend: RealMicroscope (pycromanager) + PNG helpers
servers/microscope/  MCP server (streamable HTTP, :4201)
workers/copilot/     Copilot CLI client config
```
