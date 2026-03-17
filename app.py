from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Body
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
from typing import List, Optional
import os
import shutil
import uuid
import pathlib
import asyncio

from tools import (
    BASE_TEMP_DIR,
    cleanup_loop,
    create_download_zip,
    ensure_download_dir,
    get_colab_url,
    init_base_dirs,
    init_db,
    list_downloadable_files,
    process_task,
    set_colab_url,
    tasks,
)

SECRET_TOKEN = os.environ.get("SECRET_TOKEN", "")
app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_base_dirs()
init_db()
ensure_download_dir()


def _safe_remove(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


@app.on_event("startup")
async def startup_event():
    try:
        asyncio.create_task(cleanup_loop())
    except Exception as e:
        print(f"Cleanup loop error: {e}")


@app.get("/")
async def read_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    url = get_colab_url()
    return {"youtube_enabled": url != "", "colab_url": url}


@app.get("/api/download-files")
async def get_downloadable_files():
    return {"files": list_downloadable_files()}


@app.post("/api/download-files")
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


@app.post("/api/update_colab_url")
async def update_colab_url(payload: dict = Body(...)):
    if not SECRET_TOKEN or payload.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URLが必要です")
    set_colab_url(url)
    print(f"Colab URL Updated: {url}")
    return {"status": "success", "url": url}


@app.post("/api/convert")
async def convert_start(
    background_tasks: BackgroundTasks,
    tool_id: str = Form(...),
    url: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    output_format: str = Form("mp3"),
):
    task_id = str(uuid.uuid4())
    os.makedirs(os.path.join(BASE_TEMP_DIR, task_id, "input"), exist_ok=True)

    if files is not None and len(files) == 0:
        files = None

    fnames = []
    if files:
        for f in files:
            safe_name = pathlib.Path(f.filename).name
            file_path = os.path.join(BASE_TEMP_DIR, task_id, "input", safe_name)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(f.file, buf)
            fnames.append(safe_name)

    tasks[task_id] = {"status": "processing", "progress": 10, "last_log": "タスクを開始しました"}
    background_tasks.add_task(process_task, task_id, tool_id, url, fnames, output_format)
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    return tasks.get(task_id, {"status": "failed", "error": "Task not found"})


@app.get("/api/download/{task_id}")
async def download_result(task_id: str):
    zip_path = os.path.join(BASE_TEMP_DIR, task_id, "result.zip")
    if os.path.exists(zip_path):
        return FileResponse(zip_path, filename="result.zip")
    if task_id in tasks:
        raise HTTPException(status_code=503, detail="ファイルが一時領域から消えました。再度変換をやり直してください。")
    raise HTTPException(status_code=404, detail="タスクが見つかりません。")
