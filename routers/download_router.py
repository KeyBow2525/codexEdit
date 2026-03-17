from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import os

from tools import create_download_zip, list_downloadable_files

router = APIRouter(prefix="/api", tags=["download-files"])


def _safe_remove(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


@router.get("/download-files")
async def get_downloadable_files():
    return {"files": list_downloadable_files()}


@router.post("/download-files")
async def download_selected_files(payload: dict = Body(...)):
    selected_files = payload.get("files", [])
    try:
        zip_path = create_download_zip(selected_files)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return FileResponse(
        zip_path,
        filename="selected_files.zip",
        media_type="application/zip",
        background=BackgroundTask(_safe_remove, zip_path),
    )
