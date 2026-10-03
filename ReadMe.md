# 鼠鼠娱乐中心 · 门户首页

Flask + SQLite 实现的服务导航首页，样式参考 `ReferencePhoto.png`。

## Docker 部署

以下命令使用 Bash。

```bash
# 首次启动前设置至少 12 个字符的管理员密码（输入不回显）
read -r -s -p "初始管理员密码：" SHUSHU_ADMIN_PASSWORD
echo
export SHUSHU_ADMIN_PASSWORD

# 构建并启动
docker compose -f DockerCompose.yml up -d --build

# 看日志 / 停止
docker compose -f DockerCompose.yml logs -f
docker compose -f DockerCompose.yml down
```

compose 默认只认 `docker-compose.yml` / `compose.yaml`，本文件按项目的驼峰命名
规则取名，所以要带 `-f`。

- 访问 http://localhost:12339/ ，后台 http://localhost:12339/Admin/Login
- 数据存在命名卷 `shushu-mainpage-data` 里（数据库 + 会话密钥），
  重建容器不会丢
- 容器内跑的是 **gunicorn**（`EntryPoint.sh`），不是 Flask 开发服务器；
  时会区强制为 `Asia/Shanghai`，否则访问统计按天分组会错 8 小时

### 两个必须知道的安全点

1. **`.dockerignore` 排除了 `Data/`**。这个目录里有 `SecretKey.txt`（会话签名
   密钥）和管理员密码哈希 —— 打进镜像层就等于随镜像分发出去，任何人拿到镜像
   都能伪造管理员登录态。运行时靠卷挂载提供。
2. **`.` 会把整个目录送进构建上下文**，改 `.dockerignore` 时留意别把
   `Data/` 放回来。

### 常用环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SHUSHU_ADMIN_PASSWORD` | 空 | 首次建库必填，至少 12 个字符；已有账号不受影响 |
| `SHUSHU_TRUSTED_PROXIES` | 空 | 可信代理 IP / CIDR，逗号分隔；默认忽略转发头 |
| `SERVER_PORT` | `12339` | 监听端口 |
| `SHUSHU_SECRET_KEY` | 空 | 留空则用卷里的 `Data/SecretKey.txt` |
| `SESSION_COOKIE_SECURE` | `false` | 走 HTTPS 时设为 `True` |
| `GUNICORN_WORKERS` | `2` | SQLite 是单写者，别开大；锁冲突就降到 `1` |
| `GUNICORN_THREADS` | `4` | 并发主要靠线程 |

## 快速开始（本地开发）

```bash
# 以下命令使用 Bash；先创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 1. 安装依赖
python -m pip install -r Requirements.txt

# 2. 首次建库前设置管理员密码（至少 12 个字符，输入不回显）
read -r -s -p "初始管理员密码：" SHUSHU_ADMIN_PASSWORD
echo
export SHUSHU_ADMIN_PASSWORD

# 3. 启动
python RunServer.py
```

- 首页：http://localhost:12339/
- 后台：http://localhost:12339/Admin/Login
- 初始管理员：`admin`，密码使用首次启动时设置的 `SHUSHU_ADMIN_PASSWORD`。
- 未设置密码或密码少于 12 个字符时，新数据库初始化会失败；已有数据库不会重置密码。
- 初始化后可移除该环境变量；以后在后台修改密码。

首次启动会自动创建 `Data/MainPage.db`，并写入参考图中的全部内容。

端口、密钥、锁定策略等都在 `AppConfig.py` 里改。

### 反向代理来源 IP

默认使用实际连接的来源 IP，忽略 `X-Forwarded-For`。需要反向代理时，
通过 `SHUSHU_TRUSTED_PROXIES` 配置实际代理的 IP 或 CIDR，多个值用逗号分隔。
代理必须覆盖转发头，或在其右侧追加真实连接来源；应用从右向左跳过可信代理，
取第一个不可信地址，避免客户端伪造的左侧地址绕过登录限流。
不要配置 `0.0.0.0/0`、`::/0` 或包含普通客户端的网段。

## 两步验证（2FA）

后台 →「账号安全」→「两步验证」：

1. 填当前密码 → 生成二维码
2. 用验证器 App 扫码（Google / Microsoft Authenticator、Authy、1Password 均可）
3. 输入 App 显示的 6 位码完成绑定
4. 保存弹出的 10 个恢复码

开启后登录分两步：密码通过后仍需输入动态码。验证器丢失时可用恢复码顶替，每个恢复码只能用一次。

**安全设计：**

