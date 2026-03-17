import os
import pathlib
import uuid
import zipfile
from typing import List

DOWNLOAD_FILES_DIR = pathlib.Path(__file__).resolve().parent.parent / "download_files"


def ensure_download_dir() -> None:
    DOWNLOAD_FILES_DIR.mkdir(parents=True, exist_ok=True)


def list_downloadable_files() -> List[str]:
    ensure_download_dir()
    files = []
    for item in DOWNLOAD_FILES_DIR.iterdir():
        if item.is_file() and not item.name.startswith('.'):
            files.append(item.name)
    return sorted(files)


def validate_selected_files(selected_files: List[str]) -> List[pathlib.Path]:
    if not selected_files:
        raise ValueError("ダウンロードするファイルを1つ以上選択してください。")

    available = {name: DOWNLOAD_FILES_DIR / name for name in list_downloadable_files()}
    resolved = []

    for name in selected_files:
        if name not in available:
            raise ValueError(f"指定されたファイルは存在しません: {name}")
        resolved.append(available[name])

    return resolved


def create_download_zip(selected_files: List[str]) -> str:
    ensure_download_dir()
    resolved_files = validate_selected_files(selected_files)
    zip_path = pathlib.Path("/tmp") / f"download_files_{uuid.uuid4().hex}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in resolved_files:
            zf.write(file_path, arcname=file_path.name)

    return str(zip_path)
