"""SQLite 连接管理与建表脚本。

对外只暴露四个函数：
    InitializeDatabase()  —— 建表 + 首次运行时写入种子数据
    QueryAll()            —— 查多行，返回 sqlite3.Row 列表
    QueryOne()            —— 查一行，无结果返回 None
    Execute()             —— 执行写操作，返回自增主键
"""

import sqlite3
from contextlib import contextmanager

from AppConfig import DATA_FOLDER, DATABASE_FILE

# ------------------------------------------------------------------ 表结构定义
SCHEMA_STATEMENTS = [
    # 站点级键值配置（标题、背景图、页脚等）
    """
    CREATE TABLE IF NOT EXISTS SiteSetting (
        SettingKey   TEXT PRIMARY KEY,
        SettingValue TEXT NOT NULL DEFAULT ''
    )
    """,
    # 后台管理员账号
    """
    CREATE TABLE IF NOT EXISTS AdminAccount (
        Id           INTEGER PRIMARY KEY AUTOINCREMENT,
        UserName     TEXT NOT NULL UNIQUE,
        PasswordHash TEXT NOT NULL,
        UpdatedAt    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
    # 两步验证（TOTP）绑定信息。与 AdminAccount 一对一，独立成表便于后续扩展多账号
    """
    CREATE TABLE IF NOT EXISTS AdminTotp (
        Id            INTEGER PRIMARY KEY AUTOINCREMENT,
        UserName      TEXT    NOT NULL UNIQUE,
        TotpSecret    TEXT    NOT NULL DEFAULT '',
        IsEnabled     INTEGER NOT NULL DEFAULT 0,
        RecoveryCodes TEXT    NOT NULL DEFAULT '',
        UpdatedAt     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
    # 登录失败计数。必须放服务端：Flask 默认是客户端 session，
    # 把计数塞在 cookie 里的话，攻击者丢掉 cookie 就能无限重试。
    #
    # 主键是 AttemptKey 而不是 UserName，因为两类失败的合理粒度不同：
    #   密码阶段（未认证）按「来源 IP + 用户名」计数 —— 否则任何人都能靠
    #     故意输错密码把站长锁在门外（拿 IP 做键，攻击者只能锁住自己）
    #   动态码阶段（已过密码）按「用户名」计数 —— 此时对方已持有密码，
    #     必须是账号级封锁
    """
    CREATE TABLE IF NOT EXISTS LoginAttempt (
        AttemptKey   TEXT    PRIMARY KEY,
        UserName     TEXT    NOT NULL DEFAULT '',
        FailedCount  INTEGER NOT NULL DEFAULT 0,
        LockedUntil  TEXT    NOT NULL DEFAULT '',
        LastFailedAt TEXT    NOT NULL DEFAULT ''
    )
    """,
    # 访问记录。只记页面访问，静态资源与健康检查在写入前就被过滤掉。
    # 按天的聚合查询都走 VisitDate，所以它单独建索引。
    """
    CREATE TABLE IF NOT EXISTS PageVisit (
        Id          INTEGER PRIMARY KEY AUTOINCREMENT,
        VisitedAt   TEXT    NOT NULL,
        VisitDate   TEXT    NOT NULL,
        VisitHour   INTEGER NOT NULL DEFAULT 0,
        Path        TEXT    NOT NULL DEFAULT '/',
        StatusCode  INTEGER NOT NULL DEFAULT 0,
        DurationMs  INTEGER NOT NULL DEFAULT 0,
        VisitorHash TEXT    NOT NULL DEFAULT '',
        ClientIp    TEXT    NOT NULL DEFAULT '',
        UserAgent   TEXT    NOT NULL DEFAULT '',
        Referer     TEXT    NOT NULL DEFAULT '',
        IsBot       INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS IdxPageVisitDate    ON PageVisit (VisitDate, IsBot)",
    "CREATE INDEX IF NOT EXISTS IdxPageVisitPath    ON PageVisit (Path, VisitDate)",
    "CREATE INDEX IF NOT EXISTS IdxPageVisitVisitor ON PageVisit (VisitorHash, VisitDate)",
    # 日志面板（左侧「资源更新日志」/ 中间「系统更新日志」）
    """
    CREATE TABLE IF NOT EXISTS LogPanel (
        Id               INTEGER PRIMARY KEY AUTOINCREMENT,
        PanelKey         TEXT    NOT NULL UNIQUE,
        Title            TEXT    NOT NULL DEFAULT '',
        Subtitle         TEXT    NOT NULL DEFAULT '',
        SubtitleLinkText TEXT    NOT NULL DEFAULT '',
        SubtitleLinkUrl  TEXT    NOT NULL DEFAULT '',
        SortOrder        INTEGER NOT NULL DEFAULT 0,
        IsVisible        INTEGER NOT NULL DEFAULT 1
    )
    """,
    # 日志面板顶部的提示行（如「注意：…」「可选：…」）
    """
    CREATE TABLE IF NOT EXISTS PanelNotice (
        Id        INTEGER PRIMARY KEY AUTOINCREMENT,
        PanelKey  TEXT    NOT NULL,
        Prefix    TEXT    NOT NULL DEFAULT '',
        Content   TEXT    NOT NULL DEFAULT '',
        LinkUrl   TEXT    NOT NULL DEFAULT '',
        SortOrder INTEGER NOT NULL DEFAULT 0
    )
    """,
    # 更新日志条目
    """
    CREATE TABLE IF NOT EXISTS UpdateLog (
        Id        INTEGER PRIMARY KEY AUTOINCREMENT,
        PanelKey  TEXT    NOT NULL,
        LogDate   TEXT    NOT NULL DEFAULT '',
        Title     TEXT    NOT NULL DEFAULT '',
        Content   TEXT    NOT NULL DEFAULT '',
        LinkUrl   TEXT    NOT NULL DEFAULT '',
        SortOrder INTEGER NOT NULL DEFAULT 0,
        IsVisible INTEGER NOT NULL DEFAULT 1,
        UpdatedAt TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
    )
    """,
    # 服务入口卡片（右侧栏 / 底部横排）
    """
    CREATE TABLE IF NOT EXISTS ServiceCard (
        Id         INTEGER PRIMARY KEY AUTOINCREMENT,
        GroupKey   TEXT    NOT NULL,
        Title      TEXT    NOT NULL DEFAULT '',
        Subtitle   TEXT    NOT NULL DEFAULT '',
        TargetUrl  TEXT    NOT NULL DEFAULT '',
        ImageUrl   TEXT    NOT NULL DEFAULT '',
        ThemeColor TEXT    NOT NULL DEFAULT '#3B82F6',
        SortOrder  INTEGER NOT NULL DEFAULT 0,
        IsVisible  INTEGER NOT NULL DEFAULT 1
    )
    """,
    # 常用查询索引
    "CREATE INDEX IF NOT EXISTS IdxUpdateLogPanel ON UpdateLog (PanelKey, SortOrder)",
    "CREATE INDEX IF NOT EXISTS IdxNoticePanel    ON PanelNotice (PanelKey, SortOrder)",
    "CREATE INDEX IF NOT EXISTS IdxServiceGroup   ON ServiceCard (GroupKey, SortOrder)",
]


def GetConnection():
    """建立一个开启了行工厂与外键约束的连接。"""
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DATABASE_FILE), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def UseConnection(commit=False):
    """连接上下文管理器，异常时自动回滚。"""
    connection = GetConnection()
    try:
        yield connection
        if commit:
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def QueryAll(sql, params=()):
    """查询多行。"""
    with UseConnection() as connection:
        return connection.execute(sql, params).fetchall()


def QueryOne(sql, params=()):
    """查询单行，无结果返回 None。"""
    with UseConnection() as connection:
        return connection.execute(sql, params).fetchone()


def Execute(sql, params=()):
    """执行写操作，返回新插入行的主键（非插入语句返回受影响行数）。"""
    with UseConnection(commit=True) as connection:
        cursor = connection.execute(sql, params)
        return cursor.lastrowid if cursor.lastrowid else cursor.rowcount


def ExecuteReturning(sql, params=()):
    """执行一条带 RETURNING 的写语句，提交后返回结果行。

    不能拿 QueryOne 跑 INSERT：它走的是不提交的连接，
    写完关连接时会被回滚掉。
    """
    with UseConnection(commit=True) as connection:
        return connection.execute(sql, params).fetchone()


def ExecuteRowCount(sql, params=()):
    """执行写操作并返回受影响行数。

    需要判断「这一行到底有没有被我改到」时必须用它：`Execute` 对 UPDATE
    会先看 lastrowid，语义不够明确，而且返回 0 和返回行数无法区分。
    """
    with UseConnection(commit=True) as connection:
        return connection.execute(sql, params).rowcount


def ExecuteMany(statements):
    """在一个事务中执行多条 (sql, params) 语句。"""
    with UseConnection(commit=True) as connection:
        for sql, params in statements:
            connection.execute(sql, params)


def _MigrateLoginAttempt(connection):
    """老版本的 LoginAttempt 以 UserName 为唯一键，换成 AttemptKey 主键。

    这张表只存易失的失败计数，直接重建即可，没有需要保留的数据。
    """
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(LoginAttempt)")
    }
    if columns and "AttemptKey" not in columns:
        connection.execute("DROP TABLE LoginAttempt")
        connection.execute(
            """CREATE TABLE LoginAttempt (
                   AttemptKey   TEXT    PRIMARY KEY,
                   UserName     TEXT    NOT NULL DEFAULT '',
                   FailedCount  INTEGER NOT NULL DEFAULT 0,
                   LockedUntil  TEXT    NOT NULL DEFAULT '',
                   LastFailedAt TEXT    NOT NULL DEFAULT ''
               )"""
        )


def InitializeDatabase():
    """建表；若数据库为空则写入种子数据与初始管理员。"""
    with UseConnection(commit=True) as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        _MigrateLoginAttempt(connection)

        already_seeded = connection.execute(
            "SELECT COUNT(*) AS Total FROM SiteSetting"
        ).fetchone()["Total"]

    if not already_seeded:
        # 延迟导入，避免模块循环依赖
        from Core.SeedData import SeedDatabase

        SeedDatabase()