- 密钥用 pyotp 生成校验，不自己实现密码学
- 恢复码用 Werkzeug 默认的 **scrypt** 哈希存储，仅在生成时明文显示一次；
  消费走带条件的原子更新，避免并发复用同一个码
- 密码校验通过但未过第二因子时，不授予任何后台权限；
  「已过密码」的挂起态只保留 5 分钟（`PENDING_TOTP_SECONDS`）

失败次数与锁定时间在 `AppConfig.py` 中调整。

### 限流按阶段用不同粒度

| 阶段 | 计数键 | 原因 |
| --- | --- | --- |
| 密码（未认证） | 来源 IP + 用户名 | 若按账号计数，任何人都能靠故意输错密码把站长锁在门外 |
| 动态码（已过密码） | 用户名 | 对方已持有密码，必须账号级封锁 |

两个阶段都在**验码之前**先查锁定状态。计数用单条带 `RETURNING` 的 SQL
完成——早先是「读一次再写一次」，并发请求会读到同一初值各加一，
增量全部丢失（实测 30 并发只记到 1 次），限流等于不存在。

## 访问统计

后台顶栏「访问统计」，两个子页面：

| 页面 | 内容 |
| --- | --- |
| `/Admin/Analytics` | KPI 统计卡、按天趋势折线图、24 小时时段分布、热门页面排行、访问来源 |
| `/Admin/Analytics/Records` | 访问明细，支持时间范围、路径筛选、分页 |

时间范围与「是否含机器人」是**全局筛选**，放在顶部一行，所有图表按同一个切片
重算 —— 每张图各带一套筛选是反模式，会让读者以为在看同一份数据。

### 记什么、不记什么

- **只记公开页面**。`/Static/`、`/Health`、`/Admin/` 前缀都在记录前被过滤掉：
  静态资源会把表撑爆，后台是站长自己的操作，会把「热门页面」冲掉
- **只记路径，不记查询串**。查询串里可能有 token 之类的东西，落库没必要也不安全
- **访客身份用不可逆哈希**：`HMAC(会话密钥, IP + UA)`。密钥来自
  `Data/SecretKey.txt`，没有它无法反推。用固定密钥（而不是每日换盐）是为了让
  跨天的独立访客数也准确
- **原始 IP 默认记录**，由 `ANALYTICS_STORE_RAW_IP` 控制。关掉后独立访客数
  依然准确，但明细里看不到具体来源了
- 超过 `ANALYTICS_RETENTION_DAYS`（默认 90 天）的记录会自动清理

以上都在 `AppConfig.py` 的「访问统计」段。

### 图表约定

图表用参考调色板的**已验证**色值，没有替换成品牌色 —— 替换配色必须重新跑
色差校验（色盲可辨性），而项目里没有 Node 运行时跑不了那个脚本。要改配色请
先补齐校验。

其他几条硬约束：所有排行条**同色**（按数值深浅上色会把条长重复编码一遍）；
网格线是一像素**实线**；折线只有一条纵轴；每张图都配了**数据表**折叠视图，
不依赖颜色也能读数。

## 安全

### 会话密钥

Flask 用的是**客户端 session**，整个登录态只靠 `SECRET_KEY` 签名。密钥一旦随
源码泄露，任何人都能自己签一个 `{"AdminUser": "admin"}` 的 cookie，
**密码和两步验证全部绕过**。所以密钥不再硬编码：

- 首次启动随机生成，写入 `Data/SecretKey.txt`（权限 600，已在 `.gitignore` 中）
- 需要固定密钥（多进程/多机共享会话）时设环境变量 `SHUSHU_SECRET_KEY`
- **这个文件不能外传、不能进版本库、不能放进备份分享**

### 其他

- **URL 与颜色的入库校验**：`Core/Sanitizer.py`。Jinja 的自动转义只防属性逃逸，
  拦不住 `href="javascript:..."`，也拦不住 `style="--CardColor: ..."` 里的
  CSS 注入（autoescape 把 `'` 转成 `&#39;`，浏览器解析属性时会先解码回 `'`）。
  所有会进 href / style 的字段在写库前过白名单校验。
