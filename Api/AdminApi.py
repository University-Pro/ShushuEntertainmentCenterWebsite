"""后台管理路由。

页面：/Admin/Login 登录，/Admin/ 控制台
接口：统一挂在 /Admin/Api/ 下，全部需要登录态。
"""

import functools
import time

from flask import (
    Blueprint, jsonify, redirect, render_template, request, session, url_for,
)

from AppConfig import (
    LOGIN_LOCKOUT_MINUTES, MAX_LOGIN_FAILURES, SESSION_LIFETIME_DAYS,
)
from Core import Analytics, Repository, TotpService

AdminBlueprint = Blueprint("AdminApi", __name__, url_prefix="/Admin")

# 密码已通过、等待第二因子的会话最多保留多久（秒）
PENDING_TOTP_SECONDS = 300


def _ClientIp():
    """取请求来源 IP，与访问统计共用同一套解析规则。"""
    return Analytics.ResolveClientIp(
        request.remote_addr, request.headers.get("X-Forwarded-For", "")
    )


def _BuildLockMessage(attempt_key):
    """被锁时返回提示文案，未锁定返回 None。"""
    remaining = Repository.GetLockRemainingSeconds(attempt_key)
    if remaining <= 0:
        return None

    minutes = remaining // 60 + (1 if remaining % 60 else 0)
    return "失败次数过多，请约 {} 分钟后再试".format(minutes)


# ------------------------------------------------------------------ 登录校验


def LoginRequired(view_function):
    """装饰器：未登录时页面跳登录页、接口返回 401。"""

    @functools.wraps(view_function)
    def Wrapper(*args, **kwargs):
        if not session.get("AdminUser"):
            if request.path.startswith("/Admin/Api/"):
                return jsonify({"Success": False, "Message": "登录状态已失效，请重新登录"}), 401
            return redirect(url_for("AdminApi.LoginPage"))
        return view_function(*args, **kwargs)

    return Wrapper


def _ReadJson():
    return request.get_json(silent=True) or {}


