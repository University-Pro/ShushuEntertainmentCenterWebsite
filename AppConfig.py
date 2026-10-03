"""项目全局配置。

路径、端口、密钥等常量集中在此，其余模块一律从这里取用，
避免硬编码散落在各个文件里。
"""

import os
from ipaddress import ip_network
from pathlib import Path

# ------------------------------------------------------------------ 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "Web"
TEMPLATE_FOLDER = WEB_ROOT / "Templates"
STATIC_FOLDER = WEB_ROOT / "Static"
DATA_FOLDER = PROJECT_ROOT / "Data"
DATABASE_FILE = DATA_FOLDER / "MainPage.db"

# ------------------------------------------------------------------ 服务配置
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 12339
DEBUG_MODE = False

# 默认不信任转发头；仅配置实际反向代理的 IP / CIDR，不能填任意客户端网段。
TRUSTED_PROXY_NETWORKS = tuple(
    ip_network(value.strip(), strict=False)
    for value in os.environ.get("SHUSHU_TRUSTED_PROXIES", "").split(",")
    if value.strip()
)

# ------------------------------------------------------------------ 安全配置
#
# 会话密钥不再硬编码。Flask 用的是客户端 session，整个登录态就靠这个密钥签名，
# 一旦随源码泄露，任何人都能自己签一个 {"AdminUser": "admin"} 的 cookie，
# 密码和两步验证全部绕过。所以改成首次启动随机生成并落盘到 Data/SecretKey.txt。
#
# 需要固定密钥（多进程/多机共享会话）时，设环境变量 SHUSHU_SECRET_KEY 覆盖。
SECRET_KEY_FILE = DATA_FOLDER / "SecretKey.txt"
SECRET_KEY_ENV_NAME = "SHUSHU_SECRET_KEY"
SECRET_KEY_BYTES = 48
SESSION_COOKIE_NAME = "ShuShuSession"
SESSION_LIFETIME_DAYS = 7
# 走 HTTPS 时打开，浏览器就不再通过明文 HTTP 回传这个 cookie。
# 可以用环境变量 SESSION_COOKIE_SECURE=True 覆盖，容器编排里直接设即可。
SESSION_COOKIE_SECURE = os.environ.get(
    "SESSION_COOKIE_SECURE", ""
).strip().lower() in ("1", "true", "yes", "on")


def LoadOrCreateSecretKey():
    """读取持久化的会话密钥，不存在就生成一个。"""
    from os import environ
    from secrets import token_urlsafe

    from_env = environ.get(SECRET_KEY_ENV_NAME)
    if from_env:
        return from_env

    try:
        if SECRET_KEY_FILE.exists():
            existing = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if existing:
                return existing

        DATA_FOLDER.mkdir(parents=True, exist_ok=True)
        generated = token_urlsafe(SECRET_KEY_BYTES)
        SECRET_KEY_FILE.write_text(generated, encoding="utf-8")
        try:
            SECRET_KEY_FILE.chmod(0o600)
        except OSError:
            pass    # Windows / 某些文件系统不支持，忽略
        return generated
    except OSError:
        # 落盘失败也不能退回固定密钥：用进程内随机值，
        # 代价是重启后会话失效，但至少不可预测。
        return token_urlsafe(SECRET_KEY_BYTES)

# ------------------------------------------------------------------ 两步验证
# 显示在验证器 App 里的服务名，随便改，不影响已绑定的密钥
TOTP_ISSUER_NAME = "鼠鼠娱乐中心"
# 允许的时间偏移（个 30 秒窗口），1 表示容忍前后各 30 秒
TOTP_VALID_WINDOW = 1

# ------------------------------------------------------------------ 访问统计
ANALYTICS_ENABLED = True
# 访问记录保留天数，超期自动清理（启动时与每天首次写入时各检查一次）
ANALYTICS_RETENTION_DAYS = 90
# 是否记录明文 IP。关掉后只保留不可逆的访客哈希，独立访客数依然准确，
# 但明细里就看不到具体来源 IP 了。
ANALYTICS_STORE_RAW_IP = True
# 这些前缀不记录：
#   /Static/ 会把表撑爆；/Health 是探活噪音；
#   /Admin/ 是站长自己的操作，会把「热门页面」冲掉——后台登录情况另有
#   AdminTotp / LoginAttempt 两张表在管，不需要混进访客统计
ANALYTICS_IGNORED_PREFIXES = (
    "/Static/", "/Health", "/favicon.ico", "/robots.txt", "/Admin/",
)
# User-Agent 截断长度，防止超长 UA 撑大数据库
ANALYTICS_MAX_USER_AGENT_LENGTH = 300
# 热门页面 / 来源排行取前几名
ANALYTICS_TOP_LIMIT = 10

# ------------------------------------------------------------------ 两步验证恢复码
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_BYTES = 5
# 连续失败多少次锁定账号、锁定多少分钟（计数记在数据库，不随 cookie 重置）
MAX_LOGIN_FAILURES = 5
LOGIN_LOCKOUT_MINUTES = 15

# ------------------------------------------------------------------ 初始管理员
# 仅在数据库首次创建时写入，之后请到后台「账号安全」中修改。
DEFAULT_ADMIN_USERNAME = "admin"
# 仅首次建库使用；未设置则拒绝初始化，已有账号不会被环境变量重置。
DEFAULT_ADMIN_PASSWORD = os.environ.get("SHUSHU_ADMIN_PASSWORD", "")
