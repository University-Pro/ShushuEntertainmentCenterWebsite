"""首次运行时的种子数据。

内容取自参考图 ReferencePhoto.png，可在后台管理页中随意增删改。
"""

from werkzeug.security import generate_password_hash

from AppConfig import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
from Core.Database import ExecuteMany

# ------------------------------------------------------------------ 站点配置
SITE_SETTINGS = [
    ("SiteTitle", "鼠鼠娱乐中心"),
    ("SiteTitleEmoji", "🐭"),
    ("SiteDescription", "校内资源、影视服务与常用工具入口"),
    ("SearchPlaceholder", "搜索任意内容..."),
    ("FooterText", "鼠鼠娱乐中心 · 校内自用服务"),
    # 每块日志面板默认显示多少条，其余折叠在「展开全部」里
    ("LogPreviewCount", "6"),
    # 背景图：把图片放进 Web/Static/Images/ 后在此填写文件名，留空则使用内置渐变
    ("BackgroundImageUrl", ""),
    # auto = 跟随系统，也可填 light / dark 固定
    ("DefaultTheme", "auto"),
]

# ------------------------------------------------------------------ 日志面板
LOG_PANELS = [
    {
        "PanelKey": "RESOURCE",
        "Title": "资源更新日志",
        "Subtitle": "",
        "SubtitleLinkText": "校内下载站",
        "SubtitleLinkUrl": "/Download/",
        "SortOrder": 1,
        "IsVisible": 1,
    },
    {
        "PanelKey": "SYSTEM",
        "Title": "系统更新日志",
        "Subtitle": "更多日志与手册请参考飞书文档：",
        "SubtitleLinkText": "服务器说明和使用日志",
        "SubtitleLinkUrl": "https://shushucenter.feishu.cn/wiki/KlZ0w5YtRipRr2kuvAicPIFSnMd",
        "SortOrder": 2,
        "IsVisible": 1,
    },
]

# ------------------------------------------------------------------ 面板提示行
PANEL_NOTICES = [
    {
        "PanelKey": "RESOURCE",
        "Prefix": "注意：",
        "Content": "下载整个文件夹会引发服务端自动打包，可能会导致二次解压操作，不建议下载整个文件夹而是分散下载文件。",
        "LinkUrl": "",
        "SortOrder": 1,
    },
    {
        "PanelKey": "RESOURCE",
        "Prefix": "可选：",
        "Content": "推荐使用多线程下载器下载，如IDM、迅雷等。在有线网络使用非运营商宽带的前提下可能达到校园内网理论速度50MB/s",
        "LinkUrl": "",
        "SortOrder": 2,
    },
    {
        "PanelKey": "RESOURCE",
        "Prefix": "QQ交流群：",
        "Content": "1097692798",
        "LinkUrl": "",
        "SortOrder": 3,
    },
]

# ------------------------------------------------------------------ 更新日志
RESOURCE_LOGS = [
    ("2026-09-07", "人狼村之谜"),
    ("2026-08-29", "剑星"),
    ("2026-08-27", "生化危机：安魂曲；007；刺客信条：黑旗重制版"),
    ("2026-05-30", "PRAGMATA"),
    ("2026-04-19", "调整一些文件"),
    ("2026-03-24", "死亡搁浅2"),
    ("2026-03-15", "调整一些文件"),
    ("2025-11-27", "真三国无双：起源"),
    ("2025-10-24", "宝可梦传奇 A-Z"),
    ("2025-10-22", "逃离鸭科夫"),
    ("2025-10-10", "小小梦魇3"),
    ("2025-09-29", "寂静岭F"),
    ("2025-09-26", "哈迪斯2"),
    ("2025-09-24", "消逝的光芒：困兽"),
    ("2025-09-20", "寻找伪人"),
    ("2025-09-05", "空洞骑士：丝之歌"),
    ("2025-07-26", "明末：渊虚之羽"),
    ("2025-07-22", "拔作岛1【游戏】；拔作岛2【游戏】"),
]

SYSTEM_LOGS = [
    ("2026-01-01", "新年快乐！鼠鼠娱乐中心祝各位学习顺利，工作顺心！", ""),
    ("2026-01-11", "计划未来一段时间服务器软件/硬件进行调整，可能会造成一定时间的断连", ""),
    ("2026-03-02", "我们更新了一些下载站中的资源；将一些使用文档移动至飞书文档方便浏览", ""),
    ("2026-03-03", "MC服务器已停服，如有需要以后再开", ""),
    ("2026-03-13", "校园网IPv6维护中，一些功能可能受到影响", ""),
    ("2026-03-15", "校园网IPv6出口恢复正常；购入了一批氦气盘以扩容存储", ""),
    (
        "2026-03-23",
        "进行一些服务迁移，可能会造成一些影响；修复了本地服务器日志链接错误的问题；将本地说明与日志同步至飞书文档，方便不同网络环境用户查看：",
        "https://shushucenter.feishu.cn/wiki/KlZ0w5YtRipRr2kuvAicPIFSnMd",
    ),
    ("2026-04-16", "修复服务器固态硬盘错误以及影视服务弹幕错误；合并鼠鼠日志", ""),
    ("2026-04-19", "尝试创建QQ交流群：1097692798", ""),
    ("2026-04-23", "减少大模型报错500的概率；上线通用代理网站", ""),
    ("2026-04-24", "更新DeepseekV4系列", ""),
    ("2026-07-10", "更新ChatGPT 5.6全系列", ""),
    ("2026-08-13", "服务器硬件出现故障，暂时无法提供服务", ""),
    ("2026-08-17", "服务器硬件暂时修复；上线Jellyfin，尝试替代Emby服务", ""),
]

