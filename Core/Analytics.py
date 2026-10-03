"""访问统计。

访问统计是自成一体的功能，它的建表、写入和聚合 SQL 都收在这个模块里，
不混进 Repository（那里是站点内容的数据访问）。

两个设计取舍：

1. **访客识别用不可逆哈希，不用 IP。** VisitorHash = HMAC(密钥, IP + UA)。
   密钥来自 Data/SecretKey.txt，没有它无法反推。用固定密钥（而不是每日换盐）
   是为了让跨天的独立访客数也准确——每日换盐的话「近 30 天 UV」就只能靠
   每日 UV 相加，那是个偏高的数字。

2. **只记路径，不记查询串。** 查询串里可能有 token 之类的东西，
   存进数据库既没必要也不安全。
"""

import hashlib
import hmac
import re
from datetime import datetime, timedelta

from AppConfig import (
    ANALYTICS_IGNORED_PREFIXES, ANALYTICS_MAX_USER_AGENT_LENGTH,
    ANALYTICS_RETENTION_DAYS, ANALYTICS_STORE_RAW_IP, ANALYTICS_TOP_LIMIT,
    LoadOrCreateSecretKey,
)
from Core.Database import Execute, QueryAll, QueryOne

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_DATE_FORMAT = "%Y-%m-%d"

# 常见的爬虫与扫描器。命中标记为机器人，默认从统计里排除。
_BOT_PATTERN = re.compile(
    r"bot|crawler|spider|scrapy|curl|wget|python-requests|httpx|aiohttp|"
    r"go-http-client|java/|okhttp|headlesschrome|phantomjs|slurp|bingpreview|"
    r"facebookexternalhit|semrush|ahrefs|mj12|dotbot|petalbot|bytespider",
    re.IGNORECASE,
)

_SecretKeyCache = None


def _GetSecretKey():
    """密钥只在首次使用时读一次文件。"""
    global _SecretKeyCache
    if _SecretKeyCache is None:
        _SecretKeyCache = LoadOrCreateSecretKey().encode("utf-8")
    return _SecretKeyCache


# ------------------------------------------------------------------ 写入


def ShouldRecord(path, method):
    """判断这次请求要不要记。"""
    if method.upper() != "GET":
        return False
    for prefix in ANALYTICS_IGNORED_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def IsBot(user_agent):
    return bool(_BOT_PATTERN.search(user_agent or ""))


def ResolveClientIp(remote_addr):
    """仅使用实际连接来源，不解析任何代理转发头。"""
    return (remote_addr or "unknown")[:64]


def BuildVisitorHash(client_ip, user_agent):
    """不可逆的访客标识。同一天的同一设备稳定，但无法反推 IP。"""
    message = "{}|{}".format(client_ip or "", user_agent or "").encode("utf-8")
    digest = hmac.new(_GetSecretKey(), message, hashlib.sha256).hexdigest()
    return digest[:32]


