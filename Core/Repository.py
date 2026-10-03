"""数据访问层。

所有 SQL 都收敛在这里，API 层只调用函数、不写 SQL。
读取类函数统一返回可直接 JSON 序列化的 dict 列表。
"""

from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from Core import TotpService
from Core.Database import (
    Execute, ExecuteReturning, ExecuteRowCount, QueryAll, QueryOne,
)
from Core.Sanitizer import (
    SanitizeColor, SanitizeImageName, SanitizeUrl,
)

# ------------------------------------------------------------------ 工具函数


def FormatChineseDate(iso_date):
    """把 2026-09-07 转成 2026年9月7日；格式不符时原样返回。"""
    if not iso_date or len(iso_date) < 10:
        return iso_date or ""

    year, month, day = iso_date[:4], iso_date[5:7], iso_date[8:10]
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return iso_date

    return "{}年{}月{}日".format(year, int(month), int(day))


def _ToDict(row):
    """sqlite3.Row 转普通 dict。"""
    return dict(row) if row else None


def _ToDictList(rows):
    return [dict(row) for row in rows]


# ------------------------------------------------------------------ 站点配置


def GetSettings():
    """返回全部站点配置，形如 {'SiteTitle': '...'}。"""
    rows = QueryAll("SELECT SettingKey, SettingValue FROM SiteSetting")
    return {row["SettingKey"]: row["SettingValue"] for row in rows}


def GetSetting(key, default=""):
    row = QueryOne("SELECT SettingValue FROM SiteSetting WHERE SettingKey = ?", (key,))
    return row["SettingValue"] if row else default


def SaveSetting(key, value):
    # 背景图名会拼进 style 的 url()，必须按文件名规则校验
    text = str(value)
    if key == "BackgroundImageUrl":
        text = SanitizeImageName(text)

    Execute(
        "INSERT OR REPLACE INTO SiteSetting (SettingKey, SettingValue) VALUES (?, ?)",
        (key, text),
    )


def SaveSettings(mapping):
    for key, value in mapping.items():
        SaveSetting(key, value)


# ------------------------------------------------------------------ 日志面板


def GetLogPanels(only_visible=False):
    sql = "SELECT * FROM LogPanel"
    if only_visible:
        sql += " WHERE IsVisible = 1"
    sql += " ORDER BY SortOrder ASC, Id ASC"
    return _ToDictList(QueryAll(sql))


def GetLogPanel(panel_key):
    return _ToDict(
        QueryOne("SELECT * FROM LogPanel WHERE PanelKey = ?", (panel_key,))
    )


def SaveLogPanel(panel_key, title, subtitle, link_text, link_url, sort_order=0, is_visible=1):
    Execute(
        """UPDATE LogPanel
              SET Title = ?, Subtitle = ?, SubtitleLinkText = ?, SubtitleLinkUrl = ?,
                  SortOrder = ?, IsVisible = ?
            WHERE PanelKey = ?""",
        (title, subtitle, link_text, SanitizeUrl(link_url),
         int(sort_order), int(is_visible), panel_key),
    )


# ------------------------------------------------------------------ 面板提示行


def GetNotices(panel_key=None):
    if panel_key:
        rows = QueryAll(
            "SELECT * FROM PanelNotice WHERE PanelKey = ? ORDER BY SortOrder ASC, Id ASC",
            (panel_key,),
        )
    else:
        rows = QueryAll("SELECT * FROM PanelNotice ORDER BY PanelKey ASC, SortOrder ASC, Id ASC")
    return _ToDictList(rows)


def SaveNotice(notice_id, panel_key, prefix, content, link_url, sort_order=0):
    if notice_id:
        Execute(
            """UPDATE PanelNotice
                  SET PanelKey = ?, Prefix = ?, Content = ?, LinkUrl = ?, SortOrder = ?
                WHERE Id = ?""",
            (panel_key, prefix, content, SanitizeUrl(link_url), int(sort_order), int(notice_id)),
        )
        return int(notice_id)

    return Execute(
        """INSERT INTO PanelNotice (PanelKey, Prefix, Content, LinkUrl, SortOrder)
           VALUES (?, ?, ?, ?, ?)""",
        (panel_key, prefix, content, SanitizeUrl(link_url), int(sort_order)),
    )


