"""Check the FTP drive from the settings in .env.

    uv run dreams/ftp/test-ftp-conn.py                 # read-only checks
    uv run dreams/ftp/test-ftp-conn.py --path ecm      # start from a subfolder
    uv run dreams/ftp/test-ftp-conn.py --round-trip    # also upload, verify, delete

Read-only by default: it logs in, reports what the server supports, and lists a
directory. --round-trip additionally writes a small file to the drive, reads it
back, and deletes it again.
"""

import argparse
import sys
import tempfile
from ftplib import FTP_TLS
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dreams.ftp import FtpConfigError, FtpError, FtpSettings, FtpStore  # noqa: E402

console = Console()
PROBE_NAME = "dreams_ftp_probe.txt"
PROBE_BODY = b"DReAMS FTP connection check - safe to delete.\n"


def show_settings(settings: FtpSettings) -> None:
    table = Table(title="Settings", title_justify="left", show_header=False)
    table.add_column(style="cyan")
    table.add_column()
    table.add_row("host", f"{settings.host}:{settings.port}")
    table.add_row("user", settings.user)
    table.add_row("password", "•" * 8 if settings.password else "[red]not set[/]")
    table.add_row("root", settings.root)
    table.add_row("tls", "explicit FTPS" if settings.use_tls else "[yellow]off[/]")
    table.add_row("passive", str(settings.passive))
    table.add_row("timeout", f"{settings.timeout:g}s")
    console.print(table)


def report(label: str, ok: bool, detail: str = "") -> bool:
    mark = "[green]ok  [/]" if ok else "[red]FAIL[/]"
    console.print(f"{mark} {label}" + (f"  [dim]{detail}[/]" if detail else ""))
    return ok


def check_features(store: FtpStore) -> None:
    """Report the optional commands this server advertises."""
    try:
        feat = store._run(lambda ftp: ftp.sendcmd("FEAT"))
    except Exception as exc:  # noqa: BLE001 - FEAT is optional
        report("FEAT", False, str(exc))
        return
    advertised = {line.strip().split()[0].upper() for line in feat.splitlines()[1:-1]}
    for command, why in [
        ("AUTH", "encrypted control channel"),
        ("MLST", "get_entry metadata"),
        ("MLSD", "list_children metadata"),
    ]:
        supported = command in advertised
        note = why if supported else f"absent - {why} falls back to SIZE/MDTM/NLST"
        report(f"supports {command}", supported, note)


def round_trip(store: FtpStore, path: str) -> bool:
    """Upload a small file, read it back, and delete it again."""
    local = Path(tempfile.mkdtemp()) / PROBE_NAME
    local.write_bytes(PROBE_BODY)
    remote = None
    ok = True
    try:
        result = store.upload_file(str(local), path)
        remote = result["remote_path"]
        ok &= report("upload_file", result["size"] == len(PROBE_BODY), remote)

        entry = store.get_entry(remote)
        ok &= report("get_entry on upload", entry["type"] == "file", str(entry))

        listed = [child["name"] for child in store.list_children(path)]
        ok &= report("appears in listing", PROBE_NAME in listed)

        back = store.download_file(remote, str(local.with_suffix(".back")))
        same = Path(back["local_path"]).read_bytes() == PROBE_BODY
        ok &= report("download round-trip", same, back["local_path"])
    except (FtpError, OSError) as exc:
        return report("round-trip", False, str(exc))
    finally:
        if remote is not None:
            try:
                store._run(lambda ftp: ftp.delete(remote))
                report("cleaned up", True, remote)
            except Exception as exc:  # noqa: BLE001 - report, never mask the result
                report("cleaned up", False, f"{remote} still on the drive - {exc}")
                ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--path",
        default=".",
        help="Remote directory to inspect (default: FTP_ROOT).",
    )
    parser.add_argument(
        "--round-trip",
        action="store_true",
        help="Also upload a small probe file, read it back, and delete it.",
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Entries to print (default: 10)."
    )
    args = parser.parse_args()

    load_dotenv()
    try:
        settings = FtpSettings.from_env()
    except FtpConfigError as exc:
        console.print(f"[red]{exc}[/]")
        return 1
    show_settings(settings)

    store = FtpStore(settings)
    ok = True
    try:
        try:
            details = store.connect()
        except FtpConfigError as exc:
            report("login", False, str(exc))
            return 1
        report("login", True, details["welcome"])
        encrypted = isinstance(store._run(lambda ftp: ftp), FTP_TLS)
        report(
            "encrypted",
            encrypted,
            "control and data channels" if encrypted else "FTP_TLS=0, plaintext",
        )
        check_features(store)

        try:
            entry = store.get_entry(args.path)
            ok &= report("get_entry", entry["type"] == "dir", entry["path"])
            children = store.list_children(args.path)
        except FtpError as exc:
            return 0 if report("list_children", False, str(exc)) else 1
        ok &= report("list_children", True, f"{len(children)} entries")

        if children:
            table = Table(title=f"{entry['path']}", title_justify="left")
            table.add_column("name")
            table.add_column("type")
            table.add_column("size", justify="right")
            table.add_column("modified")
            for child in children[: args.limit]:
                size = "" if child["size"] is None else f"{child['size']:,}"
                table.add_row(
                    child["name"], child["type"], size, child["modified"] or ""
                )
            console.print(table)
            if len(children) > args.limit:
                console.print(f"[dim]... {len(children) - args.limit} more[/]")

        if args.round_trip:
            console.rule("[bold]write round-trip[/]")
            ok &= round_trip(store, args.path)
        else:
            console.print(
                "[dim]Read-only checks. Re-run with --round-trip to test writing.[/]"
            )
    finally:
        store.close()

    console.print()
    console.print(
        "[green]All checks passed.[/]" if ok else "[red]Some checks failed.[/]"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
