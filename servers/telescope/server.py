import importlib
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

for parent in Path(__file__).resolve().parents:
    if (parent / "dreams").is_dir() and (parent / "pyproject.toml").is_file():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break

_telescope = importlib.import_module("dreams.telescope")
Telescope = _telescope.Telescope

scope = Telescope()
HOST = "127.0.0.1"
PORT = 4203

mcp = FastMCP("Telescope MCP (Real)", host=HOST, port=PORT)


# --- Tools ---


@mcp.tool()
def move_stage(x: float, y: float, z: float) -> dict:
    return scope.move_stage(x, y, z)


@mcp.tool()
def get_stage_position() -> dict:
    return scope.get_stage_position()


# --- Resources ---


# --- Prompts ---


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        mcp.streamable_http_app(),
        host=HOST,
        port=PORT,
        timeout_graceful_shutdown=0,
    )