# ------------------------------------------------------------------ 服务卡片
# 首页所有卡片同等大小、排成同一个网格，GroupKey 目前统一为 MAIN，
# 仅作为数据分类保留，不影响版面。换图标只需改 ImageUrl
SERVICE_CARDS = [
    {
        "GroupKey": "MAIN",
        "Title": "影视服务（Jellyfin）",
        "Subtitle": "影视库 · 弹幕 · 多端同步",
        "TargetUrl": "http://ubuntu-vm:8096",
        "ImageUrl": "IconMediaServer.svg",
        "ThemeColor": "#7B5CF0",
        "SortOrder": 1,
    },
    {
        "GroupKey": "MAIN",
        "Title": "鼠鼠LLM",
        "Subtitle": "大模型对话入口",
        "TargetUrl": "/Llm/",
        "ImageUrl": "IconLanguageModel.svg",
        "ThemeColor": "#10A37F",
        "SortOrder": 2,
    },
    {
        "GroupKey": "MAIN",
        "Title": "影视服务（Emby）",
        "Subtitle": "Emby",
        "TargetUrl": "http://ubuntu-vm:8096",
        "ImageUrl": "IconMediaPlay.svg",
        "ThemeColor": "#52B54B",
        "SortOrder": 3,
    },
    {
        "GroupKey": "MAIN",
        "Title": "下载站",
        "Subtitle": "校内资源下载",
        "TargetUrl": "/Download/",
        "ImageUrl": "IconDownload.svg",
        "ThemeColor": "#2F80ED",
        "SortOrder": 4,
    },
    {
        "GroupKey": "MAIN",
        "Title": "网络测速",
        "Subtitle": "内网 / 外网测速",
        "TargetUrl": "/SpeedTest/",
        "ImageUrl": "IconSpeedTest.svg",
        "ThemeColor": "#FF9F0A",
        "SortOrder": 5,
    },
    {
        "GroupKey": "MAIN",
        "Title": "通用代理",
        "Subtitle": "在线代理访问",
        "TargetUrl": "/Proxy/",
        "ImageUrl": "IconProxy.svg",
        "ThemeColor": "#00C48C",
        "SortOrder": 6,
    },
    {
        "GroupKey": "MAIN",
        "Title": "PDF编辑器",
        "Subtitle": "在线处理 PDF",
        "TargetUrl": "/Pdf/",
        "ImageUrl": "IconDocument.svg",
        "ThemeColor": "#D93A34",
        "SortOrder": 7,
    },
]


def SeedDatabase():
    """把上面的常量写进数据库。仅在空库时调用一次。"""
    if len(DEFAULT_ADMIN_PASSWORD) < 12:
        raise RuntimeError(
            "首次启动必须设置 SHUSHU_ADMIN_PASSWORD，至少 12 个字符。"
            "已有数据库的管理员密码请在后台修改。"
        )
    statements = []

    for key, value in SITE_SETTINGS:
        statements.append(
            ("INSERT OR REPLACE INTO SiteSetting (SettingKey, SettingValue) VALUES (?, ?)", (key, value))
        )

    statements.append(
        (
            "INSERT OR REPLACE INTO AdminAccount (UserName, PasswordHash) VALUES (?, ?)",
            (DEFAULT_ADMIN_USERNAME, generate_password_hash(DEFAULT_ADMIN_PASSWORD)),
        )
    )

    for panel in LOG_PANELS:
        statements.append(
            (
                """INSERT OR REPLACE INTO LogPanel
                   (PanelKey, Title, Subtitle, SubtitleLinkText, SubtitleLinkUrl, SortOrder, IsVisible)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    panel["PanelKey"], panel["Title"], panel["Subtitle"],
                    panel["SubtitleLinkText"], panel["SubtitleLinkUrl"],
                    panel["SortOrder"], panel["IsVisible"],
                ),
            )
        )

    for notice in PANEL_NOTICES:
        statements.append(
            (
                """INSERT INTO PanelNotice (PanelKey, Prefix, Content, LinkUrl, SortOrder)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    notice["PanelKey"], notice["Prefix"], notice["Content"],
                    notice["LinkUrl"], notice["SortOrder"],
                ),
            )
        )

    for index, (log_date, title) in enumerate(RESOURCE_LOGS, start=1):
        statements.append(
            (
                """INSERT INTO UpdateLog (PanelKey, LogDate, Title, Content, LinkUrl, SortOrder)
                   VALUES ('RESOURCE', ?, ?, '', '', ?)""",
                (log_date, title, index),
            )
        )

    for index, (log_date, content, link_url) in enumerate(SYSTEM_LOGS, start=1):
        statements.append(
            (
                """INSERT INTO UpdateLog (PanelKey, LogDate, Title, Content, LinkUrl, SortOrder)
                   VALUES ('SYSTEM', ?, '', ?, ?, ?)""",
                (log_date, content, link_url, index),
            )
        )

    for card in SERVICE_CARDS:
        statements.append(
            (
                """INSERT INTO ServiceCard
                   (GroupKey, Title, Subtitle, TargetUrl, ImageUrl, ThemeColor, SortOrder)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    card["GroupKey"], card["Title"], card["Subtitle"], card["TargetUrl"],
                    card["ImageUrl"], card["ThemeColor"], card["SortOrder"],
                ),
            )
        )

    ExecuteMany(statements)
