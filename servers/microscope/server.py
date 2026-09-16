import argparse
import contextlib
import os
import threading
import warnings

import uvicorn
from mcp.server.fastmcp import FastMCP
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

HOST = "127.0.0.1"
PORT = 4201

console = Console(stderr=True)
_scope = None


class ScopeUnavailableError(RuntimeError):
    """The microscope backend could not be loaded."""


def get_scope():
    """Return the microscope, connecting on first use."""
    global _scope
    if _scope is None:
        try:
            with warnings.catch_warnings():
                # mmpycorex has an unescaped Windows path in a docstring.
                warnings.simplefilter("ignore", SyntaxWarning)
                from dreams.microscope import RealMicroscope
        except ImportError as exc:
            raise ScopeUnavailableError(
                "The 'dreams' package is not importable. Install the project "
                "with `uv sync` and run the server from the project root."
            ) from exc
        _scope = RealMicroscope()
    return _scope


mcp = FastMCP("Microscope MCP (Real)", host=HOST, port=PORT)


# --- Tools ---


@mcp.tool()
def snap_image() -> dict:
    """Capture an image from the microscope at the current stage position."""
    return get_scope().snap_image()


@mcp.tool()
def move_stage(x: float, y: float, z: float) -> dict:
    """Move the microscope stage to the given (x, y, z) coordinates in µm."""
    return get_scope().move_stage(x, y, z)


@mcp.tool()
def get_stage_position() -> dict:
    """Return the current stage position as {x, y, z}."""
    return get_scope().get_stage_position()


@mcp.tool()
def wait(seconds: float) -> dict:
    """Pause execution for the given number of seconds."""
    return get_scope().wait(seconds)


# --- Resources ---


@mcp.resource("microscope://latest_image", mime_type="image/png")
def latest_image() -> bytes:
    """The most recently captured image as a PNG."""
    return get_scope().get_image_png()


# --- Prompts ---


@mcp.prompt()
def tile_scan_xy(
    x_positions: list[float],
    y_positions: list[float],
    z: float,
    delay_seconds: float = 1.0,
) -> str:
    """Generate a prompt for a 2D tile scan at fixed Z."""
    return f"""
You are controlling a microscope via MCP tools.

Run a tiled XY acquisition:
- Fixed Z = {z}
- Delay between tiles = {delay_seconds}s
- X positions: {x_positions}
- Y positions: {y_positions}

For each y in Y positions, for each x in X positions:
  1. Call move_stage(x=x, y=y, z={z})
  2. Call snap_image()
  3. Call wait(seconds={delay_seconds})

Do not skip any positions. Report progress after each tile.
"""


@contextlib.contextmanager
def _quiet_bridge_threads():
    """Swallow pycromanager socket-thread tracebacks while probing."""
    previous = threading.excepthook

    def hook(args):
        thread = getattr(args, "thread", None)
        if thread is not None and thread.name.startswith("BridgeSocketThread"):
            return
        previous(args)

    threading.excepthook = hook
    try:
        yield
    finally:
        threading.excepthook = previous


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``start`` console script."""
    parser = argparse.ArgumentParser(prog="start", description="Start a DReAMS server.")
    parser.add_argument(
        "command",
        nargs="?",
        default="server",
        choices=["server"],
        help="Serve the microscope MCP server over streamable HTTP.",
    )
    parser.add_argument(
        "--no-scope",
        action="store_true",
        help=(
            "Start even if the microscope is unavailable (missing 'dreams' "
            "package or no Micro-Manager); tools error when called."
        ),
    )
    args = parser.parse_args(argv)

    if args.no_scope:
        console.print(
            "[yellow]Starting without a microscope[/] - tools will fail when called."
        )
    else:
        try:
            with _quiet_bridge_threads():
                get_scope()
        except Exception as exc:
            console.print(
                Panel(
                    f"{escape(str(exc))}\n\n"
                    "Start Micro-Manager with [cyan]Tools -> Options -> Run server on port 4827[/]\n"
                    "enabled, or re-run with [cyan]--no-scope[/] to start the server anyway.",
                    title="[bold red]Cannot reach the microscope[/]",
                    border_style="red",
                )
            )
            # pycromanager leaves daemon socket threads behind on a failed
            # connect; a normal exit deadlocks on them during finalization.
            os._exit(1)

    uvicorn.run(
        mcp.streamable_http_app(),
        host=HOST,
        port=PORT,
        timeout_graceful_shutdown=0,
    )


if __name__ == "__main__":
    main()
