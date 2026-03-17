import asyncio
import os
import time
from typing import Dict, List

from .base_tool import BASE_TEMP_DIR, create_result_zip, cleanup_task, prepare_task_dirs
from .config_store import get_colab_url
from .image_tools import convert_heic_to_jpg, convert_jpegs_to_pdf, convert_pdf_to_pngs
from .video_tools import convert_to_mp3, is_ngrok_error, request_youtube_batch

tasks: Dict[str, dict] = {}
VALID_TOOL_IDS = {"youtube", "heic-jpg", "m4a-mp3", "mp4-mp3", "jpeg-pdf", "pdf-png"}


async def cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        now = time.time()
        to_delete = [
            tid
            for tid, task in list(tasks.items())
            if task.get("completed_at") and now - task["completed_at"] > 3600
        ]
        for task_id in to_delete:
            tasks.pop(task_id, None)
            cleanup_task(task_id)


def process_task(task_id: str, tool_id: str, url_text: str, filenames: List[str], output_format: str = "mp3") -> None:
    session_path, input_path, output_path = prepare_task_dirs(task_id)

    try:
        if tool_id not in VALID_TOOL_IDS:
            raise ValueError(f"無効なtool_idです: {tool_id}")

        if output_format not in ("mp3", "mp4"):
            raise ValueError(f"無効なoutput_formatです: {output_format}")

        if tool_id == "youtube" and url_text:
            tasks[task_id]["last_log"] = f"Colabへリクエスト送信中... ({output_format})"
            try:
                request_youtube_batch(url_text, output_format, get_colab_url(), session_path, output_path)
                tasks[task_id]["last_log"] = "取得完了"
                tasks[task_id]["progress"] = 90
            except Exception as exc:
                error_msg = str(exc)
                if is_ngrok_error(error_msg) or "サーバーが停止しています" in error_msg:
                    raise Exception("サーバーが停止しています。管理者にお問い合わせください。")
                raise Exception(f"Colab接続失敗: {error_msg}")

        elif tool_id == "jpeg-pdf":
            image_paths = [os.path.join(input_path, filename) for filename in filenames]
            convert_jpegs_to_pdf(image_paths, os.path.join(output_path, "output.pdf"))
            tasks[task_id]["progress"] = 80

        else:
            for index, filename in enumerate(filenames):
                in_file = os.path.join(input_path, filename)
                tasks[task_id]["last_log"] = f"処理中: {filename}"
                tasks[task_id]["progress"] = int(20 + (index / len(filenames)) * 60)

                if tool_id == "heic-jpg":
                    out_file = os.path.join(output_path, f"{os.path.splitext(filename)[0]}.jpg")
                    try:
                        convert_heic_to_jpg(in_file, out_file)
                    except Exception as exc:
                        raise Exception(f"HEIC変換に失敗しました: {filename}。{exc}")

                elif tool_id in ["m4a-mp3", "mp4-mp3"]:
                    out_file = os.path.join(output_path, f"{os.path.splitext(filename)[0]}.mp3")
                    convert_to_mp3(in_file, out_file)

                elif tool_id == "pdf-png":
                    convert_pdf_to_pngs(in_file, output_path, os.path.splitext(filename)[0])

        tasks[task_id]["last_log"] = "ファイルを圧縮中..."
        final_zip = os.path.join(session_path, "result.zip")
        create_result_zip(output_path, final_zip)

        tasks[task_id].update(
            {
                "status": "completed",
                "progress": 100,
                "last_log": "完了",
                "completed_at": time.time(),
            }
        )

    except Exception as exc:
        print(f"[ERROR] task_id={task_id}, error={str(exc)}")
        tasks[task_id].update({"status": "failed", "error": str(exc), "completed_at": time.time()})
