from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Body
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import os
import shutil
import zipfile
import uuid
import time
import requests
import sqlite3
import subprocess
from pydub import AudioSegment
from PIL import Image
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    PILLOW_HEIF_AVAILABLE = True
except Exception:
    PILLOW_HEIF_AVAILABLE = False
from pdf2image import convert_from_path
import pathlib
import asyncio

SECRET_TOKEN = os.environ.get("SECRET_TOKEN", "")
app = FastAPI()

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# パス設定
BASE_TEMP_DIR = "/tmp/media_master"
DB_PATH = "/tmp/media_master/colab_config.db"
os.makedirs(BASE_TEMP_DIR, exist_ok=True)

# 進行状況管理（メモリ上）
tasks: Dict[str, dict] = {}

# --- データベース初期化 ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

async def cleanup_loop():
    while True:
        await asyncio.sleep(3600)
        now = time.time()
        to_delete = [
            tid for tid, t in list(tasks.items())
            if t.get("completed_at") and now - t["completed_at"] > 3600
        ]
        for tid in to_delete:
            tasks.pop(tid, None)
            shutil.rmtree(os.path.join(BASE_TEMP_DIR, tid), ignore_errors=True)

@app.on_event("startup")
async def startup_event():
    try:
        asyncio.create_task(cleanup_loop())
    except Exception as e:
        print(f"Cleanup loop error: {e}")

def get_colab_url() -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM config WHERE key = "colab_url"')
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception as e:
        print(f"DB Read Error: {e}")
        return ""

def set_colab_url(url: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO config (key, value, updated_at)
        VALUES (?, ?, ?)
    ''', ("colab_url", url.strip(), time.time()))
    conn.commit()
    conn.close()

def is_ngrok_error(text: str) -> bool:
    """ngrok のオフラインページかどうかを判定する"""
    return "ERR_NGROK" in text or "<!DOCTYPE html>" in text or "ngrok" in text.lower()

# --- 非同期処理ロジック ---
def process_task(task_id: str, tool_id: str, url_text: str, filenames: List[str], output_format: str = "mp3"):
    session_path = os.path.join(BASE_TEMP_DIR, task_id)
    input_path = os.path.join(session_path, "input")
    output_path = os.path.join(session_path, "output")
    os.makedirs(output_path, exist_ok=True)

    try:
        VALID_TOOL_IDS = {'youtube', 'heic-jpg', 'm4a-mp3', 'mp4-mp3', 'jpeg-pdf', 'pdf-png'}
        if tool_id not in VALID_TOOL_IDS:
            raise ValueError(f"無効なtool_idです: {tool_id}")

        if output_format not in ('mp3', 'mp4'):
            raise ValueError(f"無効なoutput_formatです: {output_format}")

        current_colab_url = get_colab_url()

        # YouTube 処理
        if tool_id == 'youtube' and url_text:
            if not current_colab_url:
                raise Exception("サーバーが停止しています。管理者にお問い合わせください。")

            urls = [u.strip() for u in url_text.split('\n') if u.strip()]
            tasks[task_id]["last_log"] = f"Colabへリクエスト送信中... ({output_format})"

            try:
                response = requests.post(
                    f"{current_colab_url.rstrip('/')}/batch-download",
                    json={"urls": urls, "format": output_format},
                    timeout=900
                )

                if response.status_code != 200:
                    error_body = response.text
                    if is_ngrok_error(error_body):
                        raise Exception("サーバーが停止しています。管理者にお問い合わせください。")
                    raise Exception(f"Colabエラー: {error_body}")

                colab_zip = os.path.join(session_path, "colab_result.zip")
                with open(colab_zip, "wb") as f:
                    f.write(response.content)

                with zipfile.ZipFile(colab_zip, 'r') as z:
                    z.extractall(output_path)

                tasks[task_id]["last_log"] = "取得完了"
                tasks[task_id]["progress"] = 90
            except Exception as e:
                error_msg = str(e)
                if is_ngrok_error(error_msg) or "サーバーが停止しています" in error_msg:
                    raise Exception("サーバーが停止しています。管理者にお問い合わせください。")
                raise Exception(f"Colab接続失敗: {error_msg}")

        # 通常のメディア変換処理
        else:
            # jpeg-pdf は全ファイルをまとめて1つのPDFに結合
            if tool_id == 'jpeg-pdf':
                imgs = []
                for fname in filenames:
                    in_f = os.path.join(input_path, fname)
                    img = Image.open(in_f).convert('RGB')
                    imgs.append(img)
                if not imgs:
                    raise Exception("変換対象の画像がありません")
                out_pdf = os.path.join(output_path, "output.pdf")
                imgs[0].save(out_pdf, "PDF", save_all=True, append_images=imgs[1:])
                tasks[task_id]["progress"] = 80

            else:
                for i, fname in enumerate(filenames):
                    in_f = os.path.join(input_path, fname)
                    tasks[task_id]["last_log"] = f"処理中: {fname}"
                    tasks[task_id]["progress"] = int(20 + (i / len(filenames)) * 60)

                    if tool_id == 'heic-jpg':
                        out_f = os.path.join(output_path, f"{os.path.splitext(fname)[0]}.jpg")
                        converted = False
                        # まずImageMagickで試みる（最も確実）
                        try:
                            result = subprocess.run(
                                ["convert", in_f, "-quality", "95", out_f],
                                capture_output=True, timeout=60
                            )
                            if result.returncode == 0 and os.path.exists(out_f):
                                converted = True
                        except Exception:
                            pass
                        # フォールバック: pillow-heif
                        if not converted and PILLOW_HEIF_AVAILABLE:
                            img = Image.open(in_f)
                            img.convert('RGB').save(out_f, 'JPEG', quality=95)
                            converted = True
                        if not converted:
                            raise Exception(f"HEIC変換に失敗しました: {fname}。ImageMagickおよびpillow-heifが利用できません。")

                    elif tool_id in ['m4a-mp3', 'mp4-mp3']:
                        audio = AudioSegment.from_file(in_f)
                        audio.export(os.path.join(output_path, f"{os.path.splitext(fname)[0]}.mp3"), format="mp3")

                    elif tool_id == 'pdf-png':
                        images = convert_from_path(in_f)
                        for j, image in enumerate(images):
                            image.save(os.path.join(output_path, f"{os.path.splitext(fname)[0]}_{j}.png"), "PNG")

        # 結果をZIPにまとめる
        tasks[task_id]["last_log"] = "ファイルを圧縮中..."
        final_zip = os.path.join(session_path, "result.zip")
        with zipfile.ZipFile(final_zip, 'w') as z:
            for f in os.listdir(output_path):
                z.write(os.path.join(output_path, f), f)

        tasks[task_id].update({"status": "completed", "progress": 100, "last_log": "完了", "completed_at": time.time()})

    except Exception as e:
        print(f"[ERROR] task_id={task_id}, error={str(e)}")
        tasks[task_id].update({"status": "failed", "error": str(e), "completed_at": time.time()})

# --- APIエンドポイント ---

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
    output_format: str = Form("mp3")
):
    task_id = str(uuid.uuid4())
    os.makedirs(os.path.join(BASE_TEMP_DIR, task_id, "input"), exist_ok=True)

    # 空リストはNoneとして扱う
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