def RecordVisit(path, status_code, duration_ms, client_ip, user_agent, referer):
    """写一条访问记录。调用方要保证异常不会影响正常请求。"""
    now = datetime.now()
    user_agent = (user_agent or "")[:ANALYTICS_MAX_USER_AGENT_LENGTH]
    referer = (referer or "")[:500]
    client_ip = (client_ip or "")[:64]

    Execute(
        """INSERT INTO PageVisit
               (VisitedAt, VisitDate, VisitHour, Path, StatusCode, DurationMs,
                VisitorHash, ClientIp, UserAgent, Referer, IsBot)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            now.strftime(_TIME_FORMAT),
            now.strftime(_DATE_FORMAT),
            now.hour,
            (path or "/")[:300],
            int(status_code or 0),
            int(duration_ms or 0),
            BuildVisitorHash(client_ip, user_agent),
            client_ip if ANALYTICS_STORE_RAW_IP else "",
            user_agent,
            referer,
            1 if IsBot(user_agent) else 0,
        ),
    )


# ------------------------------------------------------------------ 清理


def PurgeOldVisits(force=False):
    """清理超过保留期的记录。每天最多真正执行一次。"""
    today = datetime.now().strftime(_DATE_FORMAT)
    marker = QueryOne(
        "SELECT SettingValue FROM SiteSetting WHERE SettingKey = 'AnalyticsLastPurge'"
    )

    if not force and marker and marker["SettingValue"] == today:
        return 0

    cutoff = (datetime.now() - timedelta(days=ANALYTICS_RETENTION_DAYS)).strftime(_DATE_FORMAT)
    removed = Execute("DELETE FROM PageVisit WHERE VisitDate < ?", (cutoff,))

    Execute(
        "INSERT OR REPLACE INTO SiteSetting (SettingKey, SettingValue) "
        "VALUES ('AnalyticsLastPurge', ?)",
        (today,),
    )
    return removed


# ------------------------------------------------------------------ 查询辅助


def _RangeStart(days):
    """返回最近 days 天的起始日期（含今天）。"""
    return (datetime.now() - timedelta(days=max(1, days) - 1)).strftime(_DATE_FORMAT)


def _ExcludeBotsClause(include_bots):
    return "" if include_bots else " AND IsBot = 0"


def _FormatCount(value):
    """大数字缩写，用于卡片上的数值。"""
    number = int(value or 0)
    if number >= 1000000:
        return "{:.1f}M".format(number / 1000000.0)
    if number >= 10000:
        return "{:.1f}K".format(number / 10000.0)
    return "{:,}".format(number)


# ------------------------------------------------------------------ 概览


def GetOverview(days=7, include_bots=False):
    """顶部 KPI：今日、昨日、区间合计、平均响应。"""
    today = datetime.now().strftime(_DATE_FORMAT)
    yesterday = (datetime.now() - timedelta(days=1)).strftime(_DATE_FORMAT)
    range_start = _RangeStart(days)
    bots = _ExcludeBotsClause(include_bots)

    def _DayStats(day):
        row = QueryOne(
            """SELECT COUNT(*) AS PageViews,
                      COUNT(DISTINCT VisitorHash) AS Visitors
                 FROM PageVisit
                WHERE VisitDate = ?""" + bots,
            (day,),
        )
        return {
            "PageViews": row["PageViews"] or 0,
            "Visitors": row["Visitors"] or 0,
        }

    today_stats = _DayStats(today)
    yesterday_stats = _DayStats(yesterday)

    range_row = QueryOne(
        """SELECT COUNT(*) AS PageViews,
                  COUNT(DISTINCT VisitorHash) AS Visitors,
                  COALESCE(AVG(DurationMs), 0) AS AvgDuration
             FROM PageVisit
            WHERE VisitDate >= ?""" + bots,
        (range_start,),
    )

    bot_row = QueryOne(
        "SELECT COUNT(*) AS Total FROM PageVisit WHERE VisitDate >= ?",
        (range_start,),
    )

    total_row = QueryOne("SELECT COUNT(*) AS Total FROM PageVisit")

    return {
        "TodayPageViews": today_stats["PageViews"],
        "TodayVisitors": today_stats["Visitors"],
        "YesterdayPageViews": yesterday_stats["PageViews"],
        "YesterdayVisitors": yesterday_stats["Visitors"],
        "DeltaPageViews": today_stats["PageViews"] - yesterday_stats["PageViews"],
        "DeltaVisitors": today_stats["Visitors"] - yesterday_stats["Visitors"],
        "RangePageViews": range_row["PageViews"] or 0,
        "RangeVisitors": range_row["Visitors"] or 0,
        "AverageDurationMs": int(range_row["AvgDuration"] or 0),
        "RangeBotVisits": (bot_row["Total"] or 0) if include_bots else 0,
        "TotalRecords": total_row["Total"] or 0,
        "RangeDays": days,
    }


# ------------------------------------------------------------------ 趋势


def GetDailyTrend(days=14, include_bots=False):
    """按天的浏览量 / 独立访客，缺失的日期补 0。"""
    range_start = _RangeStart(days)
    bots = _ExcludeBotsClause(include_bots)

    rows = QueryAll(
        """SELECT VisitDate,
                  COUNT(*) AS PageViews,
                  COUNT(DISTINCT VisitorHash) AS Visitors
             FROM PageVisit
            WHERE VisitDate >= ?""" + bots + """
            GROUP BY VisitDate
            ORDER BY VisitDate ASC""",
        (range_start,),
    )

    found = {row["VisitDate"]: row for row in rows}
    series = []

    for offset in range(days):
        day = (datetime.now() - timedelta(days=days - 1 - offset)).strftime(_DATE_FORMAT)
        row = found.get(day)
        series.append({
            "Date": day,
            "ShortDate": day[5:],          # MM-DD
            "PageViews": (row["PageViews"] if row else 0) or 0,
            "Visitors": (row["Visitors"] if row else 0) or 0,
        })

    return series


def GetHourlyDistribution(days=7, include_bots=False):
    """24 小时时段分布。"""
    range_start = _RangeStart(days)
    bots = _ExcludeBotsClause(include_bots)

    rows = QueryAll(
        """SELECT VisitHour, COUNT(*) AS Hits
             FROM PageVisit
            WHERE VisitDate >= ?""" + bots + """
            GROUP BY VisitHour""",
        (range_start,),
    )

    found = {row["VisitHour"]: row["Hits"] for row in rows}
    return [
        {"Hour": hour, "Label": "{:02d}".format(hour), "Hits": found.get(hour, 0)}
        for hour in range(24)
    ]


# ------------------------------------------------------------------ 排行


def GetTopPaths(days=7, limit=None, include_bots=False):
    """热门页面。"""
    limit = limit or ANALYTICS_TOP_LIMIT
    range_start = _RangeStart(days)
    bots = _ExcludeBotsClause(include_bots)

    rows = QueryAll(
        """SELECT Path,
                  COUNT(*) AS Hits,
                  COUNT(DISTINCT VisitorHash) AS Visitors,
                  COALESCE(AVG(DurationMs), 0) AS AvgDuration
             FROM PageVisit
            WHERE VisitDate >= ?""" + bots + """
            GROUP BY Path
            ORDER BY Hits DESC
            LIMIT ?""",
        (range_start, limit),
    )

    return [
        {
            "Path": row["Path"],
            "Hits": row["Hits"] or 0,
            "Visitors": row["Visitors"] or 0,
            "AverageDurationMs": int(row["AvgDuration"] or 0),
        }
        for row in rows
    ]


def GetTopReferers(days=7, limit=None, include_bots=False):
    """来源站点。空 referer 归为「直接访问」。

    按主机名合并，而不是按完整 URL：同一个站点的不同页面在展示时都截成
    「example.com」，若按完整 URL 分组就会出现好几行一样的名字。
    所以在 Python 里合并后再排序取前几名。
    """
    limit = limit or ANALYTICS_TOP_LIMIT
    range_start = _RangeStart(days)
    bots = _ExcludeBotsClause(include_bots)

    rows = QueryAll(
        """SELECT Referer, COUNT(*) AS Hits
             FROM PageVisit
            WHERE VisitDate >= ?""" + bots + """
            GROUP BY Referer""",
        (range_start,),
    )

    merged = {}
    for row in rows:
        display = _ShortReferer(row["Referer"])
        entry = merged.setdefault(display, {"Display": display, "Hits": 0, "Raw": row["Referer"]})
        entry["Hits"] += row["Hits"] or 0

    ordered = sorted(merged.values(), key=lambda item: item["Hits"], reverse=True)
    return ordered[:limit]


def _ShortReferer(referer):
    """只留主机名，长 URL 在表格里读不出信息。"""
    if not referer:
        return "直接访问"

    text = referer
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    host = text.split("/")[0]
    return host or referer


# ------------------------------------------------------------------ 明细


def GetVisits(days=7, path_filter="", only_bots=False, limit=50, offset=0):
    """访问明细，按时间倒序。"""
    range_start = _RangeStart(days)
    conditions = ["VisitDate >= ?"]
    params = [range_start]

    if path_filter:
        conditions.append("Path LIKE ?")
        params.append("%{}%".format(path_filter))

    if only_bots:
        conditions.append("IsBot = 1")

    where = " AND ".join(conditions)

    total = QueryOne(
        "SELECT COUNT(*) AS Total FROM PageVisit WHERE " + where, tuple(params)
    )["Total"]

    params_with_page = list(params) + [int(limit), int(offset)]
    rows = QueryAll(
        """SELECT Id, VisitedAt, Path, StatusCode, DurationMs,
                  ClientIp, UserAgent, Referer, IsBot
             FROM PageVisit
            WHERE """ + where + """
            ORDER BY Id DESC
            LIMIT ? OFFSET ?""",
        tuple(params_with_page),
    )

    return {
        "Total": total or 0,
        "Records": [
            {
                "Id": row["Id"],
                "VisitedAt": row["VisitedAt"],
                "Path": row["Path"],
                "StatusCode": row["StatusCode"],
                "DurationMs": row["DurationMs"],
                "ClientIp": row["ClientIp"] or "已隐藏",
                "UserAgent": _ShortUserAgent(row["UserAgent"]),
                "Referer": _ShortReferer(row["Referer"]),
                "IsBot": bool(row["IsBot"]),
            }
            for row in rows
        ],
    }


def _ShortUserAgent(user_agent):
    """把 UA 压成「浏览器 · 系统」，原始串太长且没信息量。"""
    text = user_agent or ""
    if not text:
        return "未知"

    browser = "未知浏览器"
    for keyword, name in (
        ("Edg/", "Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"),
        ("Safari/", "Safari"), ("Firefox/", "Firefox"), ("MSIE", "IE"),
    ):
        if keyword in text:
            browser = name
            break

    system = "未知系统"
    for keyword, name in (
        ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
        ("Mac OS X", "macOS"), ("Windows", "Windows"), ("Linux", "Linux"),
    ):
        if keyword in text:
            system = name
            break

    return "{} · {}".format(browser, system)


def GetAvailableDays():
    """记录一共覆盖了多少天，用于页面上的范围选择。"""
    row = QueryOne(
        """SELECT MIN(VisitDate) AS FirstDay, MAX(VisitDate) AS LastDay,
                  COUNT(*) AS Total FROM PageVisit"""
    )
    return {
        "FirstDay": (row["FirstDay"] if row else "") or "",
        "LastDay": (row["LastDay"] if row else "") or "",
        "Total": (row["Total"] if row else 0) or 0,
    }
