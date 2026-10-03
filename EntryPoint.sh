#!/bin/sh
# 容器启动脚本。
#
# 建库必须发生在 gunicorn 拉 worker 之前：CreateApplication() 是工厂函数，
# 每个 worker 都会调一次，把建表放在里面会变成多进程同时建表。
set -e

PORT="${SERVER_PORT:-12339}"
WORKERS="${GUNICORN_WORKERS:-2}"
THREADS="${GUNICORN_THREADS:-4}"
TIMEOUT="${GUNICORN_TIMEOUT:-60}"

echo "正在检查数据库…"
python - <<'PYCODE'
from Core.Database import InitializeDatabase
from Core import Analytics

InitializeDatabase()

# 每次启动清一次过期访问记录。放在这里而不是应用里，
# 是为了避免多 worker 同时执行。
try:
    removed = Analytics.PurgeOldVisits(force=True)
    if removed:
        print("已清理过期访问记录 {} 条".format(removed))
except Exception as error:
    print("访问记录清理失败（不影响启动）：{}".format(error))
PYCODE

echo "启动 gunicorn —— 端口 ${PORT}，${WORKERS} 进程 × ${THREADS} 线程"

# SQLite 是单写者模型。进程数不要开太大，靠线程扛并发就够了；
# 真遇到 "database is locked" 就把 GUNICORN_WORKERS 降到 1。
exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WORKERS}" \
    --threads "${THREADS}" \
    --timeout "${TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    --log-level "${GUNICORN_LOG_LEVEL:-info}" \
    "RunServer:CreateApplication()"