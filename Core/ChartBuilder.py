"""把统计数据转成画图所需的几何。

模板里不该出现除法和取整，所以坐标、刻度、标签位置都在这里算好，
模板只负责把算好的数字填进 SVG / style 属性。

标记规格（粗细、圆角、留白）遵循数据可视化规范：
柱条不超过 24px、数据端 4px 圆角、基线端方角、折线 2px、
网格线是一像素实线（不用虚线）、相邻柱之间留 2px 表面色缝隙。
"""

from math import ceil, log10

# 趋势图的坐标系。用 viewBox 等比缩放，配 vector-effect 保证描边不随缩放变粗。
TREND_VIEW_WIDTH = 720
TREND_VIEW_HEIGHT = 240

# 绘图区留白：左侧给 Y 轴刻度，右侧给端点标签，下方给日期
_PADDING_LEFT = 40
_PADDING_RIGHT = 52
_PADDING_TOP = 16
_PADDING_BOTTOM = 28

# Y 轴刻度线数量（含 0 那条基线）
_Y_TICK_COUNT = 4


def _NiceCeiling(value):
    """把最大值收成 1 / 2 / 5 × 10ⁿ 这样的整数上界，刻度才不会出现 3271 这种数。"""
    if value <= 0:
        return 1

    exponent = log10(value)
    magnitude = 10 ** int(exponent // 1)
    normalized = value / magnitude

    for step in (1, 2, 5, 10):
        if normalized <= step:
            return int(step * magnitude)

    return int(10 * magnitude)


def _FormatTick(value):
    if value >= 10000:
        return "{:.0f}K".format(value / 1000.0)
    return "{:,}".format(int(value))


def BuildLineChart(Series, XLabels, ViewWidth=TREND_VIEW_WIDTH, ViewHeight=TREND_VIEW_HEIGHT):
    """折线图几何。

    Series: [{"Key","Name","ColorVar","Values":[int,...]}, ...]
    XLabels: ["09-07", ...]，长度与 Values 一致
    """
    point_count = max(len(XLabels), 1)

    # 所有序列共用一条 Y 轴。两个 Y 轴会让读者以为存在某种相关性，那是错的。
    max_value = 0
    for item in Series:
        for value in item["Values"]:
            max_value = max(max_value, value)
    axis_max = _NiceCeiling(max_value)

    plot_left = _PADDING_LEFT
    plot_right = ViewWidth - _PADDING_RIGHT
    plot_top = _PADDING_TOP
    plot_bottom = ViewHeight - _PADDING_BOTTOM
    plot_width = max(plot_right - plot_left, 1)
    plot_height = max(plot_bottom - plot_top, 1)

    def _X(index):
        if point_count == 1:
            return plot_left + plot_width / 2.0
        return plot_left + plot_width * index / float(point_count - 1)

    def _Y(value):
        return plot_bottom - plot_height * (value / float(axis_max))

    # Y 轴刻度 + 网格线
    y_ticks = []
    for index in range(_Y_TICK_COUNT + 1):
        value = axis_max * index / float(_Y_TICK_COUNT)
        y_ticks.append({
            "Y": round(_Y(value), 2),
            "Value": int(value),
            "Label": _FormatTick(value),
        })

    # X 轴标签：点太多时隔一个画一个，避免挤成一团
    label_step = 1
    if point_count > 16:
        label_step = 2
    if point_count > 28:
        label_step = 4

    last_index = point_count - 1
    x_labels = []
    for index, text in enumerate(XLabels):
        show = (index % label_step == 0) or index == last_index
        # 首尾标签向内收，否则会被绘图区边缘裁掉
        anchor = "middle"
        if index == 0:
            anchor = "start"
        elif index == last_index:
            anchor = "end"
        x_labels.append({
            "X": round(_X(index), 2),
            "Label": text,
            "Show": show,
            "Anchor": anchor,
        })

    # 折线几何
    built_series = []
    for item in Series:
        coordinates = []
        for index, value in enumerate(item["Values"]):
            coordinates.append("{},{}".format(round(_X(index), 2), round(_Y(value), 2)))

        built_series.append({
            "Key": item["Key"],
            "Name": item["Name"],
            "ColorVar": item["ColorVar"],
            # polyline/path 用的坐标串
            "Points": " ".join(coordinates),
            "EndX": round(_X(last_index), 2),
            "EndY": round(_Y(item["Values"][-1] if item["Values"] else 0), 2),
            "EndValue": item["Values"][-1] if item["Values"] else 0,
            "Total": sum(item["Values"]),
        })

    # 端点标签。两条线的端点挨太近时不做上下挪动（挪开就和线脱钩，看着更乱），
    # 直接让后者退回图例 + 悬停提示来承载。
    for position, item in enumerate(built_series):
        item["ShowEndLabel"] = True
        for previous in built_series[:position]:
            if abs(previous["EndY"] - item["EndY"]) < 16:
                item["ShowEndLabel"] = False
                break

    # 悬停热区：每个 x 一列，宽度取整列宽。热区要比线本身宽，
    # 否则要精确压在 2px 的线上才触发。
    band_width = plot_width / float(max(point_count - 1, 1)) if point_count > 1 else plot_width
    hit_bands = []
    for index in range(point_count):
        center = _X(index)
        left = max(plot_left, center - band_width / 2.0)
        right = min(plot_right, center + band_width / 2.0)

        readings = []
        for item in Series:
            readings.append("{} {}".format(item["Name"], item["Values"][index]))

        hit_bands.append({
            "X": round(left, 2),
            "Width": round(max(right - left, 1), 2),
            "Index": index,
            "CenterX": round(center, 2),
            "Title": "{} · {}".format(XLabels[index], " · ".join(readings)),
        })

    return {
        "ViewWidth": ViewWidth,
        "ViewHeight": ViewHeight,
        "PlotLeft": plot_left,
        "PlotRight": plot_right,
        "PlotTop": plot_top,
        "PlotBottom": plot_bottom,
        "AxisMax": axis_max,
        "HasData": max_value > 0,
        "YTicks": y_ticks,
        "XLabels": x_labels,
        "Series": built_series,
        "HitBands": hit_bands,
    }


def BuildColumnChart(Buckets, ValueKey="Hits"):
    """柱状图。返回每根柱子占绘图区高度的百分比，模板用 CSS 高度画。

    用 CSS 而不是 SVG，是为了能真正把柱宽限制在 24px——SVG 里按 viewBox
    算出来的宽度会随容器缩放，管不住。
    """
    max_value = max([item[ValueKey] for item in Buckets] or [0])
    axis_max = _NiceCeiling(max_value)

    columns = []
    for item in Buckets:
        value = item[ValueKey]
        percent = (value / float(axis_max) * 100.0) if axis_max else 0.0
        columns.append({
            "Label": item["Label"],
            "Value": value,
            # 值很小时也留一丝可见高度，否则「有 1 次访问」和「0 次」看起来一样
            "Percent": round(percent, 2) if value > 0 else 0.0,
            "Hour": item.get("Hour", 0),
        })

    y_ticks = []
    for index in range(_Y_TICK_COUNT + 1):
        value = axis_max * index / float(_Y_TICK_COUNT)
        y_ticks.append({
            "Label": _FormatTick(value),
            "Percent": round(100.0 * index / float(_Y_TICK_COUNT), 2),
        })

    return {
        "Columns": columns,
        "YTicks": list(reversed(y_ticks)),
        "AxisMax": axis_max,
        "HasData": max_value > 0,
    }


def BuildRankingBars(Items, ValueKey="Hits", LabelKey="Path"):
    """横向排行条。返回百分比宽度，模板用 CSS 画。

    所有条**同色**。按数值深浅上色会把条长这个信息重复编码一遍，
    白白烧掉唯一的自由通道。
    """
    max_value = max([item[ValueKey] for item in Items] or [0])

    bars = []
    for item in Items:
        value = item[ValueKey]
        percent = (value / float(max_value) * 100.0) if max_value else 0.0
        bars.append({
            "Label": item[LabelKey],
            "Value": value,
            # 最短的条也保证看得见
            "Percent": round(max(percent, 2.0), 2) if value > 0 else 0.0,
        })

    return {
        "Bars": bars,
        "MaxValue": max_value,
        "HasData": max_value > 0,
    }


def BuildSparkline(Values, Width=96, Height=28):
    """统计卡上的迷你趋势线。用去强调灰，末点用强调色。"""
    if not Values:
        return {"Points": "", "HasData": False, "EndX": 0, "EndY": 0}

    peak = max(max(Values), 1)
    count = len(Values)
    step = Width / float(max(count - 1, 1))

    coordinates = []
    for index, value in enumerate(Values):
        x = step * index
        y = Height - (Height * (value / float(peak)))
        coordinates.append("{},{}".format(round(x, 2), round(y, 2)))

    return {
        "Points": " ".join(coordinates),
        "HasData": peak > 0,
        "EndX": round(step * (count - 1), 2),
        "EndY": round(Height - Height * (Values[-1] / float(peak)), 2),
        "Width": Width,
        "Height": Height,
    }


def FormatDuration(milliseconds):
    """毫秒转成人能读的形式。"""
    value = int(milliseconds or 0)
    if value >= 1000:
        return "{:.2f}s".format(value / 1000.0)
    return "{}ms".format(value)


def FormatSignedDelta(value):
    """带符号的变化量，用于统计卡的同比。"""
    number = int(value or 0)
    if number > 0:
        return "+{:,}".format(number)
    return "{:,}".format(number)


def CeilPercent(value, axis_max):
    """把一个数值换算成 0-100 的百分比（供模板直接当 CSS 用）。"""
    if not axis_max:
        return 0.0
    return round(min(100.0, value / float(axis_max) * 100.0), 2)


def SafeAverage(total, count):
    """避免除零。"""
    if not count:
        return 0
    return int(ceil(float(total) / count))