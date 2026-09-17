import os
import posixpath
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from ftplib import FTP, FTP_TLS, all_errors, error_perm

DEFAULT_HOST = "ftp.microscopy.wisc.edu"
DEFAULT_PORT = 21
DEFAULT_TIMEOUT = 30.0

# Replies that mean "this server has no such command", as opposed to a reply
# about the path. 501 is excluded: servers also use it for a missing path.
UNSUPPORTED_REPLIES = ("500", "502")


class FtpConfigError(RuntimeError):
    """Credentials or connection settings are missing or unusable."""


class FtpError(RuntimeError):
    """The FTP server rejected a request."""


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FtpSettings:
    """Connection settings for the FTP drive."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    user: str = ""
    password: str = ""
    root: str = "/"
    use_tls: bool = True
    passive: bool = True
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> "FtpSettings":
        """Build settings from FTP_* environment variables (or a .env file)."""
        user = os.environ.get("FTP_USER", "")
        password = os.environ.get("FTP_PASSWORD", "")
        if not user or not password:
            raise FtpConfigError(
                "FTP_USER and FTP_PASSWORD are not set. Put them in a .env file "
                "at the project root (it is gitignored) or export them in the "
                "shell before starting the server."
            )
        root = os.environ.get("FTP_ROOT", "/").strip() or "/"
        return cls(
            host=os.environ.get("FTP_HOST", DEFAULT_HOST),
            port=int(os.environ.get("FTP_PORT", DEFAULT_PORT)),
            user=user,
            password=password,
            root=root if root.startswith("/") else "/" + root,
            use_tls=_env_flag("FTP_TLS", True),
            passive=_env_flag("FTP_PASSIVE", True),
            timeout=float(os.environ.get("FTP_TIMEOUT", DEFAULT_TIMEOUT)),
        )


def _parse_facts(line: str) -> tuple[dict[str, str], str]:
    """Split one MLSD/MLST line into its facts and the entry name."""
    facts_text, _, name = line.lstrip().partition(" ")
    facts: dict[str, str] = {}
    for item in facts_text.split(";"):
        if not item:
            continue
        key, _, value = item.partition("=")
        facts[key.lower()] = value
    return facts, name.strip()


def _parse_timestamp(value: str | None) -> str | None:
    """Convert an FTP YYYYMMDDHHMMSS timestamp to an ISO-8601 string."""
    if not value:
        return None
    try:
        # FTP timestamps are UTC; pin the offset so the result is tz-aware.
        parsed = datetime.strptime(value.split(".")[0] + "+0000", "%Y%m%d%H%M%S%z")
    except ValueError:
        return None
    return parsed.isoformat()


def _kind(facts: dict[str, str]) -> str:
    entry_type = facts.get("type", "").lower()
    if entry_type in {"dir", "cdir", "pdir"}:
        return "dir"
    if entry_type == "file":
        return "file"
    return entry_type or "unknown"


def _entry(path: str, facts: dict[str, str], name: str | None = None) -> dict:
    """Build the metadata dict returned for a remote path."""
    size = facts.get("size", "")
    return {
        "path": path,
        "name": name or posixpath.basename(path.rstrip("/")) or "/",
        "type": _kind(facts),
        "size": int(size) if size.isdigit() else None,
        "modified": _parse_timestamp(facts.get("modify")),
        "parent": posixpath.dirname(path.rstrip("/")) or "/",
    }


class FtpStore:
    """Browse, download from, and upload to an FTP drive.

    A single connection is shared behind a lock and re-opened transparently
    when the server has dropped it since the last call.
    """

    def __init__(self, settings: FtpSettings | None = None):
        self.settings = settings or FtpSettings.from_env()
        self._ftp: FTP | None = None
        self._lock = threading.Lock()

    # --- Connection handling ---

    def connect(self) -> dict:
        """Open the connection eagerly and report what it is talking to."""
        welcome = self._run(lambda ftp: ftp.getwelcome())
        return {
            "status": "ok",
            "host": self.settings.host,
            "port": self.settings.port,
            "user": self.settings.user,
            "root": self.settings.root,
            "tls": self.settings.use_tls,
            "welcome": welcome,
        }

    def close(self) -> None:
        """Close the connection if one is open."""
        with self._lock:
            self._close()

    def _close(self) -> None:
        ftp, self._ftp = self._ftp, None
        if ftp is None:
            return
        try:
            ftp.quit()
        except all_errors:
            try:
                ftp.close()
            except all_errors:
                pass

    def _connection(self) -> FTP:
        if self._ftp is not None:
            return self._ftp
        settings = self.settings
        ftp: FTP = (
            FTP_TLS(timeout=settings.timeout)
            if settings.use_tls
            else FTP(timeout=settings.timeout)
        )
        try:
            ftp.connect(settings.host, settings.port, timeout=settings.timeout)
            if isinstance(ftp, FTP_TLS):
                ftp.auth()
            ftp.login(settings.user, settings.password)
            if isinstance(ftp, FTP_TLS):
                ftp.prot_p()
        except error_perm as exc:
            ftp.close()
            raise FtpConfigError(
                f"{settings.host} rejected the login for {settings.user!r}: {exc}"
            ) from exc
        except all_errors as exc:
            ftp.close()
            raise FtpConfigError(
                f"Cannot reach {settings.host}:{settings.port} - {exc}"
            ) from exc
        ftp.set_pasv(settings.passive)
        self._ftp = ftp
        return ftp

    def _run(self, action):
        """Run an action against the connection, re-opening a stale one once."""
        with self._lock:
            try:
                return action(self._connection())
            except error_perm:
                raise
            except all_errors:
                self._close()
                return action(self._connection())

    # --- Paths ---

    def resolve(self, path: str | None) -> str:
        """Resolve a caller-supplied path against the configured root."""
        candidate = (path or ".").strip()
        if candidate.startswith("/"):
            resolved = posixpath.normpath(candidate)
        else:
            if candidate in {"", "."}:
                candidate = ""
            resolved = posixpath.normpath(posixpath.join(self.settings.root, candidate))
        return resolved if resolved.startswith("/") else "/" + resolved

    # --- Actions ---

    def get_entry(self, path: str = ".") -> dict:
        """Return metadata for one remote file or directory."""
        remote = self.resolve(path)
        try:
            response = self._run(lambda ftp: ftp.sendcmd(f"MLST {remote}"))
        except error_perm as exc:
            if str(exc).startswith(UNSUPPORTED_REPLIES):
                return self._stat_fallback(remote)
            raise FtpError(f"No entry at {remote} - {exc}") from exc
        for line in response.splitlines()[1:-1]:
            facts, name = _parse_facts(line)
            if facts:
                return _entry(remote, facts, posixpath.basename(name) or name)
        return self._stat_fallback(remote)

    def _stat_fallback(self, remote: str) -> dict:
        """Derive metadata with SIZE/MDTM when the server has no MLST."""

        def probe(ftp: FTP) -> dict:
            try:
                # Many servers refuse SIZE in ASCII mode.
                ftp.voidcmd("TYPE I")
                size = ftp.size(remote)
            except error_perm:
                size = None
            if size is None:
                original = ftp.pwd()
                try:
                    ftp.cwd(remote)
                except error_perm as exc:
                    raise FtpError(f"No entry at {remote} - {exc}") from exc
                finally:
                    ftp.cwd(original)
                return _entry(remote, {"type": "dir"})
            facts = {"type": "file", "size": str(size)}
            try:
                facts["modify"] = ftp.sendcmd(f"MDTM {remote}").split()[-1]
            except error_perm:
                pass
            return _entry(remote, facts)

        return self._run(probe)

    def list_children(self, path: str = ".") -> list[dict]:
        """List the direct contents of a remote directory."""
        remote = self.resolve(path)
        entries: list[dict] = []

        def collect(line: str) -> None:
            facts, name = _parse_facts(line)
            if not name or facts.get("type", "").lower() in {"cdir", "pdir"}:
                return
            entries.append(_entry(posixpath.join(remote, name), facts, name))

        try:
            self._run(lambda ftp: ftp.retrlines(f"MLSD {remote}", collect))
        except error_perm as exc:
            if str(exc).startswith(UNSUPPORTED_REPLIES):
                return self._list_fallback(remote)
            raise FtpError(f"Cannot list {remote} - {exc}") from exc
        entries.sort(key=lambda entry: (entry["type"] != "dir", entry["name"].lower()))
        return entries

    def _list_fallback(self, remote: str) -> list[dict]:
        """List names with NLST when the server has no MLSD."""
        names: list[str] = []
        try:
            self._run(lambda ftp: ftp.retrlines(f"NLST {remote}", names.append))
        except error_perm as exc:
            raise FtpError(f"Cannot list {remote} - {exc}") from exc
        children = []
        for name in names:
            base = posixpath.basename(name.strip())
            if base in {"", ".", ".."}:
                continue
            children.append(self.get_entry(posixpath.join(remote, base)))
        return children

    def download_file(self, remote_path: str, local_path: str | None = None) -> dict:
        """Download a remote file and report where it landed locally."""
        remote = self.resolve(remote_path)
        target = os.path.abspath(
            local_path
            or os.path.join(
                tempfile.gettempdir(), posixpath.basename(remote) or "ftp_download"
            )
        )
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)

        def fetch(ftp: FTP) -> None:
            with open(target, "wb") as handle:
                ftp.retrbinary(f"RETR {remote}", handle.write)

        try:
            self._run(fetch)
        except error_perm as exc:
            if os.path.exists(target):
                os.remove(target)
            raise FtpError(f"Cannot download {remote} - {exc}") from exc
        return {
            "status": "ok",
            "remote_path": remote,
            "local_path": target,
            "size": os.path.getsize(target),
        }

    def upload_file(
        self, local_path: str, parent_path: str = ".", name: str | None = None
    ) -> dict:
        """Upload a local file into a remote directory."""
        source = os.path.abspath(local_path)
        if not os.path.isfile(source):
            raise FtpError(f"No local file at {source}")
        parent = self.resolve(parent_path)
        remote = posixpath.join(parent, name or os.path.basename(source))

        def store(ftp: FTP) -> None:
            with open(source, "rb") as handle:
                ftp.storbinary(f"STOR {remote}", handle)

        try:
            self._run(store)
        except error_perm as exc:
            raise FtpError(
                f"Cannot upload to {remote} - {exc}. Check that {parent} exists "
                "and that the account may write to it."
            ) from exc
        return {
            "status": "ok",
            "local_path": source,
            "remote_path": remote,
            "parent": parent,
            "name": posixpath.basename(remote),
            "size": os.path.getsize(source),
        }
