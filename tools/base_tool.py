import os
import shutil
import zipfile
from typing import Tuple

BASE_TEMP_DIR = "/tmp/media_master"
DB_PATH = "/tmp/media_master/colab_config.db"


def init_base_dirs() -> None:
    os.makedirs(BASE_TEMP_DIR, exist_ok=True)


def prepare_task_dirs(task_id: str) -> Tuple[str, str, str]:
    session_path = os.path.join(BASE_TEMP_DIR, task_id)
    input_path = os.path.join(session_path, "input")
    output_path = os.path.join(session_path, "output")
    os.makedirs(input_path, exist_ok=True)
    os.makedirs(output_path, exist_ok=True)
    return session_path, input_path, output_path


def create_result_zip(output_path: str, zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for file_name in os.listdir(output_path):
            zf.write(os.path.join(output_path, file_name), file_name)


def cleanup_task(task_id: str) -> None:
    shutil.rmtree(os.path.join(BASE_TEMP_DIR, task_id), ignore_errors=True)
