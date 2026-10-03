"""后台访问统计子页面。

/Admin/Analytics          总览：KPI、按天趋势、时段分布、热门页面、来源
/Admin/Analytics/Records  明细：分页 + 路径筛选

时间范围与「是否含机器人」是**全局筛选**，放在页面顶部一行，
所有图表按同一个切片重算（每张图各带一套筛选是反模式）。
"""

from flask import Blueprint, render_template, request, session

from Api.AdminApi import LoginRequired
from Core import Analytics, ChartBuilder, Repository

AnalyticsBlueprint = Blueprint("AnalyticsApi", __name__, url_prefix="/Admin/Analytics")

# 允许的时间范围，以及各图表用多长的窗口
RANGE_OPTIONS = [
    {"Days": 7, "Label": "近 7 天"},
    {"Days": 14, "Label": "近 14 天"},
    {"Days": 30, "Label": "近 30 天"},
    {"Days": 90, "Label": "近 90 天"},
]

RECORDS_PER_PAGE = 50

# 趋势图最多画 30 个点，再多折线就糊了；选了 90 天时按周聚合
TREND_VIEW_MAX_DAYS = 30


def _ReadDays():
    """读取时间范围，非法值一律退回 7 天。"""
    try:
        days = int(request.args.get("days", 7))
    except (TypeError, ValueError):
        days = 7

    allowed = [option["Days"] for option in RANGE_OPTIONS]
    return days if days in allowed else 7


def _ReadIncludeBots():
    return request.args.get("bots") == "1"


def _BuildFilterState(days, include_bots):
    """给模板用的筛选器状态，避免模板里出现比较逻辑。"""
    return {
        "Days": days,
        "IncludeBots": include_bots,
        "Ranges": [
            {
                "Days": option["Days"],
                "Label": option["Label"],
                "IsActive": option["Days"] == days,
            }
            for option in RANGE_OPTIONS
        ],
    }


def _BaseContext(active_page):
    """子页面模板都要的那几个变量。"""
    return {
        "ActiveAdminPage": active_page,
        "AdminUser": session.get("AdminUser"),
        "DefaultTheme": Repository.GetSetting("DefaultTheme", "auto"),
    }


@AnalyticsBlueprint.route("/", methods=["GET"])
@LoginRequired
def AnalyticsPage():
    days = _ReadDays()
    include_bots = _ReadIncludeBots()

    overview = Analytics.GetOverview(days, include_bots)
    trend = Analytics.GetDailyTrend(min(days, TREND_VIEW_MAX_DAYS), include_bots)
    hourly = Analytics.GetHourlyDistribution(days, include_bots)
    top_paths = Analytics.GetTopPaths(days, include_bots=include_bots)
    top_referers = Analytics.GetTopReferers(days, include_bots=include_bots)

    # 折线图两条序列，共用一条 Y 轴（都是「次数」，量纲一致）
    line_chart = ChartBuilder.BuildLineChart(
        [
            {
                "Key": "PageViews",
                "Name": "浏览量",
                "ColorVar": "--ChartSeriesOne",
                "Values": [item["PageViews"] for item in trend],
            },
            {
                "Key": "Visitors",
                "Name": "独立访客",
                "ColorVar": "--ChartSeriesTwo",
                "Values": [item["Visitors"] for item in trend],
            },
        ],
        [item["ShortDate"] for item in trend],
    )

    context = _BaseContext("Analytics")
    context.update(
        Filter=_BuildFilterState(days, include_bots),
        Overview=overview,
        Trend=trend,
        LineChart=line_chart,
        Hourly=ChartBuilder.BuildColumnChart(hourly),
        TopPaths=ChartBuilder.BuildRankingBars(top_paths),
        TopPathsRaw=top_paths,
        TopReferers=top_referers,
        Coverage=Analytics.GetAvailableDays(),
        Days=days,
        IncludeBots=include_bots,
        FormatDuration=ChartBuilder.FormatDuration,
        FormatSignedDelta=ChartBuilder.FormatSignedDelta,
    )
    return render_template("AdminAnalyticsPage.html", **context)


@AnalyticsBlueprint.route("/Records", methods=["GET"])
@LoginRequired
def RecordsPage():
    days = _ReadDays()
    include_bots = _ReadIncludeBots()
    path_filter = (request.args.get("q") or "").strip()[:100]

    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    result = Analytics.GetVisits(
        days=days,
        path_filter=path_filter,
        only_bots=include_bots,
        limit=RECORDS_PER_PAGE,
        offset=(page - 1) * RECORDS_PER_PAGE,
    )

    total_pages = max(1, (result["Total"] + RECORDS_PER_PAGE - 1) // RECORDS_PER_PAGE)

    context = _BaseContext("AnalyticsRecords")
    context.update(
        Filter=_BuildFilterState(days, include_bots),
        Records=result["Records"],
        Total=result["Total"],
        Page=page,
        TotalPages=total_pages,
        PathFilter=path_filter,
        HasPrevious=page > 1,
        HasNext=page < total_pages,
        PreviousPage=page - 1,
        NextPage=page + 1,
        Days=days,
        IncludeBots=include_bots,
        FormatDuration=ChartBuilder.FormatDuration,
    )
    return render_template("AdminAnalyticsRecordsPage.html", **context)