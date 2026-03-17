import os
import requests
import zipfile
from pydub import AudioSegment


def is_ngrok_error(text: str) -> bool:
    return "ERR_NGROK" in text or "<!DOCTYPE html>" in text or "ngrok" in text.lower()


def request_youtube_batch(url_text: str, output_format: str, colab_url: str, session_path: str, output_path: str) -> None:
    if not colab_url:
        raise Exception("サーバーが停止しています。管理者にお問い合わせください。")

    urls = [u.strip() for u in url_text.split("\n") if u.strip()]
    response = requests.post(
        f"{colab_url.rstrip('/')}/batch-download",
        json={"urls": urls, "format": output_format},
        timeout=900,
    )

    if response.status_code != 200:
        error_body = response.text
        if is_ngrok_error(error_body):
            raise Exception("サーバーが停止しています。管理者にお問い合わせください。")
        raise Exception(f"Colabエラー: {error_body}")

    colab_zip = os.path.join(session_path, "colab_result.zip")
    with open(colab_zip, "wb") as f:
        f.write(response.content)

    with zipfile.ZipFile(colab_zip, "r") as zf:
        zf.extractall(output_path)


def convert_to_mp3(in_file: str, out_file: str) -> None:
    audio = AudioSegment.from_file(in_file)
    audio.export(out_file, format="mp3")
