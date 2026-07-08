FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i \
            -e 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' \
            -e 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' \
            /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i \
            -e 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' \
            -e 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' \
            /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential curl ffmpeg; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
        --index-url https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
    && pip install --no-cache-dir -r requirements.txt \
        --index-url https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com

COPY app ./app
COPY knowledge ./knowledge
COPY scripts ./scripts
COPY research ./research

RUN useradd -m -u 10001 appuser \
    && mkdir -p /app_cache /app_data \
    && chown -R appuser:appuser /app /app_cache /app_data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
