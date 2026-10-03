<div align="center">

# 🐭 鼠鼠娱乐中心

**把服务入口、资源动态与站点管理，收进一个轻量门户。**

基于 Flask 与 SQLite 构建，支持响应式布局、深浅主题、后台管理与访问统计。

[快速部署](#快速部署) · [功能亮点](#功能亮点) · [自定义站点](#自定义站点) · [本地运行](#本地运行)

</div>

---

## 项目简介

鼠鼠娱乐中心是一个面向校园与个人自建服务的导航门户。首页集中展示服务卡片、资源更新和系统公告，管理员可通过后台维护内容，无需逐次编辑页面代码。

界面采用毛玻璃面板、柔和阴影与轻量视差交互，在桌面和移动设备上提供一致的浏览体验。适合校园服务导航、家庭服务器首页和个人资源入口。

## 功能亮点

| 功能 | 说明 |
| --- | --- |
| 服务导航 | 统一卡片网格，支持自定义链接、图标、颜色、排序与显示状态 |
| 更新公告 | 资源与系统日志分区展示，支持提示信息和日志折叠 |
| 主题与外观 | 浅色、深色及跟随系统模式，可配置站点背景 |
| 后台管理 | 在线维护站点设置、服务卡片、日志和提示信息 |
| 账号保护 | 密码登录、失败锁定、TOTP 两步验证及一次性恢复码 |
| 访问统计 | 浏览量、独立访客、每日趋势、时段分布、热门页面及访问明细 |
| 轻量部署 | SQLite 存储，Docker Compose 启动，Gunicorn 提供服务 |

首页支持自适应卡片布局；触屏设备和开启“减少动态效果”的设备会跳过倾斜与视差效果。

## 快速部署

推荐使用 Docker Compose。以下终端示例使用 **Bash**，首次启动需要设置至少 12 个字符的管理员密码。

```bash
git clone https://github.com/University-Pro/ShushuEntertainmentCenterWebsite.git
cd ShushuEntertainmentCenterWebsite

# 安全输入初始密码，输入内容不会回显
read -r -s -p "初始管理员密码：" SHUSHU_ADMIN_PASSWORD
echo
export SHUSHU_ADMIN_PASSWORD

# 构建并启动
docker compose -f DockerCompose.yml up -d --build
```

| 入口 | 地址 |
| --- | --- |
| 门户首页 | http://localhost:12339/ |
| 管理后台 | http://localhost:12339/Admin/Login |
| 健康检查 | http://localhost:12339/Health |

初始管理员用户名为 `admin`，密码使用上面设置的值。首次启动会创建数据库与示例内容；已有数据库的账号不会被环境变量重置。初始化后可移除密码环境变量，后续在后台修改密码。

### 日常维护

```bash
# 查看日志
docker compose -f DockerCompose.yml logs -f

# 更新代码后重新构建
docker compose -f DockerCompose.yml up -d --build

# 停止服务，保留数据卷
docker compose -f DockerCompose.yml down
```

数据库和会话密钥保存在命名卷 `shushu-mainpage-data` 中，重建容器会保留数据。备份或迁移时需保留整个数据卷；执行 `down -v` 会删除数据卷。

## 自定义站点

登录后台后，即可调整站点内容和外观。

- **站点设置**：修改标题、描述、页脚、默认主题及日志预览条数。
- **服务卡片**：配置名称、说明、目标链接、图标、主题色与排序。
- **日志与提示**：发布资源更新、系统动态和面板通知。
- **背景与图标**：将图片放入 `Web/Static/Images/`，在后台填写对应文件名；背景留空时使用内置渐变。
- **账号安全**：修改密码、绑定验证器并管理恢复码。

初始内容包含示例服务地址，请在使用前替换为自己的服务链接。

### 开启两步验证

进入后台“账号安全 → 两步验证”，输入当前密码后，用兼容 TOTP 的验证器扫描二维码，再输入动态码完成绑定。请妥善保存生成的恢复码；每个恢复码只能使用一次。

## 配置

### 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `SHUSHU_ADMIN_PASSWORD` | 空 | 首次建库必填，至少 12 个字符 |
| `SHUSHU_SECRET_KEY` | 自动生成并持久化 | 覆盖会话签名密钥 |
| `SESSION_COOKIE_SECURE` | `false` | HTTPS 部署时设为 `true` |
| `SERVER_PORT` | `12339` | 容器入口的监听端口 |
| `GUNICORN_WORKERS` | `2` | Gunicorn 工作进程数 |
| `GUNICORN_THREADS` | `4` | 每个工作进程的线程数 |
| `GUNICORN_TIMEOUT` | `60` | Gunicorn 请求超时秒数 |
| `GUNICORN_LOG_LEVEL` | `info` | Gunicorn 日志级别 |

容器环境变量在 `DockerCompose.yml` 的 `environment` 中配置；`SHUSHU_ADMIN_PASSWORD` 已支持从当前终端读取。本地运行的地址、端口和访问统计选项在 `AppConfig.py` 中配置。

修改容器监听端口时，需同步调整 Compose 端口映射与健康检查地址。

### 数据与部署

- `Data/` 存放数据库和会话密钥，包含敏感信息，请勿提交或公开分享。
- 对外部署请使用 HTTPS，并启用 `SESSION_COOKIE_SECURE`。
- 来源 IP 始终取实际连接地址，不解析代理转发头。使用反向代理时，统计和登录限流会以代理地址识别来源。
- 访问统计默认保留明文来源 IP；可在 `AppConfig.py` 中将 `ANALYTICS_STORE_RAW_IP` 设为 `False`。
- 默认统计保留期为 90 天，过期记录在服务启动时清理。

## 本地运行

建议使用 Python 3.13，与 Docker 镜像保持一致。无需单独安装数据库服务。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r Requirements.txt

# 首次建库时设置；已有数据库可跳过
read -r -s -p "初始管理员密码：" SHUSHU_ADMIN_PASSWORD
echo
export SHUSHU_ADMIN_PASSWORD

python RunServer.py
```

本地运行使用 Flask 开发服务器；正式部署推荐采用上面的 Docker 方式。

## 项目结构

```text
.
├── RunServer.py            应用入口
├── AppConfig.py            全局配置
├── Requirements.txt        Python 依赖
├── Dockerfile              容器镜像
├── DockerCompose.yml       服务编排
├── EntryPoint.sh           容器启动脚本
├── Api/                    页面与接口
├── Core/                   数据存储、账号安全与访问统计
├── Web/
│   ├── Templates/          页面模板
│   └── Static/
│       ├── CSS/            样式
│       ├── JS/             交互脚本
│       ├── Images/         图标与背景
│       └── robots.txt      爬虫访问声明
└── Data/                   运行时数据（自动生成）
```

**技术栈**：Python · Flask · SQLite · Gunicorn · 原生 HTML / CSS / JavaScript
