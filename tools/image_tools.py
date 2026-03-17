import os
import subprocess
from typing import List

from PIL import Image
from pdf2image import convert_from_path

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    PILLOW_HEIF_AVAILABLE = True
except Exception:
    PILLOW_HEIF_AVAILABLE = False


def convert_heic_to_jpg(in_file: str, out_file: str) -> None:
    converted = False

    try:
        result = subprocess.run(
            ["convert", in_file, "-quality", "95", out_file],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0 and os.path.exists(out_file):
            converted = True
    except Exception:
        pass

    if not converted and PILLOW_HEIF_AVAILABLE:
        img = Image.open(in_file)
        img.convert("RGB").save(out_file, "JPEG", quality=95)
        converted = True

    if not converted:
        raise Exception(
            "HEIC変換に失敗しました。ImageMagickおよびpillow-heifが利用できません。"
        )


def convert_jpegs_to_pdf(input_files: List[str], out_pdf: str) -> None:
    images = [Image.open(path).convert("RGB") for path in input_files]
    if not images:
        raise Exception("変換対象の画像がありません")
    images[0].save(out_pdf, "PDF", save_all=True, append_images=images[1:])


def convert_pdf_to_pngs(in_file: str, output_dir: str, base_name: str) -> None:
    pages = convert_from_path(in_file)
    for index, page in enumerate(pages):
        out_file = os.path.join(output_dir, f"{base_name}_{index}.png")
        page.save(out_file, "PNG")
