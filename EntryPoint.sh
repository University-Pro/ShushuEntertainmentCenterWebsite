#!/bin/sh
# 容器启动脚本。
#
# 仅用于 Docker：读取运行参数，再启动 Gunicorn。
# --preload 在主进程创建应用并初始化数据，然后再启动 worker。
set -e

PORT="${SERVER_PORT:-12339}"
WORKERS="${GUNICORN_WORKERS:-2}"
THREADS="${GUNICORN_THREADS:-4}"
TIMEOUT="${GUNICORN_TIMEOUT:-60}"

echo "启动 gunicorn —— 端口 ${PORT}，${WORKERS} 进程 × ${THREADS} 线程"

# SQLite 是单写者模型。进程数不要开太大，靠线程扛并发就够了；
# 真遇到 "database is locked" 就把 GUNICORN_WORKERS 降到 1。
exec gunicorn \
    --preload \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WORKERS}" \
    --threads "${THREADS}" \
    --timeout "${TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    --log-level "${GUNICORN_LOG_LEVEL:-info}" \
    "RunServer:CreateApplication()"