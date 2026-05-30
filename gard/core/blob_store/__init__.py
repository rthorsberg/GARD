"""BlobStore protocol + value types (F2).

The protocol defines the seam between the firmware-package router and the
underlying storage. v1 ships exactly one concrete implementation,
:class:`LocalFsBlobStore`, rooted at ``GARD_BLOB_ROOT`` per ADR-0011 §5.
A future S3-backed implementation would be additive.

Per spec FR-029..FR-033:

- SHA-256 verification is chunked on both write AND read.
- Concurrent uploads to the same key serialise on the filesystem
  (POSIX ``flock``); losers raise :class:`BlobUploadInProgress`.
- Mismatched checksums raise :class:`BlobChecksumMismatch` (write) or
  :class:`BlobChecksumMismatchOnRead` (read).
- Uploads exceeding the configured cap stream-and-discard then raise
  :class:`BlobTooLarge` (the FastAPI handler translates to HTTP 413).
- A missing blob raises :class:`BlobNotPresent` (handler → HTTP 404).

Keys are content-addressed:

    sha256/<first-2-hex>/<remaining-62-hex>

so concurrent uploads of the same artefact converge on the same path and
the filesystem itself becomes the serialisation point.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable

__all__ = [
    "BlobChecksumMismatch",
    "BlobChecksumMismatchOnRead",
    "BlobNotPresent",
    "BlobStore",
    "BlobStoreError",
    "BlobTooLarge",
    "BlobUploadInProgress",
    "StreamWithVerify",
    "WriteReceipt",
    "key_for_sha256",
]


# ---- Errors -----------------------------------------------------------


class BlobStoreError(Exception):
    """Base for all BlobStore-raised errors."""


class BlobChecksumMismatch(BlobStoreError):
    """Computed SHA-256 of the uploaded stream does not match the expected SHA."""


class BlobChecksumMismatchOnRead(BlobStoreError):
    """Computed SHA-256 of bytes read from storage does not match the key.

    This typically means the on-disk blob has been tampered with or corrupted.
    The handler maps this to HTTP 500 + ``code=blob_checksum_mismatch_on_read``
    and emits a ``firmware_catalog.package.blob_read_failed`` audit event.
    """


class BlobTooLarge(BlobStoreError):
    """Upload exceeded the configured per-blob size cap (FR-031)."""


class BlobUploadInProgress(BlobStoreError):
    """Another writer holds the per-key flock; loser retries after backoff (FR-033)."""


class BlobNotPresent(BlobStoreError):
    """Catalog row exists but no bytes have been uploaded yet (FR-029 / FR-030)."""


# ---- Value types ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    """What ``BlobStore.put`` returns on success."""

    computed_sha256: str
    bytes_written: int
    stored_at: dt.datetime


class StreamWithVerify:
    """A read stream that recomputes SHA-256 as it's consumed.

    The router iterates ``.iter_chunks()`` to stream the response body;
    after the stream is exhausted (or on close), the caller MUST call
    :meth:`verify_at_eof` which raises :class:`BlobChecksumMismatchOnRead`
    on tamper detection.
    """

    __slots__ = ("_chunk_size", "_consumed", "_expected_sha256", "_fh", "_hasher", "_size")

    def __init__(
        self,
        fh: BinaryIO,
        expected_sha256: str,
        size: int,
        chunk_size: int = 8 * 1024 * 1024,  # 8 MiB
    ) -> None:
        self._fh = fh
        self._expected_sha256 = expected_sha256
        self._hasher = hashlib.sha256()
        self._chunk_size = chunk_size
        self._consumed = False
        self._size = size

    @property
    def size(self) -> int:
        return self._size

    def iter_chunks(self) -> Iterator[bytes]:
        """Yield 8 MiB chunks, updating the running SHA. Idempotent on close."""
        try:
            while True:
                chunk = self._fh.read(self._chunk_size)
                if not chunk:
                    break
                self._hasher.update(chunk)
                yield chunk
        finally:
            self._consumed = True
            self._fh.close()

    def verify_at_eof(self) -> str:
        """Return the computed hex digest; raise on mismatch.

        Safe to call after :meth:`iter_chunks` has been fully consumed. If
        called before consumption is complete, the verdict reflects only
        the bytes seen so far — callers MUST ensure full consumption first.
        """
        digest = self._hasher.hexdigest()
        if digest != self._expected_sha256:
            raise BlobChecksumMismatchOnRead(
                f"expected sha256={self._expected_sha256}, observed={digest}"
            )
        return digest


# ---- Helpers ----------------------------------------------------------


def key_for_sha256(sha256: str) -> str:
    """Compute the content-addressed key for a hex SHA-256.

    ``sha256/<first2>/<remaining62>`` — splits the hex digest so the
    top-level directory holds at most 256 entries even for a multi-million-
    blob deployment.
    """
    sha = sha256.lower()
    if len(sha) != 64:
        raise ValueError(f"sha256 must be 64 hex chars, got {len(sha)}")
    return f"sha256/{sha[:2]}/{sha[2:]}"


# ---- Protocol ---------------------------------------------------------


@runtime_checkable
class BlobStore(Protocol):
    """Five-method protocol — implementations live in submodules."""

    def put(
        self,
        key: str,
        stream: BinaryIO,
        expected_sha256: str,
        *,
        max_bytes: int,
    ) -> WriteReceipt:
        """Stream ``stream`` to storage under ``key``, verifying SHA chunked.

        On mismatch: temp file deleted, raises :class:`BlobChecksumMismatch`.
        On size cap exceeded: temp file deleted, raises :class:`BlobTooLarge`.
        On concurrent writer: raises :class:`BlobUploadInProgress`.
        """
        ...

    def get(self, key: str, *, expected_sha256: str, size: int) -> StreamWithVerify:
        """Open a verified read stream. Raises :class:`BlobNotPresent` if absent."""
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Delete the blob. v1: out-of-band admin tooling only; no API surface."""
        ...

    def iter_keys(self) -> Iterator[str]:
        """Walk all stored keys (for integrity-audit + ``make seed`` tooling)."""
        ...
