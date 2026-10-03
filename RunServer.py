"""程序入口。

启动：
    python RunServer.py

首次运行会自动创建 Data/MainPage.db 并写入参考图中的初始内容。
初始管理员：admin，首次建库密码由 SHUSHU_ADMIN_PASSWORD 环境变量提供。
"""

import time
from datetime import timedelta

from flask import Flask, g, request

from Api.AdminApi import AdminBlueprint
from Api.AnalyticsApi import AnalyticsBlueprint
from Api.PublicApi import PublicBlueprint
from Core import Analytics
from AppConfig import (
    ANALYTICS_ENABLED, DEBUG_MODE, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME,
    LoadOrCreateSecretKey, SERVER_HOST, SERVER_PORT,
    SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE, SESSION_LIFETIME_DAYS,
    STATIC_FOLDER, TEMPLATE_FOLDER,
)
from Core.Database import InitializeDatabase

# 允许内联 style 是因为卡片主题色、背景图要靠 style 属性下发（CSP 的 style-src
# 认 'unsafe-inline' 才会放行 style 属性）。script-src 保持 'self'，
# 模板里已无内联脚本，XSS 的主要入口就堵住了。
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "img-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    "script-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def CreateApplication():
    """组装 Flask 应用。"""
    application = Flask(
        __name__,
        template_folder=str(TEMPLATE_FOLDER),
        static_folder=str(STATIC_FOLDER),
        static_url_path="/Static",
    )
    application.config.update(
        SECRET_KEY=LoadOrCreateSecretKey(),
        SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_LIFETIME_DAYS),
        JSON_AS_ASCII=False,
        TEMPLATES_AUTO_RELOAD=DEBUG_MODE,
    )

    application.register_blueprint(PublicBlueprint)
    application.register_blueprint(AdminBlueprint)
    application.register_blueprint(AnalyticsBlueprint)

    @application.before_request
    def MarkRequestStart():
        g.ShuShuRequestStart = time.perf_counter()

    @application.after_request
    def RecordPageVisit(response):
        """记录一次页面访问。

        统计绝不能影响正常请求，所以整个写入包在 try 里——写不进去最多是
        少一条统计，不该让用户看到 500。
        """
        if not ANALYTICS_ENABLED:
            return response

        if not Analytics.ShouldRecord(request.path, request.method):
            return response

        try:
            started = g.get("ShuShuRequestStart") or time.perf_counter()
            Analytics.RecordVisit(
                path=request.path,
                status_code=response.status_code,
                duration_ms=int((time.perf_counter() - started) * 1000),
                client_ip=Analytics.ResolveClientIp(request.remote_addr),
                user_agent=request.headers.get("User-Agent", ""),
                referer=request.headers.get("Referer", ""),
            )
        except Exception as error:
            application.logger.warning("访问记录写入失败：%s", error)

        return response

    @application.after_request
    def ApplySecurityHeaders(response):
        """补齐浏览器侧的默认防护。"""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # frame-ancestors 已经能防嵌套，这条是给老浏览器兜底
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        return response

    return application


def PrintSecurityWarnings():
    """启动时体检。默认口令 + 监听 0.0.0.0 是本项目风险最高的组合。"""
    from Core import Repository

    warnings = []

    account = Repository.GetAdmin(DEFAULT_ADMIN_USERNAME)
    if account and DEFAULT_ADMIN_PASSWORD and Repository.VerifyAdmin(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD):
        warnings.append(
            "后台仍在使用环境变量提供的初始口令。\n"
            "      建议登录后台 →「账号安全」修改密码，并移除初始化密码环境变量。"
        )

    totp_record = Repository.GetTotpRecord(DEFAULT_ADMIN_USERNAME)
    if not totp_record or not totp_record["IsEnabled"]:
        warnings.append("尚未开启两步验证。后台 →「账号安全」→「两步验证」。")

    if SERVER_HOST == "0.0.0.0":
        warnings.append(
            "服务监听 0.0.0.0，同网段任何人都能访问。\n"
            "      不做端口映射到公网；校园网/宿舍网环境下请确认这一点。"
        )

    if warnings:
        print("!" * 60)
        print("  安全提醒")
        for index, text in enumerate(warnings, start=1):
            print("  {}. {}".format(index, text))
        print("!" * 60)


def Main():
    InitializeDatabase()
    try:
        Analytics.PurgeOldVisits()
    except Exception as error:
        print("  访问记录清理失败（不影响启动）：{}".format(error))

    application = CreateApplication()

    print("=" * 56)
    print("  鼠鼠娱乐中心 —— 已启动")
    print("  首页      http://{}:{}/".format(SERVER_HOST, SERVER_PORT))
    print("  后台管理  http://{}:{}/Admin/Login".format(SERVER_HOST, SERVER_PORT))
    print("=" * 56)

    PrintSecurityWarnings()

    application.run(host=SERVER_HOST, port=SERVER_PORT, debug=DEBUG_MODE)


if __name__ == "__main__":
    Main()
