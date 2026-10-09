from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LectureSource, Subject


DEFAULT_LECTURE_STORAGE_PATH = (
    Path(__file__).resolve().parents[2] / "lecture_uploads"
)
STORED_FILENAME_PATTERN = re.compile(r"^[a-f0-9]{64}\.pdf$")


class LectureStorageError(RuntimeError):
    pass


def lecture_storage_root() -> Path:
    configured = os.getenv("LECTURE_STORAGE_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_LECTURE_STORAGE_PATH


def safe_original_filename(filename: str | None) -> str:
    normalized = (filename or "lecture.pdf").replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1].replace("\x00", "").strip()
    if not basename:
        basename = "lecture.pdf"
    return basename[:255]


def _relative_storage_path(file_hash: str) -> Path:
    return Path(file_hash[:2]) / f"{file_hash}.pdf"


def _write_pdf_if_missing(root: Path, relative_path: Path, raw: bytes) -> None:
    destination = root / relative_path
    if destination.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=".upload-", delete=False
        ) as temporary:
            temporary.write(raw)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, destination)
    except OSError as exc:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise LectureStorageError("Could not persist the uploaded lecture PDF") from exc


def persist_lecture_source(
    db: Session,
    *,
    subject: Subject,
    original_filename: str | None,
    raw: bytes,
    page_count: int,
    storage_root: Path | None = None,
) -> LectureSource:
    file_hash = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(
        select(LectureSource).where(
            LectureSource.subject_id == subject.id,
            LectureSource.file_hash == file_hash,
        )
    )
    root = (storage_root or lecture_storage_root()).resolve()
    relative_path = _relative_storage_path(file_hash)
    _write_pdf_if_missing(root, relative_path, raw)
    if existing is not None:
        return existing

    source = LectureSource(
        subject_id=subject.id,
        original_filename=safe_original_filename(original_filename),
        stored_filename=relative_path.name,
        file_path=relative_path.as_posix(),
        file_hash=file_hash,
        page_count=page_count,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def resolve_lecture_file(
    source: LectureSource, storage_root: Path | None = None
) -> Path:
    root = (storage_root or lecture_storage_root()).resolve()
    if not STORED_FILENAME_PATTERN.fullmatch(source.stored_filename):
        raise LectureStorageError("Stored lecture filename is invalid")
    candidate = (root / source.file_path).resolve()
    if not candidate.is_relative_to(root) or candidate.name != source.stored_filename:
        raise LectureStorageError("Stored lecture path is invalid")
    if not candidate.is_file():
        raise LectureStorageError("Stored lecture PDF is missing")
    return candidate
