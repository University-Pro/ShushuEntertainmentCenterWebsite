"""入库前的取值校验。

Jinja 的自动转义只保证 HTML 属性不被「逃逸」，拦不住两类东西：

1. 伪协议。`href="javascript:..."` 里的字符全是合法属性字符，转义后照样执行。
2. CSS 注入。`style="--CardColor: {{ 值 }}"` 中，autoescape 把 `'` 转成 `&#39;`，
   但浏览器解析属性值时会先把实体解码回 `'`，CSS 解析器拿到的就是未转义的引号，
   于是能闭合 url('...') 再追加任意声明（加载外部资源、覆盖页面元素钓鱼）。

所以会进 href 或 style 的字段，一律在**写入数据库前**过一遍这里。
校验放在写入口而不是渲染口，是为了把所有写入路径一次性覆盖掉。
"""

import re

# 只放行这三种外链协议。data: 同样能执行脚本，所以不在白名单里。
SAFE_URL_SCHEMES = ("http://", "https://", "mailto:")

_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$|^#[0-9A-Fa-f]{3}$")

# 浏览器在解析协议前会丢掉这些字符，`java\nscript:` 因此可能被当成 javascript:
_CONTROL_CHARACTERS = str.maketrans("", "", "\t\n\r\x00")


def SanitizeUrl(value):
    """放行 http/https/mailto 与站内相对路径，其余一律返回空串。

    采用白名单而非黑名单：只要不是明确认识的形式，就不要。
    """
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    normalized = text.lower().translate(_CONTROL_CHARACTERS)

    # 站内相对路径：单斜杠开头。`//host` 是协议相对地址，指向外部，排除
    if normalized.startswith("/") and not normalized.startswith("//"):
        return text

    if normalized.startswith(SAFE_URL_SCHEMES):
        return text

    return ""


def SanitizeColor(value, default="#0071E3"):
    """只接受 #RGB / #RRGGBB。挡不住的话 theme color 就是 CSS 注入口。"""
    if value is None:
        return default

    text = str(value).strip()
    return text if _COLOR_PATTERN.match(text) else default


def SanitizeImageName(value):
    """图标与背景图只允许 Static/Images/ 下的纯文件名，不接受任何路径成分。"""
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    if "/" in text or "\\" in text or ".." in text:
        return ""

    return text


def SanitizePlainText(value, max_length=None):
    """去掉首尾空白与不可见控制字符；可选截断长度。"""
    if value is None:
        return ""

    text = str(value).strip().translate(_CONTROL_CHARACTERS)
    if max_length and len(text) > max_length:
        text = text[:max_length]
    return text


def SanitizeInteger(value, default=0, minimum=None, maximum=None):
    """安全的整数转换，可带上下界。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default

    if minimum is not None and number < minimum:
        return minimum
    if maximum is not None and number > maximum:
        return maximum
    return number