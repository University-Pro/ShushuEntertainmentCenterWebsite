# 鼠鼠娱乐中心 —— 生产镜像
#
# 与本地开发的差别只有一处：本地跑 RunServer.py（Flask 自带开发服务器），
# 容器里跑 gunicorn。

FROM python:3.13-slim

# PYTHONDONTWRITEBYTECODE：不生成 .pyc，镜像更干净
# PYTHONUNBUFFERED：日志实时打到 docker logs，不被缓冲吞掉
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 容器里的「今天」必须和你的时区一致，否则访问统计按天分组会错 8 小时。
# python:slim 不带 tzdata，得单独装。
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

# 依赖单独一层：改业务代码时不必重装依赖
COPY Requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r Requirements.txt

# 注意：Data/ 被 .dockerignore 排除在外，不会进镜像。
# 这一点很关键——Data/ 里放着 SecretKey.txt，打进镜像层就等于把会话密钥
# 随镜像分发出去了，任何人拿到镜像都能伪造管理员登录态。
COPY . .

# 以非 root 运行
RUN useradd --create-home --shell /usr/sbin/nologin --uid 1000 shushu \
 && mkdir -p /app/Data \
 && chmod +x /app/EntryPoint.sh \
 && chown -R shushu:shushu /app

USER shushu

# 数据库与会话密钥都落在这里，必须挂载出去，否则重建容器数据就没了
VOLUME ["/app/Data"]

EXPOSE 12339

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import sys,urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:12339/Health', timeout=4).status == 200 else 1)"

CMD ["./EntryPoint.sh"]