- **安全响应头**：`Content-Security-Policy`（`script-src 'self'`）、
  `X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、`Referrer-Policy`。
  模板里已无内联脚本，所以 `script-src` 不需要 `unsafe-inline`。
- **CSRF**：写接口全是 POST + JSON，配合 `SameSite=Lax` 与不开放 CORS，
  跨站打不进来。但这是**两层依赖**——一旦为了图方便放宽 content-type 或加上
  CORS，全部写接口会立刻变成 0 点击 CSRF。改动这两处时务必注意。

### 爬虫协议

`Web/Static/robots.txt`，由 `Api/PublicApi.py` 的 `/robots.txt` 路由按 `text/plain`
提供（**必须挂在根路径**——爬虫只读根目录那一份，不会去 `/Static/` 下找）。

全站 `Disallow: /`，不设搜索引擎白名单。另有一节权利声明：不授予任何明示或默示
许可、技术措施声明、禁止指使第三方实施。

需要清楚的一点是，robots.txt **不是拦截手段**，拦不住任何恶意程序。它唯一能真正
产生法律效果的机制是**构成侵权警告**：民法典第一千一百八十五条与著作权法第五十四条
的惩罚性赔偿（1–5 倍），要件正是最高法法释〔2026〕7 号所列的「经有效通知、警告后
仍继续实施侵权」。本文件就是这个「通知」。

法条援引分两层。主要依据不依赖主体资格：《著作权法》第五十二至五十四条、
《民法典》第一千一百六十五、一千一百六十九、一千一百八十五、一千一百九十四条、
《数据安全法》第三十二条、《网络安全法》第二十七条、《刑法》第二百五十三条之一
（侵犯公民个人信息罪，比第二百八十五条更贴合抓取行为）、《个人信息保护法》。
补充依据是《反不正当竞争法》第十三条（2025 年修订版）——它保护的是「经营者」，
个人站点援引有主体不适格风险，所以放在补充位置并单独论述了适格理由。

改文案直接编辑那个 txt 文件即可，不必动代码。

> **一个需要留意的自相矛盾**：文件里主张访客 IP / UA / 访问时间属于受《刑法》
> 第二百五十三条之一与《个人信息保护法》保护的公民个人信息，但本站自己正在
> 明文存储访客 IP（`AppConfig.ANALYTICS_STORE_RAW_IP = True`）。个人站点存储
> 访客明文 IP 缺少《个人信息保护法》第十三条的合法性基础，主张他人不得抓取
> 的同时自身留存，属于「双手不干净」的抗辩弱点。建议改为 `False`——保留不可
> 逆散列后独立访客数依然准确，只是明细里看不到具体 IP。见下节。

### 部署前必做

1. **首次建库设置独立的强密码**；已有部署如果使用过旧版初始口令，请到后台修改
2. **开启两步验证**
3. 走 HTTPS 时把 `AppConfig.py` 的 `SESSION_COOKIE_SECURE` 设为 `True`

启动时会自动体检以上几项并在终端提示。

## 目录结构

```
MainPage/
├── RunServer.py            程序入口
├── AppConfig.py            路径 / 端口 / 密钥 / 初始管理员
├── Requirements.txt        依赖清单
├── Dockerfile              生产镜像
├── DockerCompose.yml       容器编排（需 -f 指定）
├── EntryPoint.sh           容器入口：建库 → 清理旧记录 → gunicorn
├── Core/                   核心层
│   ├── Database.py         SQLite 连接、建表
│   ├── SeedData.py         首次运行的种子数据
│   ├── Repository.py       站点内容的数据访问（SQL 集中在此）
│   ├── Sanitizer.py        入库前的 URL / 颜色 / 文件名校验
│   ├── TotpService.py      两步验证算码、验码、二维码、恢复码
│   ├── Analytics.py        访问统计：记录、聚合、保留策略
│   └── ChartBuilder.py     统计数据 → 图表几何
├── Api/                    接口层
│   ├── PublicApi.py        首页、只读接口与 /robots.txt
│   ├── AdminApi.py         后台页面与增删改接口
│   └── AnalyticsApi.py     访问统计子页面
├── Web/
│   ├── Templates/          页面模板
│   │   ├── IndexPage.html
│   │   ├── AdminLoginPage.html
│   │   ├── AdminPage.html
│   │   ├── AdminHeaderPartial.html
│   │   ├── AdminAnalyticsPage.html
│   │   └── AdminAnalyticsRecordsPage.html
│   └── Static/
│       ├── Css/            MainStyle.css / AdminStyle.css
│       ├── Js/
│       │   ├── ThemeBoot.js   主题启动（必须在 head 同步加载）
│       │   ├── MainScript.js  首页 3D 与视差
│       │   └── AdminScript.js 后台交互
│       ├── Images/         图标与背景图
│       └── robots.txt      爬虫排除协议（由根路径 /robots.txt 提供）
└── Data/
    └── MainPage.db         SQLite 数据库（自动生成，勿提交）
