"""两步验证（TOTP）服务。

遵循 RFC 6238，兼容 Google Authenticator / Microsoft Authenticator /
Authy / 1Password 等任意标准验证器。

这里只负责「算码 / 验码 / 生成二维码 / 生成恢复码」，
读写数据库的部分在 Repository 里。密钥本身用 pyotp 生成与校验，
不自己实现密码学。
"""

import io
import json
import secrets

import pyotp
import qrcode
import qrcode.image.svg
from werkzeug.security import check_password_hash, generate_password_hash

from AppConfig import (
    RECOVERY_CODE_BYTES, RECOVERY_CODE_COUNT, TOTP_ISSUER_NAME, TOTP_VALID_WINDOW,
)

# 恢复码字母表：去掉 0/O、1/I/L 这些容易看错的字符
RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# 用户可能在验证码里带空格或连字符，统一清掉
_CODE_NOISE = str.maketrans("", "", " -")


# ------------------------------------------------------------------ 密钥


def GenerateSecret():
    """生成一个新的 base32 密钥。"""
    return pyotp.random_base32()


def BuildProvisioningUri(user_name, secret):
    """生成 otpauth:// 链接，验证器 App 扫的就是它。"""
    return pyotp.TOTP(secret).provisioning_uri(
        name=user_name, issuer_name=TOTP_ISSUER_NAME
    )


def BuildQrSvg(content):
    """把 otpauth 链接渲染成 SVG 字符串，前端直接内嵌，不需要额外图片接口。"""
    factory = qrcode.image.svg.SvgPathImage
    image = qrcode.make(content, image_factory=factory, box_size=10, border=2)

    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


# ------------------------------------------------------------------ 验码


def VerifyCode(secret, code, window=None):
    """校验 6 位动态码。window 为允许的时间偏移窗口数。"""
    if not secret or not code:
        return False

    cleaned = str(code).strip().translate(_CODE_NOISE)
    if not cleaned.isdigit() or len(cleaned) != 6:
        return False

    if window is None:
        window = TOTP_VALID_WINDOW

    return pyotp.TOTP(secret).verify(cleaned, valid_window=window)


def GetCurrentCode(secret):
    """取当前动态码。仅用于调试，正常登录流程用不到。"""
    return pyotp.TOTP(secret).now()


# ------------------------------------------------------------------ 恢复码


def GenerateRecoveryCodes():
    """生成一组一次性恢复码，形如 A1B2C-3D4E5。"""
    codes = []
    while len(codes) < RECOVERY_CODE_COUNT:
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_BYTES * 2))
        code = "{}-{}".format(raw[:RECOVERY_CODE_BYTES], raw[RECOVERY_CODE_BYTES:])
        if code not in codes:
            codes.append(code)
    return codes


def HashRecoveryCodes(codes):
    """恢复码落库前逐个做哈希，返回 JSON 字符串。"""
    return json.dumps([
        {"Hash": generate_password_hash(code), "Used": 0} for code in codes
    ])


def ConsumeRecoveryCode(recovery_codes_json, code):
    """校验并作废一个恢复码。

    返回 (是否命中, 新的 JSON 字符串)。命中时该码标记为已使用，
    调用方需要用返回值覆盖数据库里的原值。
    """
    if not recovery_codes_json or not code:
        return False, recovery_codes_json

    cleaned = str(code).strip().upper().translate(_CODE_NOISE)
    # 用户可能漏打中间的连字符，补回来
    if "-" not in cleaned and len(cleaned) == RECOVERY_CODE_BYTES * 2:
        cleaned = "{}-{}".format(cleaned[:RECOVERY_CODE_BYTES], cleaned[RECOVERY_CODE_BYTES:])

    try:
        records = json.loads(recovery_codes_json)
    except (TypeError, ValueError):
        return False, recovery_codes_json

    for record in records:
        if record.get("Used"):
            continue
        if check_password_hash(record.get("Hash", ""), cleaned):
            record["Used"] = 1
            return True, json.dumps(records)

    return False, recovery_codes_json


def CountUnusedRecoveryCodes(recovery_codes_json):
    """还剩几个没用过的恢复码。"""
    try:
        records = json.loads(recovery_codes_json or "[]")
    except (TypeError, ValueError):
        return 0
    return sum(1 for record in records if not record.get("Used"))