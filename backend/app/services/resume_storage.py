from pathlib import Path
import re
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import ApiError
from app.services.resume_parser import MAX_FILE_BYTES, validate_file

def storage_path(key: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", key):
        raise ApiError(500, "INVALID_STORAGE_KEY", "无法读取简历存储位置")
    root = get_settings().resume_storage_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / key

def store_upload(upload: UploadFile) -> tuple[str, str, str, int]:
    name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isprintable()).strip()
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".docx"} or len(name) > 255:
        raise ApiError(415, "UNSUPPORTED_RESUME_TYPE", "只支持文件名有效的 PDF 或 DOCX")
    file_type = suffix.removeprefix(".")
    key = uuid4().hex
    destination = storage_path(key)
    size = 0
    with upload.file as stream:
        try:
            with destination.open("xb") as target:
                while chunk := stream.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise ApiError(413, "FILE_TOO_LARGE", "简历文件最多 10 MB")
                    target.write(chunk)
            if not size:
                raise ApiError(422, "EMPTY_RESUME_FILE", "简历文件为空")
            with destination.open("rb") as stored:
                validate_file(stored, file_type)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    return key, name, file_type, size
