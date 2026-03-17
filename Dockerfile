# Pythonの軽量版を使用
FROM python:3.10-slim

# 環境変数の設定
# .pycファイルを作成しないようにする
ENV PYTHONDONTWRITEBYTECODE=1
# 標準出力をバッファリングせず、リアルタイムにログを表示
ENV PYTHONUNBUFFERED=1

# システム依存関係のインストールとクリーンアップ
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    poppler-utils \
    libheif-dev \
    libheif1 \
    libffi-dev \
    gcc \
    imagemagick \
    libmagickwand-dev \
    && rm -rf /var/lib/apt/lists/*

# ImageMagickのHEIC読み取り制限を解除
RUN sed -i 's/<policy domain="coder" rights="none" pattern="HEIC" \/>/<!-- HEIC allowed -->/' /etc/ImageMagick-6/policy.xml 2>/dev/null || true && \
    sed -i 's/<policy domain="coder" rights="none" pattern="HEIF" \/>/<!-- HEIF allowed -->/' /etc/ImageMagick-6/policy.xml 2>/dev/null || true

WORKDIR /app

# 一時ディレクトリの作成と権限設定
# Hugging Face SpacesはユーザーID 1000で実行されるため、そのユーザーが書き込めるようにする
RUN mkdir -p /tmp/media_master && chmod 777 /tmp/media_master

# 依存ライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt \
    --timeout 120

# アプリケーションファイルのコピー
COPY . .

# セキュリティと動作のため、/app 全体に権限を付与 (Hugging Faceの慣習)
RUN chmod -R 777 /app

# デフォルトのポート
EXPOSE 7860

# アプリケーションの起動
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
