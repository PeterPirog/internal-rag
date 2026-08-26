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
import secrets
import sys
import time
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union


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

    The lock file contains three lines:

        <pid>\\n<timestamp>\\n<ownership_token>\\n

    The ownership token is a per-instance, non-predictable random value
    (``secrets.token_hex``). Ownership is the ONLY condition under which a
    lock file is removed by ``release()``: a lock file is unlinked only if the
    token written inside it still equals this object's token. This prevents a
    stale owner from deleting a lock that a *new* owner has already taken over
    (the classic "foreign unlock" race).

    Stale-lock reclaim policy:
      - A lock whose recorded PID is dead (process no longer alive) may always
        be reclaimed, regardless of age.
      - A lock whose recorded PID is *live* is NEVER reclaimed on age alone —
        on any platform a live holder owns the lock no matter how old the
        timestamp is.
      - On Windows the liveness check uses the conservative kernel32 API
        (``OpenProcess`` + ``GetExitCodeProcess``); any uncertainty resolves to
        "assume alive", so a fresh foreign lock is never taken.
      - Unreadable/corrupt lock files are reclaimed on age alone after
        ``stale_seconds`` (the holder cannot be identified).

    Usage:
        with ProjectWriteLock(rag_dir / ".write.lock"):
            # exclusive access to memory mutations
            ...
    """

    def __init__(self, lock_path: Union[str, Path],
                 timeout: float = 10.0,
                 stale_seconds: float = 120.0,
                 poll_interval: float = 0.1):
        self.lock_path = Path(lock_path)
        self.timeout = timeout
        self.stale_seconds = stale_seconds
        self.poll_interval = poll_interval
        self._token: Optional[str] = None
        self._fd: Optional[int] = None
        self._have_posix_lock = False

    # ------------------------------------------------------------------ #
    # pid helpers                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _proc_creation_epoch(pid: int) -> Optional[float]:
        """Process creation time (epoch seconds) or None if the pid is not
        a live process on this machine.

        Windows: GetProcessTimes (ctypes over kernel32 — stdlib only).
        POSIX: 100 ns FILETIME → epoch.
        """
        try:
            import ctypes
            import ctypes.wintypes as wt

            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", wt.DWORD),
                            ("dwHighDateTime", wt.DWORD)]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            h = k32.OpenProcess(0x1000, False, pid)
            if not h:
                return None
            try:
                ct = FILETIME()
                if not k32.GetProcessTimes(h,
                                           ctypes.byref(ct),
                                           ctypes.byref(FILETIME()),
                                           ctypes.byref(FILETIME())):
                    return None
                # 100-ns intervals since 1601-01-01 → epoch
                total = (ct.dwHighDateTime << 32) | ct.dwLowDateTime
                return total / 1e7 - 11644473600.0
            finally:
                k32.CloseHandle(h)
        except Exception:
            return None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """Return True if the pid refers to a process that still holds it.

        POSIX: ``os.kill(pid, 0)`` (succeeds or PermissionError → alive;
        ProcessLookupError → dead).
        Windows: ``OpenProcess`` + ``GetExitCodeProcess`` (ctypes over
        kernel32, stdlib only):
          - handle failure ERROR_FILE_NOT_FOUND / ERROR_INVALID_PARAMETER →
            no such process → DEAD.
          - handle failure ERROR_ACCESS_DENIED → process exists → ALIVE
            (conservative: never steal a live holder's lock).
          - exit code STILL_ACTIVE (259) → running → ALIVE.
          - real exit code → the process has exited → DEAD.
        Note: Windows reuses PIDs, so a DEAD answer for a *recorded* pid can
        theoretically be a reused pid that is live — but the recorded holder
        is gone either way, which is what staleness is about.
        """
        if pid <= 0:
            return False
        if sys.platform == "win32":
            return ProjectWriteLock._pid_alive_win(pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, but we lack signal permission
        except OSError:
            return False
        return True

    @staticmethod
    def _pid_alive_win(pid: int) -> bool:
        """Windows liveness check (ctypes over kernel32 — stdlib only)."""
        try:
            import ctypes
            import ctypes.wintypes as wt

            STILL_ACTIVE = 0x00000103
            ERROR_ACCESS_DENIED = 5
            ERROR_FILE_NOT_FOUND = 2
            ERROR_INVALID_PARAMETER = 87

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wt.HANDLE
            k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
            k32.GetExitCodeProcess.argtypes = [wt.HANDLE,
                                               ctypes.POINTER(wt.DWORD)]

            handle = k32.OpenProcess(0x1000, False, pid)
            if not handle:
                err = ctypes.get_last_error()
                if err in (ERROR_FILE_NOT_FOUND, ERROR_INVALID_PARAMETER):
                    return False  # pid is gone → holder dead
                if err == ERROR_ACCESS_DENIED:
                    return True   # exists, state unreadable → conservative
                return True       # unknown → conservative (assume alive)
            try:
                code = wt.DWORD()
                if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return True   # unknown → conservative (assume alive)
                return code.value == STILL_ACTIVE
            finally:
                k32.CloseHandle(handle)
        except Exception:
            return True  # any failure → conservative (assume alive)

    def _parse_lock(self) -> Optional[Dict[str, Any]]:
        """Read the lock file -> {pid, time, token, created} or None if
        unreadable. `created` is the holder's process creation epoch (0.0 if
        legacy lock file / unknown) used to detect Windows PID reuse."""
        try:
            content = self.lock_path.read_text(encoding="ascii", errors="replace")
            lines = content.strip().split("\n")
            if len(lines) < 2:
                return None
            pid = int(lines[0].strip())
            ts = float(lines[1].strip())
            token = lines[2].strip() if len(lines) >= 3 else ""
            created = 0.0
            if len(lines) >= 4:
                try:
                    created = float(lines[3].strip())
                except ValueError:
                    created = 0.0
            return {"pid": pid, "time": ts, "token": token, "created": created}
        except (OSError, ValueError, IndexError):
            return None

    # ------------------------------------------------------------------ #
    # acquire                                                            #
    # ------------------------------------------------------------------ #

    def _create_fresh(self) -> bool:
        """Atomically create the lock file (O_EXCL) with our ownership token.

        Format (one value per line):
          1: pid
          2: timestamp (epoch seconds)
          3: ownership token (random, per-instance)
          4: process creation epoch (0.0 if unknown) — used to detect
             Windows PID reuse when reclaiming
        """
        self._token = secrets.token_hex(16)
        fd = os.open(str(self.lock_path),
                     os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            created = ProjectWriteLock._proc_creation_epoch(os.getpid()) or 0.0
            content = f"{os.getpid()}\n{time.time()}\n{self._token}\n{created}\n"
            os.write(fd, content.encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        self._fd = None  # file is closed; we hold the lock via existence+token

        # On POSIX, also take a cooperative advisory lock (flock) as belt-and-
        # braces: a live foreign holder that took the flock will block us even
        # if a race ever let us create the file.
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

    def _try_acquire(self) -> bool:
        """Attempt to acquire the lock once. Returns True on success."""
        try:
            self._create_fresh()
            return True
        except FileExistsError:
            return self._try_reclaim_stale()
        except OSError:
            return False

    def _try_reclaim_stale(self) -> bool:
        """Decide whether an existing lock file may be taken over.

        Decision (cross-platform):
          - holder provably GONE (dead PID) -> reclaim.
          - holder still ALIVE -> NEVER steal (any platform).
          - holder UNKNOWN (unreadable lock file) -> conservative stale
            policy: steal only after `stale_seconds`, never a fresh foreign lock.
        """
        info = self._parse_lock()
        if info is None:
            # Unreadable/corrupt lock file — a holder may be mid-write. Only
            # reclaim after `stale_seconds` so we never stomp a live writer.
            return self._unlink_if_old()
        pid = int(info["pid"])
        created = float(info.get("created") or 0.0)
        token = info["token"]

        # Never reclaim a lock that *we* already own (re-entrant acquire).
        if token and token == self._token:
            return True

        # Dead holder is always reclaimable, regardless of age.
        if not self._pid_alive(pid):
            return self._unlink_and_reacquire()

        # Holder is confirmed ALIVE → NEVER steal on any platform.
        return False

    def _unlink_if_old(self) -> bool:
        """Unlink a foreign lock only if its timestamp is older than
        `stale_seconds` (never steal a fresh foreign lock)."""
        info = self._parse_lock()
        if info is None:
            # No readable timestamp: be conservative, do not steal.
            return False
        age = time.time() - float(info["time"])
        if age <= self.stale_seconds:
            return False
        return self._unlink_and_reacquire()

    def _unlink_and_reacquire(self) -> bool:
        """Remove a confirmed-stale foreign lock and take it over."""
        for _ in range(4):
            try:
                self.lock_path.unlink()
                break
            except FileNotFoundError:
                return False  # someone else reclaimed it first
            except OSError:
                time.sleep(0.02)
        else:
            return False
        return self._try_acquire()

    # ------------------------------------------------------------------ #
    # release                                                            #
    # ------------------------------------------------------------------ #

    def _owns_file(self) -> bool:
        """True if the lock file still records THIS object's token."""
        if not self._token:
            return False
        info = self._parse_lock()
        return bool(info and info.get("token") == self._token)

    def release(self) -> None:
        """Release the lock — but ONLY if we still own the lock file.

        A stale owner releasing after a *new* owner has already reclaimed the
        lock must NOT delete the new owner's lock file: the token inside will
        no longer match this object's token, so the unlink is skipped.

        On Windows, unlinking a file another process still has open raises
        WinError 32 — unlink is retried and, if it ultimately fails, the new
        owner's token check keeps the file in place for them.
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

        # Ownership check FIRST — never unlink a lock we no longer own.
        if not self._owns_file():
            self._token = None
            return

        for i in range(8):
            try:
                self.lock_path.unlink()
                break
            except FileNotFoundError:
                break
            except OSError:
                time.sleep(0.02 * (i + 1))
        self._token = None

    def acquire(self) -> None:
        """Acquire the lock, waiting up to `timeout` seconds."""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if self._try_acquire():
                return
            time.sleep(self.poll_interval)
        raise TimeoutError(
            f"Could not acquire write lock {self.lock_path} within {self.timeout}s")

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()