"""LocalFsBlobStore — filesystem-backed BlobStore implementation (F2).

Layout::

    <blob_root>/
      sha256/
        <first2>/
          <remaining62>.bin       # the verified blob
          <remaining62>.bin.lock  # advisory flock for concurrent-write serialisation
          <remaining62>.bin.tmp.<uuid7>  # in-flight upload; renamed on SHA match

Write path:

1. Compute target path ``<blob_root>/sha256/<f2>/<r62>.bin``.
2. Take an exclusive non-blocking ``flock`` on the sibling ``.lock`` file.
   Failure → :class:`BlobUploadInProgress` (HTTP 409).
3. Stream the upload to ``<target>.tmp.<uuid7>``, updating ``hashlib.sha256``
   incrementally with 8 MiB chunks. Track bytes_written; if it exceeds
   ``max_bytes``, drain the rest of the stream (so the client sees the
   413 promptly), delete the temp file, raise :class:`BlobTooLarge`.
4. After the stream is exhausted, compare the hex digest to
   ``expected_sha256``. Mismatch → delete temp file, raise
   :class:`BlobChecksumMismatch`. Match → ``os.rename`` into place
   (atomic on POSIX), release the flock, return :class:`WriteReceipt`.

Read path:

1. Compute target path; if missing → :class:`BlobNotPresent`.
2. Return a :class:`StreamWithVerify` wrapping the file handle plus a fresh
   ``hashlib.sha256``. The router iterates ``.iter_chunks()`` to send bytes
   to the client and calls ``.verify_at_eof()`` to assert SHA equality;
   mismatch raises :class:`BlobChecksumMismatchOnRead` which the router
   maps to HTTP 500 + ``code=blob_checksum_mismatch_on_read``.

The chunked-SHA-on-read pattern means tampering is detected on every
download, not just at upload time (FR-030 + SC-005).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import errno
import fcntl
import hashlib
import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from gard.core.blob_store import (
    BlobChecksumMismatch,
    BlobNotPresent,
    BlobStore,
    BlobTooLarge,
    BlobUploadInProgress,
    StreamWithVerify,
    WriteReceipt,
)

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB — matches BlobStore/__init__.


class LocalFsBlobStore(BlobStore):
    """The v1 concrete BlobStore implementation."""

    def __init__(self, root: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self.root = Path(root)
        self._chunk_size = chunk_size

    # ---- internal --------------------------------------------------------

    def _resolve_paths(self, key: str) -> tuple[Path, Path]:
        target = self.root / f"{key}.bin"
        lock = self.root / f"{key}.bin.lock"
        return target, lock

    def _temp_path(self, target: Path) -> Path:
        return target.with_suffix(target.suffix + f".tmp.{_uuid.uuid4().hex}")

    # ---- protocol --------------------------------------------------------

    def put(
        self,
        key: str,
        stream: BinaryIO,
        expected_sha256: str,
        *,
        max_bytes: int,
    ) -> WriteReceipt:
        target, lock_path = self._resolve_paths(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Idempotent fast-path: blob already present and matches the
        # expected SHA — we trust the on-disk hash because the read path
        # re-verifies. Just emit a receipt.
        if target.exists():
            stat = target.stat()
            return WriteReceipt(
                computed_sha256=expected_sha256,
                bytes_written=stat.st_size,
                stored_at=dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.UTC),
            )

        # Take the exclusive non-blocking flock.
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BlobUploadInProgress(
                    f"another writer is uploading key={key}"
                ) from exc

            temp_path = self._temp_path(target)
            hasher = hashlib.sha256()
            bytes_written = 0
            try:
                with temp_path.open("wb") as fh:
                    while True:
                        chunk = stream.read(self._chunk_size)
                        if not chunk:
                            break
                        bytes_written += len(chunk)
                        if bytes_written > max_bytes:
                            # Drain the rest so the client gets the error
                            # promptly rather than mid-stream.
                            self._drain(stream)
                            with contextlib.suppress(OSError):
                                temp_path.unlink(missing_ok=True)
                            raise BlobTooLarge(
                                f"upload exceeded max_bytes={max_bytes} "
                                f"(after {bytes_written} bytes)"
                            )
                        hasher.update(chunk)
                        fh.write(chunk)
                    fh.flush()
                    os.fsync(fh.fileno())

                digest = hasher.hexdigest()
                if digest != expected_sha256.lower():
                    with contextlib.suppress(OSError):
                        temp_path.unlink(missing_ok=True)
                    raise BlobChecksumMismatch(
                        f"expected sha256={expected_sha256}, computed={digest}"
                    )

                # Atomic rename — POSIX guarantees this is atomic when src
                # and dst share a filesystem (which they do — same parent dir).
                os.replace(temp_path, target)
                stored_at = dt.datetime.now(tz=dt.UTC)
                return WriteReceipt(
                    computed_sha256=digest,
                    bytes_written=bytes_written,
                    stored_at=stored_at,
                )
            except (BlobChecksumMismatch, BlobTooLarge):
                raise
            except Exception:
                # Best-effort cleanup; never mask the original exception.
                with contextlib.suppress(OSError):
                    temp_path.unlink(missing_ok=True)
                raise
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError as exc:
                if exc.errno not in (errno.EBADF,):
                    raise
            os.close(lock_fd)

    def get(self, key: str, *, expected_sha256: str, size: int) -> StreamWithVerify:
        target, _ = self._resolve_paths(key)
        if not target.exists():
            raise BlobNotPresent(f"no blob at key={key}")
        fh = target.open("rb")
        return StreamWithVerify(
            fh, expected_sha256=expected_sha256, size=size, chunk_size=self._chunk_size
        )

    def exists(self, key: str) -> bool:
        target, _ = self._resolve_paths(key)
        return target.exists()

    def delete(self, key: str) -> None:
        target, _lock = self._resolve_paths(key)
        target.unlink(missing_ok=True)
        # We intentionally leave the lock file in place — re-creating it
        # on the next put() is cheaper than racing concurrent deletes.

    def iter_keys(self) -> Iterator[str]:
        prefix_dir = self.root / "sha256"
        if not prefix_dir.exists():
            return
        for first2_dir in sorted(prefix_dir.iterdir()):
            if not first2_dir.is_dir():
                continue
            for blob in sorted(first2_dir.glob("*.bin")):
                # Skip in-flight uploads
                if ".tmp." in blob.name:
                    continue
                # Strip ".bin" then rebuild the logical key.
                stem = blob.stem  # 62-hex without .bin
                yield f"sha256/{first2_dir.name}/{stem}"

    # ---- helpers ---------------------------------------------------------

    def _drain(self, stream: BinaryIO) -> None:
        """Read the rest of a stream into the void (1 MiB at a time)."""
        while stream.read(1024 * 1024):
            continue
