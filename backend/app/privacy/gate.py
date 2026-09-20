"""In-process reader/writer gate for the privacy-operation boundary.

app/privacy/ops.py's file-based lock is what a *new* request or process
sees, including one started after a crash -- but a plain "check the lock
file, then proceed" at connection time (as the pre-v1.6 code did) leaves a
request that is already mid-flight when a write starts free to keep
reading while source and database are being rewritten underneath it. This
module closes that hole: an ordinary request holds a read lease for its
entire lifetime (app/api/deps.get_conn), and pseudonymisation acquires the
write lease before touching anything, which blocks new reads immediately
and waits for every in-flight read to finish before granting the write.

Deliberately a single process-wide, in-memory instance. CLAUDE.md accepts a
single-worker deployment for this feature ("run with one worker unless the
gate is made cross-process"); ops.py's file lock is what still degrades
safely across a restart or a crash that this in-memory state cannot survive.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.privacy.ops import ArchiveWriteBusyError, PrivacyLockedError


class ReadWriteGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._readers = 0
        self._drained = threading.Condition(self._lock)
        self._write_active = False

    @contextmanager
    def read_lease(self) -> Iterator[None]:
        with self._lock:
            if self._write_active:
                raise PrivacyLockedError("a privacy operation is in progress")
            self._readers += 1
        try:
            yield
        finally:
            with self._drained:
                self._readers -= 1
                if self._readers == 0:
                    self._drained.notify_all()

    @contextmanager
    def write_lease(self, drain_timeout: float = 30.0) -> Iterator[None]:
        # Writers must serialize with one another as well as with readers.
        # The old boolean only blocked readers; a second writer could enter
        # while the first one was still mutating source/database state.
        with self._drained:
            writer_available = self._drained.wait_for(
                lambda: not self._write_active, timeout=drain_timeout
            )
            if not writer_available:
                raise ArchiveWriteBusyError("timed out waiting for another archive write to finish")
            self._write_active = True
            drained = self._drained.wait_for(lambda: self._readers == 0, timeout=drain_timeout)
            if not drained:
                self._write_active = False
                self._drained.notify_all()
                raise ArchiveWriteBusyError(
                    "timed out waiting for in-flight archive reads to finish"
                )
        try:
            yield
        finally:
            with self._drained:
                self._write_active = False
                self._drained.notify_all()

    def reset_for_tests(self) -> None:
        """Test-only escape hatch: a failed test can otherwise leave
        _write_active True and wedge every later test in the same process."""
        with self._lock:
            self._readers = 0
            self._write_active = False
            self._drained.notify_all()


gate = ReadWriteGate()
