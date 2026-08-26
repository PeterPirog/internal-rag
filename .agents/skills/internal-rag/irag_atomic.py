#!/usr/bin/env python3
"""irag_atomic.py — atomic write helpers for MCP Light Memory.

Stdlib-only (Python 3.8+). Provides:
  - atomic_write_text(path, content): temp file -> fsync -> os.replace
  - atomic_write_bytes(path, content): same for binary
  - ProjectWriteLock: a cross-platform file lock for serializing mutations

Used by remember/update/supersede/forget/checkpoint/working-state/task-state
to prevent partial writes and race conditions when multiple agents mutate
memory concurrently.

The lock is a simple file-based lock using os.O_EXCL (atomic create) with
a stale-lock timeout. On POSIX, fcntl.flock is used as a fallback. On
Windows, the O_EXCL approach is the primary mechanism (fcntl is unavailable).
"""
from __future__ import annotations
import os
import sys
import time
import tempfile
from pathlib import Path
from typing import Optional, Union


def _replace_retry(tmp: str, target: str, attempts: int = 8, delay: float = 0.05) -> None:
    """os.replace with bounded retry for transient Windows sharing violations
    (WinError 32) — e.g. an antivirus scan briefly holding a handle on the
    target, or the target file still being closed by another thread."""
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except (PermissionError, OSError) as e:
            last = e
            # WinError 32 = ERROR_SHARING_VIOLATION; also retry other EACCES-like
            if not isinstance(e, PermissionError) and getattr(e, "winerror", None) not in (32, 5):
                raise
            time.sleep(delay * (i + 1))
    assert last is not None
    raise last


def atomic_write_text(path: Union[str, Path], content: str,
                      encoding: str = "utf-8") -> None:
    """Write text to `path` atomically: temp file -> fsync -> os.replace.

    Guarantees that `path` is either the old content or the new content,
    never a partial write. The temp file is created in the same directory
    as `path` (required for os.replace to be atomic on the same filesystem).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass  # fsync not available on some platforms
        _replace_retry(tmp, str(p))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Union[str, Path], content: bytes) -> None:
    """Write bytes to `path` atomically: temp file -> fsync -> os.replace."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass
        _replace_retry(tmp, str(p))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class ProjectWriteLock:
    """A cross-platform project write lock for serializing memory mutations.

    Uses a lock file with PID + timestamp. On POSIX, also uses fcntl.flock
    for cooperative locking. On Windows, uses O_EXCL atomic-create.

    Usage:
        with ProjectWriteLock(rag_dir / ".write.lock"):
            # exclusive access to memory mutations
            ...

    Stale locks (older than `stale_seconds`) are reclaimed automatically.
    """

    def __init__(self, lock_path: Union[str, Path],
                 timeout: float = 10.0,
                 stale_seconds: float = 120.0,
                 poll_interval: float = 0.1):
        self.lock_path = Path(lock_path)
        self.timeout = timeout
        self.stale_seconds = stale_seconds
        self.poll_interval = poll_interval
        self._fd: Optional[int] = None
        self._have_posix_lock = False

    def _try_acquire(self) -> bool:
        """Attempt to acquire the lock once. Returns True on success."""
        try:
            # Try atomic create (O_EXCL) — works on all platforms
            fd = os.open(str(self.lock_path),
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            self._fd = fd
            content = f"{os.getpid()}\n{time.time()}\n"
            os.write(fd, content.encode("ascii"))
            os.close(fd)
            self._fd = None  # file is closed; we hold the lock via existence

            # On POSIX, also try fcntl for cooperative locking
            if sys.platform != "win32":
                try:
                    import fcntl
                    fd2 = os.open(str(self.lock_path), os.O_WRONLY)
                    try:
                        fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        self._fd = fd2
                        self._have_posix_lock = True
                    except (OSError, IOError):
                        os.close(fd2)
                except ImportError:
                    pass
            return True
        except FileExistsError:
            # Lock exists — check if stale
            return self._try_reclaim_stale()

    def _try_reclaim_stale(self) -> bool:
        """Check if the existing lock is stale and reclaim it."""
        try:
            content = self.lock_path.read_text(encoding="ascii", errors="replace")
            lines = content.strip().split("\n")
            if len(lines) >= 2:
                lock_pid = int(lines[0].strip())
                lock_time = float(lines[1].strip())
                age = time.time() - lock_time
                if age > self.stale_seconds:
                    # Stale lock — reclaim
                    self.lock_path.unlink(missing_ok=True)
                    return self._try_acquire()
                # Check if PID is still alive (POSIX)
                if sys.platform != "win32":
                    try:
                        os.kill(lock_pid, 0)
                    except OSError:
                        # Process dead — reclaim
                        self.lock_path.unlink(missing_ok=True)
                        return self._try_acquire()
            return False
        except Exception:
            return False

    def acquire(self) -> None:
        """Acquire the lock, waiting up to `timeout` seconds."""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if self._try_acquire():
                return
            time.sleep(self.poll_interval)
        raise TimeoutError(
            f"Could not acquire write lock {self.lock_path} within {self.timeout}s")

    def release(self) -> None:
        """Release the lock.

        On Windows, unlinking a file another thread still has open (e.g. a
        concurrent stale-check read) raises WinError 32 — unlink is therefore
        retried and treated as best-effort: if it ultimately fails, the stale
        reclaim logic will collect the lock on a later acquisition.
        """
        if self._fd is not None and self._have_posix_lock:
            try:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._have_posix_lock = False
        for i in range(8):
            try:
                self.lock_path.unlink(missing_ok=True)
                return
            except OSError:
                time.sleep(0.02 * (i + 1))

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()