import argparse

import uvicorn
from mcp.server.fastmcp import FastMCP
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

HOST = "127.0.0.1"
PORT = 4202

console = Console(stderr=True)
_store = None


class StoreUnavailableError(RuntimeError):
    """The FTP backend could not be loaded."""


def get_store():
    """Return the FTP store, connecting on first use."""
    global _store
    if _store is None:
        try:
            from dotenv import load_dotenv

            from dreams.ftp import FtpStore
        except ImportError as exc:
            raise StoreUnavailableError(
                "The 'dreams' package is not importable. Install the project "
                "with `uv sync` and run the server from the project root."
            ) from exc
        load_dotenv()
        _store = FtpStore()
    return _store


mcp = FastMCP("FTP Datasets MCP", host=HOST, port=PORT)


# --- Tools ---


@mcp.tool()
def get_entry(path: str = ".") -> dict:
    """Get metadata for a file or directory on the FTP drive.

    Paths are remote FTP paths; relative ones resolve against FTP_ROOT.
    """
    return get_store().get_entry(path)


@mcp.tool()
def list_children(path: str = ".") -> list[dict]:
    """List the contents of a directory on the FTP drive."""
    return get_store().list_children(path)


@mcp.tool()
def download_file(remote_path: str, local_path: str | None = None) -> dict:
    """Download a file from the FTP drive and return its local path.

    Without a local_path the file is written to the system temp directory;
    file data never crosses the MCP envelope.
    """
    return get_store().download_file(remote_path, local_path)


@mcp.tool()
def upload_file(
    local_path: str, parent_path: str = ".", name: str | None = None
) -> dict:
    """Upload a local file into a directory on the FTP drive.

    The remote directory must already exist; name overrides the file name.
    """
    return get_store().upload_file(local_path, parent_path, name)


# --- Prompts ---


@mcp.prompt()
def archive_capture(image_path: str, parent_path: str, name: str | None = None) -> str:
    """Generate a prompt for archiving one captured image to the FTP drive."""
    name_argument = f', name="{name}"' if name else ""
    return f"""
You are archiving microscope data to an FTP drive via MCP tools.

Archive this capture:
- Local file = {image_path}
- Remote directory = {parent_path}
- Remote name = {name or "same as the local file name"}

Steps:
  1. Call get_entry(path="{parent_path}") and confirm it is a directory.
  2. Call upload_file(local_path="{image_path}", parent_path="{parent_path}"{name_argument})
  3. Call list_children(path="{parent_path}") and confirm the upload is listed
     with a non-zero size.

Report the remote path and size. Do not overwrite an existing entry of the
same name without saying so first.
"""


def main(argv: list[str] | None = None) -> None:
    """Entry point for the FTP datasets server."""
    parser = argparse.ArgumentParser(
        prog="ftp-server", description="Start the DReAMS FTP datasets server."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="server",
        choices=["server"],
        help="Serve the FTP datasets MCP server over streamable HTTP.",
    )
    parser.add_argument(
        "--no-connect",
        action="store_true",
        help=(
            "Start even if the FTP drive is unreachable (missing credentials "
            "or no network); tools error when called."
        ),
    )
    args = parser.parse_args(argv)

    if args.no_connect:
        console.print(
            "[yellow]Starting without an FTP connection[/] - tools will fail "
            "when called."
        )
    else:
        try:
            details = get_store().connect()
        except Exception as exc:
            console.print(
                Panel(
                    f"{escape(str(exc))}\n\n"
                    "Settings come from [cyan]FTP_*[/] variables - see "
                    "[cyan].env.example[/]. Re-run with [cyan]--no-connect[/] "
                    "to start the server anyway.",
                    title="[bold red]Cannot reach the FTP drive[/]",
                    border_style="red",
                )
            )
            raise SystemExit(1) from None
        console.print(
            f"[green]Connected[/] to {details['host']}:{details['port']} as "
            f"{details['user']} (root {details['root']}, "
            f"TLS {'on' if details['tls'] else 'off'})"
        )

    uvicorn.run(
        mcp.streamable_http_app(),
        host=HOST,
        port=PORT,
        timeout_graceful_shutdown=0,
    )


if __name__ == "__main__":
    main()