```

## 数据表

| 表名 | 用途 |
| --- | --- |
| `SiteSetting` | 站点标题、页脚、背景图等键值配置 |
| `AdminAccount` | 管理员账号（pbkdf2 哈希存储） |
| `LogPanel` | 左侧「资源更新日志」/ 中间「系统更新日志」面板 |
| `PanelNotice` | 面板顶部的提示行（注意／可选／QQ群） |
| `UpdateLog` | 更新日志条目 |
| `ServiceCard` | 服务入口卡片（统一网格，顺序由 `SortOrder` 决定） |
| `AdminTotp` | 两步验证密钥与恢复码 |
| `LoginAttempt` | 登录失败计数与锁定时间 |

## 版面结构

```
┌──────────────────┬──────────────────┐
│  资源更新日志     │  系统更新日志     │   ← 最高 45% 屏高
│  （默认 6 条）    │  （默认 6 条）    │      超出内部滚动
│  [展开全部]       │  [展开全部]       │
├──────────────────┴──────────────────┤
│  卡片网格（4 列，所有卡片等大）        │   ← 吃掉剩余空间
└─────────────────────────────────────┘
```

所有服务卡片一视同仁，排成同一个网格，顺序由后台的「排序值」决定。
不再有「侧栏 / 底部」的区分（数据库 `ServiceCard.GroupKey` 列保留并固定为
`MAIN`，方便以后想恢复分组时使用）。

**日志面板限高**：最高 `45dvh`，超出部分在面板内滚动；卡片网格吃掉剩余空间。
手机上（≤900）取消限高、改回整页滚动——嵌套滚动区域在触屏上不好用。

**日志折叠**：每块面板默认只显示前 N 条，其余收在「展开全部（还有 N 条）」里。
N 在后台「站点设置 → 每块日志默认显示条数」改（默认 6）。
展开用 `<input type="checkbox">` + CSS 兄弟选择器实现，**不依赖 JavaScript**，
禁用 JS 也能正常展开收起，键盘可 Tab 聚焦、空格切换。

列数随宽度自适应：≥1180 四列 → ≤1180 三列 → ≤640 两列；
日志面板 ≤900 起改为上下堆叠。

## 视觉设计

Apple 式材料语言：毛玻璃（`saturate(180%) blur(20px)`）+ 内高光 + 三层柔和阴影。
配色以中性灰白为主，彩色只出现在强调位置（日期、链接）。

**3D 效果只有三处，都刻意做得很轻：**

1. 服务卡片的指针跟随倾斜（上限 5°）+ 跟随指针的高光
2. 图标 / 标题 / 副标题用 `translateZ` 分层，倾斜时产生真实视差
3. 背景光斑跟随指针做 ±16px 视差位移

没有霓虹、粒子、旋转方块那类效果。倾斜角度在 `MainScript.js` 的
`TILT_RANGE_DEGREES` 调，视差幅度在 `PARALLEL_RANGE_PIXELS` 调。

触屏设备和系统开启「减少动态效果」时，3D 与视差自动跳过。

## 主题与背景

首页、后台、登录页**共用同一套设计令牌**（`MainStyle.css` 与 `AdminStyle.css`
开头的 `:root` 变量块），因此三处样式天然一致，改配色只需改这两个块。

主题解析集中在 `Web/Static/Js/ThemeBoot.js`：它在 `<head>` 里**同步**加载，
在首屏绘制前就把 `data-theme` 定成 `light` 或 `dark`。这样 CSS 只需处理两种终态，
不必把深色变量写两遍，也不会出现闪白。三个页面的切换按钮都调用
`window.ShuShuTheme.Toggle()`。

- **默认主题**：后台 →「站点设置 → 默认主题」，可选「跟随系统 / 浅色 / 深色」。
  「跟随系统」走 `prefers-color-scheme`，并且会在系统切换时实时跟随。
  右上角按钮手动切换后写入 `localStorage`，不再跟随系统。
- **背景图**：把图片放进 `Web/Static/Images/`，例如 `Wallpaper.png`，
  然后在后台填这个文件名。留空则使用内置的 Apple 风渐变。
  用自定义壁纸时会自动加一层压暗 + 模糊，保证面板上的字读得清。
  图片建议 2560×1440 以上，横版。

## 换服务图标

把 SVG / PNG 放进 `Web/Static/Images/`，然后在后台「服务卡片」里改「图标文件名」。
内置图标是原创 SVG，可自由替换成自己的图。

## 部署提示

`RunServer.py` 用的是 Flask 开发服务器。对外提供服务时建议换成生产级 WSGI：

```bash
python -m pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:12339 "RunServer:CreateApplication()"
```

同时记得修改 `AppConfig.py` 里的 `SECRET_KEY`。