def _AsInt(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ 页面


@AdminBlueprint.route("/Login", methods=["GET"])
def LoginPage():
    if session.get("AdminUser"):
        return redirect(url_for("AdminApi.DashboardPage"))
    return render_template(
        "AdminLoginPage.html",
        DefaultTheme=Repository.GetSetting("DefaultTheme", "auto"),
    )


@AdminBlueprint.route("/", methods=["GET"])
@LoginRequired
def DashboardPage():
    return render_template(
        "AdminPage.html",
        AdminUser=session.get("AdminUser"),
        DefaultTheme=Repository.GetSetting("DefaultTheme", "auto"),
    )


# ------------------------------------------------------------------ 登录 / 登出


@AdminBlueprint.route("/Api/Login", methods=["POST"])
def DoLogin():
    payload = _ReadJson()
    user_name = (payload.get("UserName") or "").strip()
    password = payload.get("Password") or ""

    if not user_name or not password:
        return jsonify({"Success": False, "Message": "请填写账号与密码"}), 400

    # 密码阶段按「来源 IP + 用户名」限流：攻击者只能锁住自己，
    # 不会像账号级锁定那样被用来把站长永久挡在门外
    attempt_key = Repository.BuildPasswordAttemptKey(user_name, _ClientIp())

    lock_message = _BuildLockMessage(attempt_key)
    if lock_message:
        return jsonify({"Success": False, "Message": lock_message}), 429

    verified = Repository.VerifyAdmin(user_name, password)
    if not verified:
        remaining = Repository.RegisterFailedAttempt(
            attempt_key, user_name, MAX_LOGIN_FAILURES, LOGIN_LOCKOUT_MINUTES
        )
        if remaining <= 0:
            return jsonify({
                "Success": False,
                "Message": "失败次数过多，请 {} 分钟后再试".format(LOGIN_LOCKOUT_MINUTES),
            }), 429
        return jsonify({
            "Success": False,
            "Message": "账号或密码不正确，还可尝试 {} 次".format(remaining),
        }), 401

    session.permanent = True

    # 开了两步验证就先挂起，等第二因子通过才真正登录
    totp_record = Repository.GetTotpRecord(verified)
    if totp_record and totp_record["IsEnabled"]:
        session["PendingAdminUser"] = verified
        # 记下时间，挂起态只给几分钟。默认 session 是 7 天，
        # 过了第一因子就跟着续 7 天不合理
        session["PendingSince"] = time.time()
        session.pop("AdminUser", None)
        return jsonify({"Success": True, "Data": {"NeedTotp": True, "UserName": verified}})

    Repository.ClearAllAttemptsForUser(verified)
    session["AdminUser"] = verified
    session.pop("PendingAdminUser", None)
    return jsonify({"Success": True, "Data": {"NeedTotp": False, "UserName": verified}})


@AdminBlueprint.route("/Api/VerifyTotp", methods=["POST"])
def VerifyTotp():
    """登录第二步：校验动态码或恢复码。"""
    pending_user = session.get("PendingAdminUser")
    if not pending_user:
        return jsonify({"Success": False, "Message": "登录会话已过期，请重新登录"}), 401

    # 挂起态限时，避免「只过了密码」的半成品会话长期有效
    pending_since = session.get("PendingSince") or 0
    if time.time() - pending_since > PENDING_TOTP_SECONDS:
        session.pop("PendingAdminUser", None)
        session.pop("PendingSince", None)
        return jsonify({"Success": False, "Message": "验证超时，请重新登录"}), 401

    record = Repository.GetTotpRecord(pending_user)
    if not record or not record["IsEnabled"]:
        return jsonify({"Success": False, "Message": "该账号未开启两步验证"}), 400

    code = (_ReadJson().get("Code") or "").strip()
    if not code:
        return jsonify({"Success": False, "Message": "请输入验证码"}), 400

    # 动态码阶段按用户名封锁。这一步必须在验码之前查：
    # 原先只在 RegisterFailedAttempt 返回 0 时才响应，而锁定时计数已被清零，
    # 后续请求会重新从 1 开始数，等于锁根本没生效。
    attempt_key = Repository.BuildTotpAttemptKey(pending_user)
    lock_message = _BuildLockMessage(attempt_key)
    if lock_message:
        session.pop("PendingAdminUser", None)
        session.pop("PendingSince", None)
        return jsonify({
            "Success": False,
            "Message": lock_message,
            "Data": {"Locked": True},
        }), 429

    used_recovery_code = False
    remaining_codes = None

    if TotpService.VerifyCode(record["TotpSecret"], code):
        passed = True
    else:
        # 动态码不对时再试恢复码；消费走带条件的原子更新，防并发复用同一个码
        passed = Repository.ConsumeTotpRecoveryCode(pending_user, code)
        if passed:
            used_recovery_code = True
            remaining_codes = TotpService.CountUnusedRecoveryCodes(
                (Repository.GetTotpRecord(pending_user) or {}).get("RecoveryCodes", "")
            )

    if not passed:
        remaining = Repository.RegisterFailedAttempt(
            attempt_key, pending_user, MAX_LOGIN_FAILURES, LOGIN_LOCKOUT_MINUTES
        )
        if remaining <= 0:
            session.pop("PendingAdminUser", None)
            session.pop("PendingSince", None)
            return jsonify({
                "Success": False,
                "Message": "失败次数过多，请 {} 分钟后再试".format(LOGIN_LOCKOUT_MINUTES),
                "Data": {"Locked": True},
            }), 429

        return jsonify({
            "Success": False,
            "Message": "验证码不正确，还可尝试 {} 次".format(remaining),
        }), 401

    Repository.ClearAllAttemptsForUser(pending_user)
    session["AdminUser"] = pending_user
    session.pop("PendingAdminUser", None)
    session.pop("PendingSince", None)

    message = "登录成功"
    if used_recovery_code:
        message = "已使用恢复码登录，剩余 {} 个，建议尽快重新生成".format(remaining_codes)

    return jsonify({
        "Success": True,
        "Message": message,
        "Data": {
            "UserName": pending_user,
            "UsedRecoveryCode": used_recovery_code,
            "RemainingRecoveryCodes": remaining_codes,
        },
    })


@AdminBlueprint.route("/Api/Logout", methods=["POST"])
def DoLogout():
    session.pop("AdminUser", None)
    session.pop("PendingAdminUser", None)
    session.pop("PendingSince", None)
    return jsonify({"Success": True})


@AdminBlueprint.route("/Api/ChangePassword", methods=["POST"])
@LoginRequired
def ChangePassword():
    payload = _ReadJson()
    old_password = payload.get("OldPassword") or ""
    new_password = payload.get("NewPassword") or ""

    if len(new_password) < 6:
        return jsonify({"Success": False, "Message": "新密码至少 6 位"}), 400

    user_name = session["AdminUser"]
    if not Repository.VerifyAdmin(user_name, old_password):
        return jsonify({"Success": False, "Message": "原密码不正确"}), 400

    Repository.ChangeAdminPassword(user_name, new_password)
    return jsonify({"Success": True, "Message": "密码已更新"})


# ------------------------------------------------------------------ 两步验证


def _BuildTotpStatus(user_name):
    record = Repository.GetTotpRecord(user_name)
    is_enabled = bool(record and record["IsEnabled"])
    return {
        "IsEnabled": is_enabled,
        "HasPendingSecret": bool(record and record["TotpSecret"] and not is_enabled),
        "UnusedRecoveryCodes": (
            TotpService.CountUnusedRecoveryCodes(record["RecoveryCodes"]) if is_enabled else 0
        ),
    }


@AdminBlueprint.route("/Api/Totp/Status", methods=["GET"])
@LoginRequired
def TotpStatus():
    return jsonify({"Success": True, "Data": _BuildTotpStatus(session["AdminUser"])})


@AdminBlueprint.route("/Api/Totp/Setup", methods=["POST"])
@LoginRequired
def TotpSetup():
    """开始绑定：校验密码 → 生成密钥 → 返回二维码。此时尚未生效。"""
    user_name = session["AdminUser"]

    record = Repository.GetTotpRecord(user_name)
    if record and record["IsEnabled"]:
        return jsonify({
            "Success": False,
            "Message": "两步验证已开启，请先关闭再重新绑定",
        }), 400

    password = _ReadJson().get("Password") or ""
    if not Repository.VerifyAdmin(user_name, password):
        return jsonify({"Success": False, "Message": "密码不正确"}), 400

    secret = TotpService.GenerateSecret()
    Repository.SaveTotpSecret(user_name, secret)

    uri = TotpService.BuildProvisioningUri(user_name, secret)
    return jsonify({
        "Success": True,
        "Data": {
            "Secret": secret,
            "Uri": uri,
            "QrSvg": TotpService.BuildQrSvg(uri),
        },
    })


@AdminBlueprint.route("/Api/Totp/Enable", methods=["POST"])
@LoginRequired
def TotpEnable():
    """用验证器上显示的码确认绑定，成功后返回一次性恢复码。"""
    user_name = session["AdminUser"]

    record = Repository.GetTotpRecord(user_name)
    if not record or not record["TotpSecret"]:
        return jsonify({"Success": False, "Message": "请先获取二维码"}), 400
    if record["IsEnabled"]:
        return jsonify({"Success": False, "Message": "两步验证已经开启了"}), 400

    code = (_ReadJson().get("Code") or "").strip()
    if not TotpService.VerifyCode(record["TotpSecret"], code):
        return jsonify({"Success": False, "Message": "验证码不正确，请确认验证器时间是否准确"}), 400

    recovery_codes = TotpService.GenerateRecoveryCodes()
    Repository.EnableTotp(user_name, TotpService.HashRecoveryCodes(recovery_codes))

    return jsonify({
        "Success": True,
        "Message": "两步验证已开启",
        "Data": {
            "RecoveryCodes": recovery_codes,
            "Status": _BuildTotpStatus(user_name),
        },
    })


@AdminBlueprint.route("/Api/Totp/RegenerateRecoveryCodes", methods=["POST"])
@LoginRequired
def TotpRegenerateRecoveryCodes():
    """重新生成恢复码，旧的立即作废。需要密码 + 当前动态码。"""
    user_name = session["AdminUser"]

    record = Repository.GetTotpRecord(user_name)
    if not record or not record["IsEnabled"]:
        return jsonify({"Success": False, "Message": "两步验证尚未开启"}), 400

    payload = _ReadJson()
    if not Repository.VerifyAdmin(user_name, payload.get("Password") or ""):
        return jsonify({"Success": False, "Message": "密码不正确"}), 400
    if not TotpService.VerifyCode(record["TotpSecret"], payload.get("Code") or ""):
        return jsonify({"Success": False, "Message": "验证码不正确"}), 400

    recovery_codes = TotpService.GenerateRecoveryCodes()
    Repository.UpdateTotpRecoveryCodes(user_name, TotpService.HashRecoveryCodes(recovery_codes))

    return jsonify({
        "Success": True,
        "Message": "恢复码已重新生成",
        "Data": {
            "RecoveryCodes": recovery_codes,
            "Status": _BuildTotpStatus(user_name),
        },
    })


@AdminBlueprint.route("/Api/Totp/Disable", methods=["POST"])
@LoginRequired
def TotpDisable():
    """关闭两步验证。需要密码 + 当前动态码（或一个恢复码）。"""
    user_name = session["AdminUser"]

    record = Repository.GetTotpRecord(user_name)
    if not record or not record["IsEnabled"]:
        return jsonify({"Success": False, "Message": "两步验证尚未开启"}), 400

    payload = _ReadJson()
    if not Repository.VerifyAdmin(user_name, payload.get("Password") or ""):
        return jsonify({"Success": False, "Message": "密码不正确"}), 400

    code = payload.get("Code") or ""
    if not TotpService.VerifyCode(record["TotpSecret"], code):
        matched, _ = TotpService.ConsumeRecoveryCode(record["RecoveryCodes"], code)
        if not matched:
            return jsonify({"Success": False, "Message": "验证码不正确"}), 400

    Repository.DisableTotp(user_name)
    return jsonify({"Success": True, "Message": "两步验证已关闭"})


# ------------------------------------------------------------------ 总览数据


@AdminBlueprint.route("/Api/Overview", methods=["GET"])
@LoginRequired
def Overview():
    """后台一次性拉取全部可编辑数据。"""
    return jsonify({
        "Success": True,
        "Data": {
            "Settings": Repository.GetSettings(),
            "Panels": Repository.GetLogPanels(),
            "Notices": Repository.GetNotices(),
            "Logs": Repository.GetUpdateLogs(),
            "Cards": Repository.GetServiceCards(),
            "Totp": _BuildTotpStatus(session["AdminUser"]),
        },
    })


# ------------------------------------------------------------------ 站点配置


@AdminBlueprint.route("/Api/Setting/Save", methods=["POST"])
@LoginRequired
def SaveSetting():
    payload = _ReadJson()
    mapping = payload.get("Settings") or {}
    if not isinstance(mapping, dict) or not mapping:
        return jsonify({"Success": False, "Message": "没有需要保存的配置"}), 400

    Repository.SaveSettings({str(key): str(value) for key, value in mapping.items()})
    return jsonify({"Success": True})


# ------------------------------------------------------------------ 日志面板


@AdminBlueprint.route("/Api/Panel/Save", methods=["POST"])
@LoginRequired
def SavePanel():
    payload = _ReadJson()
    panel_key = payload.get("PanelKey")
    if not panel_key:
        return jsonify({"Success": False, "Message": "缺少 PanelKey"}), 400

    Repository.SaveLogPanel(
        panel_key=panel_key,
        title=payload.get("Title", ""),
        subtitle=payload.get("Subtitle", ""),
        link_text=payload.get("SubtitleLinkText", ""),
        link_url=payload.get("SubtitleLinkUrl", ""),
        sort_order=_AsInt(payload.get("SortOrder")),
        is_visible=_AsInt(payload.get("IsVisible"), 1),
    )
    return jsonify({"Success": True})


# ------------------------------------------------------------------ 提示行


@AdminBlueprint.route("/Api/Notice/Save", methods=["POST"])
@LoginRequired
def SaveNotice():
    payload = _ReadJson()
    notice_id = Repository.SaveNotice(
        notice_id=_AsInt(payload.get("Id")) or None,
        panel_key=payload.get("PanelKey", "RESOURCE"),
        prefix=payload.get("Prefix", ""),
        content=payload.get("Content", ""),
        link_url=payload.get("LinkUrl", ""),
        sort_order=_AsInt(payload.get("SortOrder")),
    )
    return jsonify({"Success": True, "Data": {"Id": notice_id}})


@AdminBlueprint.route("/Api/Notice/Delete", methods=["POST"])
@LoginRequired
def DeleteNotice():
    notice_id = _AsInt(_ReadJson().get("Id"))
    if not notice_id:
        return jsonify({"Success": False, "Message": "缺少 Id"}), 400

    Repository.DeleteNotice(notice_id)
    return jsonify({"Success": True})


# ------------------------------------------------------------------ 更新日志


@AdminBlueprint.route("/Api/Log/Save", methods=["POST"])
@LoginRequired
def SaveLog():
    payload = _ReadJson()
    panel_key = payload.get("PanelKey", "RESOURCE")
    sort_order = _AsInt(payload.get("SortOrder"))

    if not payload.get("Id") and sort_order <= 0:
        sort_order = Repository.GetNextLogSortOrder(panel_key)

    log_id = Repository.SaveUpdateLog(
        log_id=_AsInt(payload.get("Id")) or None,
        panel_key=panel_key,
        log_date=payload.get("LogDate", ""),
        title=payload.get("Title", ""),
        content=payload.get("Content", ""),
        link_url=payload.get("LinkUrl", ""),
        sort_order=sort_order,
        is_visible=_AsInt(payload.get("IsVisible"), 1),
    )
    return jsonify({"Success": True, "Data": {"Id": log_id}})


@AdminBlueprint.route("/Api/Log/Delete", methods=["POST"])
@LoginRequired
def DeleteLog():
    log_id = _AsInt(_ReadJson().get("Id"))
    if not log_id:
        return jsonify({"Success": False, "Message": "缺少 Id"}), 400

    Repository.DeleteUpdateLog(log_id)
    return jsonify({"Success": True})


# ------------------------------------------------------------------ 服务卡片


@AdminBlueprint.route("/Api/Card/Save", methods=["POST"])
@LoginRequired
def SaveCard():
    payload = _ReadJson()
    card_id = Repository.SaveServiceCard(
        card_id=_AsInt(payload.get("Id")) or None,
        title=payload.get("Title", ""),
        subtitle=payload.get("Subtitle", ""),
        target_url=payload.get("TargetUrl", ""),
        image_url=payload.get("ImageUrl", ""),
        theme_color=payload.get("ThemeColor", "#3B82F6"),
        sort_order=_AsInt(payload.get("SortOrder")),
        is_visible=_AsInt(payload.get("IsVisible"), 1),
    )
    return jsonify({"Success": True, "Data": {"Id": card_id}})


@AdminBlueprint.route("/Api/Card/Delete", methods=["POST"])
@LoginRequired
def DeleteCard():
    card_id = _AsInt(_ReadJson().get("Id"))
    if not card_id:
        return jsonify({"Success": False, "Message": "缺少 Id"}), 400

    Repository.DeleteServiceCard(card_id)
    return jsonify({"Success": True})