def DeleteNotice(notice_id):
    Execute("DELETE FROM PanelNotice WHERE Id = ?", (int(notice_id),))


# ------------------------------------------------------------------ 更新日志


def GetUpdateLogs(panel_key=None, only_visible=False):
    sql = "SELECT * FROM UpdateLog WHERE 1 = 1"
    params = []
    if panel_key:
        sql += " AND PanelKey = ?"
        params.append(panel_key)
    if only_visible:
        sql += " AND IsVisible = 1"
    sql += " ORDER BY SortOrder ASC, LogDate DESC, Id ASC"

    records = _ToDictList(QueryAll(sql, tuple(params)))
    for record in records:
        record["DisplayDate"] = FormatChineseDate(record["LogDate"])
    return records


def GetUpdateLog(log_id):
    return _ToDict(QueryOne("SELECT * FROM UpdateLog WHERE Id = ?", (int(log_id),)))


def SaveUpdateLog(log_id, panel_key, log_date, title, content, link_url, sort_order=0, is_visible=1):
    if log_id:
        Execute(
            """UPDATE UpdateLog
                  SET PanelKey = ?, LogDate = ?, Title = ?, Content = ?, LinkUrl = ?,
                      SortOrder = ?, IsVisible = ?, UpdatedAt = datetime('now', 'localtime')
                WHERE Id = ?""",
            (
                panel_key, log_date, title, content, SanitizeUrl(link_url),
                int(sort_order), int(is_visible), int(log_id),
            ),
        )
        return int(log_id)

    return Execute(
        """INSERT INTO UpdateLog
               (PanelKey, LogDate, Title, Content, LinkUrl, SortOrder, IsVisible)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (panel_key, log_date, title, content, SanitizeUrl(link_url),
         int(sort_order), int(is_visible)),
    )


def DeleteUpdateLog(log_id):
    Execute("DELETE FROM UpdateLog WHERE Id = ?", (int(log_id),))


def GetNextLogSortOrder(panel_key):
    row = QueryOne(
        "SELECT COALESCE(MAX(SortOrder), 0) + 1 AS NextOrder FROM UpdateLog WHERE PanelKey = ?",
        (panel_key,),
    )
    return row["NextOrder"] if row else 1


# ------------------------------------------------------------------ 服务卡片


def GetServiceCards(only_visible=False):
    sql = "SELECT * FROM ServiceCard WHERE 1 = 1"
    params = []
    if only_visible:
        sql += " AND IsVisible = 1"
    sql += " ORDER BY SortOrder ASC, Id ASC"
    return _ToDictList(QueryAll(sql, tuple(params)))


def GetServiceCard(card_id):
    return _ToDict(QueryOne("SELECT * FROM ServiceCard WHERE Id = ?", (int(card_id),)))


def SaveServiceCard(card_id, title, subtitle, target_url, image_url, theme_color,
                    sort_order=0, is_visible=1):
    # GroupKey 固定为 MAIN：首页所有卡片排在同一网格，不再按分组区分版面
    if card_id:
        Execute(
            """UPDATE ServiceCard
                  SET GroupKey = 'MAIN', Title = ?, Subtitle = ?, TargetUrl = ?, ImageUrl = ?,
                      ThemeColor = ?, SortOrder = ?, IsVisible = ?
                WHERE Id = ?""",
            (
                title, subtitle, SanitizeUrl(target_url), SanitizeImageName(image_url),
                SanitizeColor(theme_color), int(sort_order), int(is_visible), int(card_id),
            ),
        )
        return int(card_id)

    return Execute(
        """INSERT INTO ServiceCard
               (GroupKey, Title, Subtitle, TargetUrl, ImageUrl, ThemeColor, SortOrder, IsVisible)
           VALUES ('MAIN', ?, ?, ?, ?, ?, ?, ?)""",
        (
            title, subtitle, SanitizeUrl(target_url), SanitizeImageName(image_url),
            SanitizeColor(theme_color), int(sort_order), int(is_visible),
        ),
    )


def DeleteServiceCard(card_id):
    Execute("DELETE FROM ServiceCard WHERE Id = ?", (int(card_id),))


# ------------------------------------------------------------------ 管理员账号


def GetAdmin(user_name):
    return _ToDict(QueryOne("SELECT * FROM AdminAccount WHERE UserName = ?", (user_name,)))


def AuthenticateAdmin(user_name, password):
    """返回与本次密码校验一致的账号和会话版本。"""
    account = GetAdmin(user_name)
    if not account:
        return None
    if not check_password_hash(account["PasswordHash"], password):
        return None
    return account


def VerifyAdmin(user_name, password):
    """校验账号密码，通过返回用户名，否则返回 None。"""
    account = AuthenticateAdmin(user_name, password)
    return account["UserName"] if account else None


def ChangeAdminPassword(user_name, new_password, session_version):
    """原子更新密码和初始化状态，同时撤销其他登录与两步验证挂起会话。"""
    result = ExecuteReturning(
        """UPDATE AdminAccount
              SET PasswordHash = ?, MustChangePassword = 0,
                  SessionVersion = SessionVersion + 1,
                  UpdatedAt = datetime('now', 'localtime')
            WHERE UserName = ? AND SessionVersion = ?
            RETURNING SessionVersion""",
        (generate_password_hash(new_password), user_name, session_version),
    )
    return result["SessionVersion"] if result else None


# ------------------------------------------------------------------ 两步验证


def GetTotpRecord(user_name):
    return _ToDict(
        QueryOne("SELECT * FROM AdminTotp WHERE UserName = ?", (user_name,))
    )


def SaveTotpSecret(user_name, secret):
    """写入待确认的密钥，此时 IsEnabled 仍为 0。"""
    Execute(
        """INSERT INTO AdminTotp (UserName, TotpSecret, IsEnabled, RecoveryCodes)
           VALUES (?, ?, 0, '')
           ON CONFLICT(UserName) DO UPDATE SET
               TotpSecret = excluded.TotpSecret,
               IsEnabled  = 0,
               UpdatedAt  = datetime('now', 'localtime')""",
        (user_name, secret),
    )


def EnableTotp(user_name, recovery_codes_json):
    Execute(
        """UPDATE AdminTotp
              SET IsEnabled = 1, RecoveryCodes = ?,
                  UpdatedAt = datetime('now', 'localtime')
            WHERE UserName = ?""",
        (recovery_codes_json, user_name),
    )


def UpdateTotpRecoveryCodes(user_name, recovery_codes_json):
    Execute(
        """UPDATE AdminTotp
              SET RecoveryCodes = ?, UpdatedAt = datetime('now', 'localtime')
            WHERE UserName = ?""",
        (recovery_codes_json, user_name),
    )


def ConsumeTotpRecoveryCode(user_name, code):
    """原子地校验并作废一个恢复码，返回是否由本次调用消费成功。

    早先是「读出来 → 判断 → 写回去」，两个并发请求会读到同一份旧 JSON、
    都判定命中、都写回，同一个一次性恢复码就被用了两次。
    这里改成带条件的更新：只有库里的值仍等于我读到的那份时才写入，
    受影响行数为 0 就说明别人抢先了，本次视为失败。
    """
    record = GetTotpRecord(user_name)
    if not record or not record["RecoveryCodes"]:
        return False

    matched, updated_json = TotpService.ConsumeRecoveryCode(record["RecoveryCodes"], code)
    if not matched:
        return False

    affected = ExecuteRowCount(
        "UPDATE AdminTotp SET RecoveryCodes = ?, UpdatedAt = datetime('now', 'localtime') "
        "WHERE UserName = ? AND RecoveryCodes = ?",
        (updated_json, user_name, record["RecoveryCodes"]),
    )
    return affected > 0


def DisableTotp(user_name):
    """关闭两步验证并抹掉密钥与恢复码。"""
    Execute("DELETE FROM AdminTotp WHERE UserName = ?", (user_name,))


# ------------------------------------------------------------------ 登录失败计数

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def BuildPasswordAttemptKey(user_name, client_ip):
    """密码阶段的计数键：按来源 IP + 用户名。

    这样攻击者故意输错密码只能锁住自己，锁不到站长。
    """
    return "PASSWORD|{}|{}".format(client_ip or "unknown", user_name)


def BuildTotpAttemptKey(user_name):
    """动态码阶段的计数键：按用户名。此时对方已持有密码，必须账号级封锁。"""
    return "TOTP|{}".format(user_name)


def GetLockRemainingSeconds(attempt_key):
    """还剩多少秒解锁，0 表示未被锁定。"""
    row = _ToDict(
        QueryOne("SELECT LockedUntil FROM LoginAttempt WHERE AttemptKey = ?", (attempt_key,))
    )
    if not row or not row["LockedUntil"]:
        return 0

    try:
        unlock_time = datetime.strptime(row["LockedUntil"], _TIME_FORMAT)
    except ValueError:
        return 0

    remaining = (unlock_time - datetime.now()).total_seconds()
    return max(0, int(remaining))


def RegisterFailedAttempt(attempt_key, user_name, max_failures, lock_minutes):
    """记一次失败，达到上限就锁定。返回剩余可尝试次数，触发锁定时返回 0。

    整件事用**一条** SQL 完成。早先的写法是先 SELECT 再 UPDATE（两条独立连接），
    并发请求会读到同一个初值再各自加一，增量全部丢失 —— 实测 30 并发只记到 1 次，
    等于限流形同虚设，6 位动态码可以被在线爆破。
    """
    now = datetime.now()
    locked_until = (now + timedelta(minutes=lock_minutes)).strftime(_TIME_FORMAT)
    now_text = now.strftime(_TIME_FORMAT)

    # RETURNING 拿的是自增之后的值；够到上限就写入锁定时间并把计数清零，
    # 等锁定期自然结束
    row = ExecuteReturning(
        """INSERT INTO LoginAttempt (AttemptKey, UserName, FailedCount, LockedUntil, LastFailedAt)
           VALUES (?, ?, 1, '', ?)
           ON CONFLICT(AttemptKey) DO UPDATE SET
               FailedCount = CASE
                   WHEN LoginAttempt.FailedCount + 1 >= ? THEN 0
                   ELSE LoginAttempt.FailedCount + 1
               END,
               LockedUntil = CASE
                   WHEN LoginAttempt.FailedCount + 1 >= ? THEN ?
                   ELSE LoginAttempt.LockedUntil
               END,
               LastFailedAt = excluded.LastFailedAt
           RETURNING FailedCount, LockedUntil""",
        (attempt_key, user_name, now_text, max_failures, max_failures, locked_until),
    )

    if row and row["LockedUntil"]:
        return 0

    return max(0, max_failures - (row["FailedCount"] if row else max_failures))


def ClearLoginAttempt(attempt_key):
    """登录成功后清空失败记录。"""
    Execute("DELETE FROM LoginAttempt WHERE AttemptKey = ?", (attempt_key,))


def ClearAllAttemptsForUser(user_name):
    """清掉某个用户名下所有来源的失败记录（登录完全成功后调用）。"""
    Execute("DELETE FROM LoginAttempt WHERE UserName = ?", (user_name,))


# ------------------------------------------------------------------ 页面聚合数据


def BuildSiteContent():
    """一次性组装首页所需的全部数据。"""
    panels = GetLogPanels(only_visible=True)

    panel_blocks = []
    for panel in panels:
        panel_blocks.append({
            "PanelKey": panel["PanelKey"],
            "Title": panel["Title"],
            "Subtitle": panel["Subtitle"],
            "SubtitleLinkText": panel["SubtitleLinkText"],
            "SubtitleLinkUrl": panel["SubtitleLinkUrl"],
            "Notices": GetNotices(panel["PanelKey"]),
            "Logs": GetUpdateLogs(panel["PanelKey"], only_visible=True),
        })

    return {
        "Settings": GetSettings(),
        "Panels": panel_blocks,
        # 所有卡片同等对待，排成同一个网格，顺序由 SortOrder 决定
        "Cards": GetServiceCards(only_visible=True),
    }
