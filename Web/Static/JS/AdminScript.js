/* ==========================================================================
   鼠鼠娱乐中心 —— 后台管理脚本
   同一份文件同时服务登录页与控制台，靠页面元素是否存在来区分。
   ========================================================================== */

(function () {
    "use strict";

    var PANEL_LABELS = { RESOURCE: "资源更新日志", SYSTEM: "系统更新日志" };

    // 站点设置的可编辑字段（顺序即展示顺序）
    var SETTING_FIELDS = [
        { Key: "SiteTitle", Label: "站点标题", Type: "text" },
        { Key: "SiteTitleEmoji", Label: "标题后缀表情", Type: "text" },
        { Key: "SiteDescription", Label: "站点描述（SEO）", Type: "text" },
        { Key: "FooterText", Label: "页脚文字", Type: "text" },
        { Key: "LogPreviewCount", Label: "每块日志默认显示条数", Type: "number" },
        { Key: "BackgroundImageUrl", Label: "背景图文件名（留空用内置渐变）", Type: "text" },
        {
            Key: "DefaultTheme",
            Label: "默认主题",
            Type: "select",
            Options: { auto: "跟随系统", light: "浅色", dark: "深色" }
        }
    ];

    /* ---------------------------------------------------------- 基础工具 */

    function EscapeHtml(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function Element(id) {
        return document.getElementById(id);
    }

    var toastTimer = null;
    function Toast(message, isError) {
        var box = Element("ToastBox");
        if (!box) {
            window.alert(message);
            return;
        }
        box.textContent = message;
        box.classList.toggle("IsError", !!isError);
        box.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            box.hidden = true;
        }, 2600);
    }

    /** 统一请求封装：自动带 Cookie、统一错误提示、401 时跳回登录页 */
    function ApiRequest(url, method, body) {
        return window.fetch(url, {
            method: method || "GET",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: body ? JSON.stringify(body) : undefined
        }).then(function (response) {
            if (response.status === 401) {
                window.location.href = "/Admin/Login";
                throw new Error("未登录");
            }
            return response.json().catch(function () {
                throw new Error("服务端返回了非 JSON 内容");
            }).then(function (payload) {
                if (!response.ok || !payload.Success) {
                    throw new Error(payload.Message || "请求失败");
                }
                return payload.Data || {};
            });
        });
    }

    /* ---------------------------------------------------------- 主题切换 */

    // 主题的解析在 ThemeBoot.js 里完成，这里只把按钮接上去。
    // 登录页和后台页共用同一个 id，所以放在分支之前统一处理。
    (function () {
        var toggle = Element("ThemeToggle");
        if (toggle && window.ShuShuTheme) {
            toggle.addEventListener("click", function () {
                window.ShuShuTheme.Toggle();
            });
        }
    })();

    /* ---------------------------------------------------------- 趋势图悬停 */

    /* 十字准星 + 提示框。
       热区里本来就有一个 <title>，所以禁用 JS 时浏览器会显示原生提示，
       这里只是把它换成更好看的一套。 */
    (function () {
        var chart = document.querySelector(".LineChart");
        var tooltip = Element("TrendTooltip");
        var crosshair = Element("TrendCrosshair");

        if (!chart || !tooltip || !crosshair) {
            return;
        }

        var viewBox = chart.viewBox.baseVal;

        function Hide() {
            tooltip.hidden = true;
            crosshair.hidden = true;
        }

        // SVG 用 viewBox 等比缩放，所以要按实际渲染宽度换算
        function ScaleFactor() {
            var width = chart.getBoundingClientRect().width;
            return viewBox.width ? (width / viewBox.width) : 1;
        }

        Array.prototype.forEach.call(
            chart.querySelectorAll(".ChartHitBand"),
            function (band) {
                var titleNode = band.querySelector("title");
                if (!titleNode) {
                    return;
                }

                band.addEventListener("pointerenter", function () {
                    var scale = ScaleFactor();
                    var centerUser = Number(band.getAttribute("data-center"));
                    var plotTopUser = Number(crosshair.getAttribute("y1"));

                    crosshair.setAttribute("x1", centerUser);
                    crosshair.setAttribute("x2", centerUser);
                    crosshair.hidden = false;

                    tooltip.textContent = titleNode.textContent;
                    tooltip.hidden = false;

                    // 先显示再量宽度，然后夹在绘图区内，避免贴边时溢出
                    var halfWidth = tooltip.offsetWidth / 2;
                    var chartWidth = viewBox.width * scale;
                    var left = centerUser * scale;
                    left = Math.max(halfWidth, Math.min(chartWidth - halfWidth, left));

                    tooltip.style.left = left + "px";
                    tooltip.style.top = (plotTopUser * scale + 6) + "px";
                });

                band.addEventListener("pointerleave", Hide);
            }
        );

        chart.addEventListener("pointerleave", Hide);
    })();

    /* ---------------------------------------------------------- 登录页 */

    function InitializeLoginPage() {
        var loginForm = Element("LoginForm");
        if (!loginForm) {
            return;
        }

        var loginMessage = Element("LoginMessage");
        var loginButton = Element("LoginButton");
        var totpForm = Element("TotpForm");
        var totpMessage = Element("TotpMessage");
        var totpButton = Element("TotpButton");
        var totpCode = Element("TotpCode");

        function ShowMessage(node, text, isSuccess) {
            node.textContent = text;
            node.classList.toggle("IsSuccess", !!isSuccess);
            node.hidden = false;
        }

        function HideMessage(node) {
            node.hidden = true;
        }

        /* -------- 第一步：账号密码 -------- */

        loginForm.addEventListener("submit", function (event) {
            event.preventDefault();
            HideMessage(loginMessage);
            loginButton.disabled = true;
            loginButton.textContent = "登录中…";

            ApiRequest("/Admin/Api/Login", "POST", {
                UserName: Element("UserName").value.trim(),
                Password: Element("Password").value
            }).then(function (payload) {
                if (payload.NeedTotp) {
                    // 密码对了，等第二因子
                    loginForm.hidden = true;
                    totpForm.hidden = false;
                    HideMessage(totpMessage);
                    totpCode.value = "";
                    totpCode.focus();
                } else {
                    ShowMessage(loginMessage, "登录成功，正在跳转…", true);
                    window.location.href = "/Admin/";
                }
            }).catch(function (error) {
                ShowMessage(loginMessage, error.message, false);
                loginButton.disabled = false;
                loginButton.textContent = "登 录";
            });
        });

        /* -------- 第二步：两步验证码 -------- */

        totpForm.addEventListener("submit", function (event) {
            event.preventDefault();
            HideMessage(totpMessage);
            totpButton.disabled = true;
            totpButton.textContent = "验证中…";

            ApiRequest("/Admin/Api/VerifyTotp", "POST", {
                Code: totpCode.value.trim()
            }).then(function (payload) {
                if (payload.UsedRecoveryCode) {
                    // 用恢复码进来的，提示一下剩余数量再跳转
                    window.alert("已使用恢复码登录。\n剩余恢复码："
                        + payload.RemainingRecoveryCodes + " 个，建议尽快重新生成。");
                }
                window.location.href = "/Admin/";
            }).catch(function (error) {
                ShowMessage(totpMessage, error.message, false);
                totpCode.value = "";
                totpCode.focus();

                // 次数超限 / 验证超时，挂起会话已失效，退回第一步
                if (/重新登录|验证超时|失败次数过多/.test(error.message)) {
                    totpForm.hidden = true;
                    loginForm.hidden = false;
                    loginButton.disabled = false;
                    loginButton.textContent = "登 录";
                    Element("Password").value = "";
                } else {
                    totpButton.disabled = false;
                    totpButton.textContent = "验 证";
                }
            });
        });

        totpCode.addEventListener("input", function () {
            // 纯数字自动提交，省一次点击；恢复码带连字符不会触发
            if (/^\d{6}$/.test(totpCode.value.trim()) && !totpButton.disabled) {
                totpForm.dispatchEvent(new Event("submit", { cancelable: true }));
            }
        });

        Element("TotpBackButton").addEventListener("click", function () {
            totpForm.hidden = true;
            loginForm.hidden = false;
            HideMessage(loginMessage);
            loginButton.disabled = false;
            loginButton.textContent = "登 录";
            Element("Password").value = "";
            Element("Password").focus();
        });

        Element("UserName").focus();
    }

    InitializeLoginPage();

    /* ---------------------------------------------------------- 控制台 */

    var Tabs = Element("AdminTabs");
    if (!Tabs) {
        return; // 当前是登录页
    }

    var OverviewData = { Logs: [], Cards: [], Panels: [], Notices: [], Settings: {} };
    var DialogSubmitHandler = null;

    /* ---------------------------------------------------------- 标签页切换 */

    function ActivateTab(tabName) {
        Array.prototype.forEach.call(document.querySelectorAll(".TabButton"), function (button) {
            button.classList.toggle("IsActive", button.getAttribute("data-tab") === tabName);
        });
        Array.prototype.forEach.call(document.querySelectorAll(".TabPanel"), function (panel) {
            panel.classList.toggle("IsActive", panel.getAttribute("data-panel") === tabName);
        });
    }

    Tabs.addEventListener("click", function (event) {
        var button = event.target.closest(".TabButton");
        if (button) {
            ActivateTab(button.getAttribute("data-tab"));
        }
    });

    /* ---------------------------------------------------------- 弹窗 */

    /* 弹窗打开时锁住背后的页面滚动。
   只切 hidden 的话，在标题栏/按钮区/遮罩空白处起手的滑动会落到文档滚动容器上，
   手机上就是「弹窗没动，背后页面跑了」。iOS 需要 fixed + 记住位置才能真的锁住。 */
    var LockedScrollY = 0;

    function LockPageScroll() {
        LockedScrollY = window.scrollY || window.pageYOffset || 0;
        document.body.style.position = "fixed";
        document.body.style.top = -LockedScrollY + "px";
        document.body.style.width = "100%";
        document.body.style.overflow = "hidden";
    }

    function UnlockPageScroll() {
        document.body.style.position = "";
        document.body.style.top = "";
        document.body.style.width = "";
        document.body.style.overflow = "";
        window.scrollTo(0, LockedScrollY);
    }

    function OpenDialog(title, bodyHtml, onSubmit, confirmLabel) {
        Element("DialogTitle").textContent = title;
        Element("DialogBody").innerHTML = bodyHtml;
        Element("DialogConfirm").textContent = confirmLabel || "保存";
        Element("DialogMask").hidden = false;
        DialogSubmitHandler = onSubmit;
        LockPageScroll();
    }

    function CloseDialog() {
        Element("DialogMask").hidden = true;
        Element("DialogBody").innerHTML = "";
        DialogSubmitHandler = null;
        UnlockPageScroll();
    }

    Element("DialogClose").addEventListener("click", CloseDialog);
    Element("DialogCancel").addEventListener("click", CloseDialog);
    Element("DialogMask").addEventListener("click", function (event) {
        if (event.target === Element("DialogMask")) {
            CloseDialog();
        }
    });

    Element("DialogConfirm").addEventListener("click", function () {
        if (DialogSubmitHandler) {
            DialogSubmitHandler();
        }
    });

    /** 从弹窗中读取指定字段的值 */
    function FieldValue(name) {
        var node = Element("DialogBody").querySelector("[name='" + name + "']");
        if (!node) {
            return "";
        }
        if (node.type === "checkbox") {
            return node.checked ? 1 : 0;
        }
        return node.value;
    }

    /* iOS 对 type=text 默认首字母大写 + 自动更正。
   URL、文件名、颜色、账号这些字段一旦被改写，用户还看不出为什么失败。 */
    var NO_AUTOCORRECT_FIELDS = [
        "TargetUrl", "ImageUrl", "ThemeColor", "LinkUrl",
        "BackgroundImageUrl", "SubtitleLinkUrl", "NoticeLinkUrl",
    ];

    function FieldAttributes(name) {
        if (NO_AUTOCORRECT_FIELDS.indexOf(name) === -1) {
            return "";
        }
        return ' inputmode="url" autocapitalize="none" autocorrect="off" spellcheck="false"';
    }

    function FieldRow(label, name, value, type, options) {
        var html = '<label class="FieldLabel" for="' + name + '">' + EscapeHtml(label) + "</label>";

        if (type === "textarea") {
            html += '<textarea class="FieldInput" id="' + name + '" name="' + name + '" rows="4">'
                + EscapeHtml(value) + "</textarea>";
        } else if (type === "select") {
            html += '<select class="FieldInput" id="' + name + '" name="' + name + '">';
            Object.keys(options).forEach(function (optionValue) {
                var selected = String(value) === String(optionValue) ? " selected" : "";
                html += '<option value="' + EscapeHtml(optionValue) + '"' + selected + ">"
                    + EscapeHtml(options[optionValue]) + "</option>";
            });
            html += "</select>";
        } else if (type === "checkbox") {
            var checked = Number(value) ? " checked" : "";
            html += '<label class="FieldLabel" style="font-weight:500">'
                + '<input type="checkbox" id="' + name + '" name="' + name + '"' + checked + "> 在首页显示</label>";
        } else {
            html += '<input class="FieldInput" type="' + type + '" id="' + name + '" name="' + name
                + '" value="' + EscapeHtml(value) + '"' + FieldAttributes(name) + ">";
        }

        return html;
    }

    /* ---------------------------------------------------------- 更新日志 */

    function RenderLogTable() {
        var filter = Element("LogPanelFilter").value;
        var rows = OverviewData.Logs.filter(function (log) {
            return !filter || log.PanelKey === filter;
        });

        var body = Element("LogTableBody");

        if (!rows.length) {
            body.innerHTML = '<tr><td class="EmptyRow" colspan="7">暂无日志</td></tr>';
            return;
        }

        body.innerHTML = rows.map(function (log) {
            var summary = [log.Title, log.Content].filter(Boolean).join(" ");
            var tagClass = log.PanelKey === "RESOURCE" ? "IsResource" : "IsSystem";

            return "<tr>"
                + "<td>" + log.Id + "</td>"
                + '<td><span class="Tag ' + tagClass + '">'
                + EscapeHtml(PANEL_LABELS[log.PanelKey] || log.PanelKey) + "</span></td>"
                + "<td>" + EscapeHtml(log.LogDate) + "</td>"
                + '<td class="CellEllipsis CellStrong" title="' + EscapeHtml(summary) + '">'
                + EscapeHtml(summary) + "</td>"
                + "<td>" + log.SortOrder + "</td>"
                + '<td><span class="Tag ' + (Number(log.IsVisible) ? "IsVisible\">可见" : "IsHidden\">隐藏")
                + "</span></td>"
                + '<td><div class="RowActions">'
                + '<button class="MiniButton" data-action="EditLog" data-id="' + log.Id + '">编辑</button>'
                + '<button class="MiniButton IsDanger" data-action="DeleteLog" data-id="' + log.Id + '">删除</button>'
                + "</div></td>"
                + "</tr>";
        }).join("");
    }

    function EditLog(logId) {
        var log = logId
            ? OverviewData.Logs.filter(function (item) { return item.Id === logId; })[0]
            : null;

        var record = log || {
            Id: 0, PanelKey: "RESOURCE", LogDate: new Date().toISOString().slice(0, 10),
            Title: "", Content: "", LinkUrl: "", SortOrder: 0, IsVisible: 1
        };

        OpenDialog(log ? "编辑日志 #" + log.Id : "新增日志",
            FieldRow("所属面板", "PanelKey", record.PanelKey, "select", PANEL_LABELS)
            + FieldRow("日期", "LogDate", record.LogDate, "date")
            + FieldRow("标题（资源名，可留空）", "Title", record.Title, "text")
            + FieldRow("内容", "Content", record.Content, "textarea")
            + FieldRow("附带链接（可留空）", "LinkUrl", record.LinkUrl, "text")
            + FieldRow("排序值（越小越靠前）", "SortOrder", record.SortOrder, "number")
            + FieldRow("可见性", "IsVisible", record.IsVisible, "checkbox"),
            function () {
                ApiRequest("/Admin/Api/Log/Save", "POST", {
                    Id: record.Id,
                    PanelKey: FieldValue("PanelKey"),
                    LogDate: FieldValue("LogDate"),
                    Title: FieldValue("Title"),
                    Content: FieldValue("Content"),
                    LinkUrl: FieldValue("LinkUrl"),
                    SortOrder: FieldValue("SortOrder"),
                    IsVisible: FieldValue("IsVisible")
                }).then(function () {
                    CloseDialog();
                    Toast("已保存");
                    return LoadOverview();
                }).catch(function (error) { Toast(error.message, true); });
            });
    }

    function DeleteLog(logId) {
        if (!window.confirm("确定删除这条日志吗？此操作不可恢复。")) {
            return;
        }
        ApiRequest("/Admin/Api/Log/Delete", "POST", { Id: logId })
            .then(function () {
                Toast("已删除");
                return LoadOverview();
            })
            .catch(function (error) { Toast(error.message, true); });
    }

    /* ---------------------------------------------------------- 服务卡片 */

    function RenderCardTable() {
        var body = Element("CardTableBody");

        if (!OverviewData.Cards.length) {
            body.innerHTML = '<tr><td class="EmptyRow" colspan="8">暂无卡片</td></tr>';
            return;
        }

        body.innerHTML = OverviewData.Cards.map(function (card) {
            return "<tr>"
                + "<td>" + card.Id + "</td>"
                + '<td class="CellStrong">' + EscapeHtml(card.Title) + "</td>"
                + "<td>" + EscapeHtml(card.Subtitle) + "</td>"
                + "<td>" + EscapeHtml(card.TargetUrl) + "</td>"
                + "<td>" + EscapeHtml(card.ImageUrl)
                + ' <span class="Tag" style="background:' + EscapeHtml(card.ThemeColor) + '22;color:'
                + EscapeHtml(card.ThemeColor) + '">' + EscapeHtml(card.ThemeColor) + "</span></td>"
                + "<td>" + card.SortOrder + "</td>"
                + '<td><span class="Tag ' + (Number(card.IsVisible) ? "IsVisible\">可见" : "IsHidden\">隐藏")
                + "</span></td>"
                + '<td><div class="RowActions">'
                + '<button class="MiniButton" data-action="EditCard" data-id="' + card.Id + '">编辑</button>'
                + '<button class="MiniButton IsDanger" data-action="DeleteCard" data-id="' + card.Id + '">删除</button>'
                + "</div></td>"
                + "</tr>";
        }).join("");
    }

    function EditCard(cardId) {
        var card = cardId
            ? OverviewData.Cards.filter(function (item) { return item.Id === cardId; })[0]
            : null;

        var record = card || {
            Id: 0, Title: "", Subtitle: "", TargetUrl: "",
            ImageUrl: "", ThemeColor: "#0071E3", SortOrder: 0, IsVisible: 1
        };

        OpenDialog(card ? "编辑卡片 #" + card.Id : "新增卡片",
            FieldRow("标题", "Title", record.Title, "text")
            + FieldRow("副标题", "Subtitle", record.Subtitle, "text")
            + FieldRow("跳转地址", "TargetUrl", record.TargetUrl, "text")
            + FieldRow("图标文件名（Web/Static/Images/ 下）", "ImageUrl", record.ImageUrl, "text")
            + FieldRow("主题色", "ThemeColor", record.ThemeColor, "text")
            + FieldRow("排序值", "SortOrder", record.SortOrder, "number")
            + FieldRow("可见性", "IsVisible", record.IsVisible, "checkbox"),
            function () {
                ApiRequest("/Admin/Api/Card/Save", "POST", {
                    Id: record.Id,
                    Title: FieldValue("Title"),
                    Subtitle: FieldValue("Subtitle"),
                    TargetUrl: FieldValue("TargetUrl"),
                    ImageUrl: FieldValue("ImageUrl"),
                    ThemeColor: FieldValue("ThemeColor"),
                    SortOrder: FieldValue("SortOrder"),
                    IsVisible: FieldValue("IsVisible")
                }).then(function () {
                    CloseDialog();
                    Toast("已保存");
                    return LoadOverview();
                }).catch(function (error) { Toast(error.message, true); });
            });
    }

    function DeleteCard(cardId) {
        if (!window.confirm("确定删除这张卡片吗？")) {
            return;
        }
        ApiRequest("/Admin/Api/Card/Delete", "POST", { Id: cardId })
            .then(function () {
                Toast("已删除");
                return LoadOverview();
            })
            .catch(function (error) { Toast(error.message, true); });
    }

    /* ---------------------------------------------------------- 面板与提示 */

    function RenderPanelEditors() {
        Element("PanelEditorList").innerHTML = OverviewData.Panels.map(function (panel) {
            return '<div class="EditorCard" data-panel-key="' + EscapeHtml(panel.PanelKey) + '">'
                + '<div class="EditorCardHead"><span class="EditorCardName">'
                + EscapeHtml(panel.Title) + "</span>"
                + '<button class="MiniButton" data-action="SavePanel" data-key="'
                + EscapeHtml(panel.PanelKey) + '">保存</button></div>'
                + '<div class="EditorGrid">'
                + FieldRowInline("标题", "PanelTitle", panel.Title)
                + FieldRowInline("副标题", "PanelSubtitle", panel.Subtitle)
                + FieldRowInline("副标题链接文字", "PanelLinkText", panel.SubtitleLinkText)
                + FieldRowInline("副标题链接地址", "PanelLinkUrl", panel.SubtitleLinkUrl)
                + FieldRowInline("排序值", "PanelSortOrder", panel.SortOrder, "number")
                + "</div></div>";
        }).join("");
    }

    function FieldRowInline(label, name, value, type) {
        return '<div><label class="FieldLabel">' + EscapeHtml(label) + "</label>"
            + '<input class="FieldInput" name="' + name + '" type="' + (type || "text")
            + '" value="' + EscapeHtml(value) + '"' + FieldAttributes(name) + "></div>";
    }

    function SelectInline(label, name, value, options) {
        var html = '<div><label class="FieldLabel">' + EscapeHtml(label) + "</label>"
            + '<select class="FieldInput" name="' + name + '">';
        Object.keys(options).forEach(function (optionValue) {
            var selected = String(value) === String(optionValue) ? " selected" : "";
            html += '<option value="' + EscapeHtml(optionValue) + '"' + selected + ">"
                + EscapeHtml(options[optionValue]) + "</option>";
        });
        return html + "</select></div>";
    }

    function SavePanel(panelKey) {
        var scope = Element("PanelEditorList")
            .querySelector("[data-panel-key='" + panelKey + "']");

        function Read(name) {
            return scope.querySelector("[name='" + name + "']").value;
        }

        ApiRequest("/Admin/Api/Panel/Save", "POST", {
            PanelKey: panelKey,
            Title: Read("PanelTitle"),
            Subtitle: Read("PanelSubtitle"),
            SubtitleLinkText: Read("PanelLinkText"),
            SubtitleLinkUrl: Read("PanelLinkUrl"),
            SortOrder: Read("PanelSortOrder"),
            IsVisible: 1
        }).then(function () {
            Toast("面板已保存");
            return LoadOverview();
        }).catch(function (error) { Toast(error.message, true); });
    }

    function RenderNoticeEditors() {
        Element("NoticeEditorList").innerHTML = OverviewData.Notices.map(function (notice) {
            return '<div class="EditorCard" data-notice-id="' + notice.Id + '">'
                + '<div class="EditorCardHead">'
                + '<span class="EditorCardName">'
                + EscapeHtml(PANEL_LABELS[notice.PanelKey] || notice.PanelKey)
                + " · 提示 #" + notice.Id + "</span>"
                + '<div class="RowActions">'
                + '<button class="MiniButton" data-action="SaveNotice" data-id="' + notice.Id + '">保存</button>'
                + '<button class="MiniButton IsDanger" data-action="DeleteNotice" data-id="' + notice.Id + '">删除</button>'
                + "</div></div>"
                + '<div class="EditorGrid">'
                + FieldRowInline("前缀（如「注意：」）", "NoticePrefix", notice.Prefix)
                + SelectInline("所属面板", "NoticePanel", notice.PanelKey, PANEL_LABELS)
                + FieldRowInline("排序值", "NoticeSortOrder", notice.SortOrder, "number")
                + FieldRowInline("链接地址（可留空）", "NoticeLinkUrl", notice.LinkUrl)
                + '<div class="FieldSpanAll"><label class="FieldLabel">内容</label>'
                + '<textarea class="FieldInput" name="NoticeContent" rows="2">'
                + EscapeHtml(notice.Content) + "</textarea></div>"
                + "</div></div>";
        }).join("");
    }

    function NoticeDialog(notice) {
        var record = notice || {
            Id: 0, PanelKey: "RESOURCE", Prefix: "", Content: "", LinkUrl: "", SortOrder: 0
        };

        OpenDialog(notice ? "编辑提示 #" + notice.Id : "新增提示",
            FieldRow("所属面板", "PanelKey", record.PanelKey, "select", PANEL_LABELS)
            + FieldRow("前缀（如「注意：」，可留空）", "Prefix", record.Prefix, "text")
            + FieldRow("内容", "Content", record.Content, "textarea")
            + FieldRow("链接地址（可留空）", "LinkUrl", record.LinkUrl, "text")
            + FieldRow("排序值", "SortOrder", record.SortOrder, "number"),
            function () {
                ApiRequest("/Admin/Api/Notice/Save", "POST", {
                    Id: record.Id,
                    PanelKey: FieldValue("PanelKey"),
                    Prefix: FieldValue("Prefix"),
                    Content: FieldValue("Content"),
                    LinkUrl: FieldValue("LinkUrl"),
                    SortOrder: FieldValue("SortOrder")
                }).then(function () {
                    CloseDialog();
                    Toast("已保存");
                    return LoadOverview();
                }).catch(function (error) { Toast(error.message, true); });
            });
    }

    function SaveNotice(noticeId) {
        var scope = Element("NoticeEditorList").querySelector("[data-notice-id='" + noticeId + "']");

        function Read(name) {
            return scope.querySelector("[name='" + name + "']").value;
        }

        ApiRequest("/Admin/Api/Notice/Save", "POST", {
            Id: noticeId,
            PanelKey: Read("NoticePanel"),
            Prefix: Read("NoticePrefix"),
            Content: Read("NoticeContent"),
            LinkUrl: Read("NoticeLinkUrl"),
            SortOrder: Read("NoticeSortOrder")
        }).then(function () {
            Toast("提示已保存");
            return LoadOverview();
        }).catch(function (error) { Toast(error.message, true); });
    }

    function DeleteNotice(noticeId) {
        if (!window.confirm("确定删除这条提示吗？")) {
            return;
        }
        ApiRequest("/Admin/Api/Notice/Delete", "POST", { Id: noticeId })
            .then(function () {
                Toast("已删除");
                return LoadOverview();
            })
            .catch(function (error) { Toast(error.message, true); });
    }

    /* ---------------------------------------------------------- 站点设置 */

    function RenderSettingsForm() {
        Element("SettingsForm").innerHTML = SETTING_FIELDS.map(function (field) {
            var current = OverviewData.Settings[field.Key] || "";
            var head = '<div><label class="FieldLabel" for="Setting_' + field.Key + '">'
                + EscapeHtml(field.Label) + "</label>";

            if (field.Type === "select") {
                var options = Object.keys(field.Options || {}).map(function (value) {
                    var selected = String(current) === String(value) ? " selected" : "";
                    return '<option value="' + EscapeHtml(value) + '"' + selected + ">"
                        + EscapeHtml(field.Options[value]) + "</option>";
                }).join("");

                return head + '<select class="FieldInput" id="Setting_' + field.Key
                    + '" data-setting-key="' + field.Key + '">' + options + "</select></div>";
            }

            return head + '<input class="FieldInput" id="Setting_' + field.Key + '" data-setting-key="'
                + field.Key + '" type="' + field.Type + '" value="'
                + EscapeHtml(current) + '"' + FieldAttributes(field.Key) + "></div>";
        }).join("");
    }

    function SaveSettings() {
        var mapping = {};
        Array.prototype.forEach.call(
            document.querySelectorAll("[data-setting-key]"),
            function (input) {
                mapping[input.getAttribute("data-setting-key")] = input.value;
            }
        );

        ApiRequest("/Admin/Api/Setting/Save", "POST", { Settings: mapping })
            .then(function () {
                Toast("设置已保存");
                OverviewData.Settings = mapping;
            })
            .catch(function (error) { Toast(error.message, true); });
    }

    /* ---------------------------------------------------------- 两步验证 */

    function RenderTotpStatus(status) {
        var tag = Element("TotpStatusTag");

        tag.textContent = status.IsEnabled ? "已开启" : "未开启";
        tag.className = "Tag " + (status.IsEnabled ? "IsVisible" : "IsHidden");

        Element("TotpSetupArea").hidden = status.IsEnabled;
        Element("TotpManageArea").hidden = !status.IsEnabled;
        Element("TotpQrArea").hidden = true;   // 每次刷新数据都收起二维码，避免长期挂在页面上

        var hint = Element("TotpRecoveryHint");
        if (status.IsEnabled) {
            hint.hidden = false;
            hint.textContent = "剩余可用的恢复码：" + status.UnusedRecoveryCodes
                + " 个。恢复码只在生成时显示一次，用完请及时重新生成。";
        } else {
            hint.hidden = true;
        }
    }

    /** 恢复码只显示一次，用弹窗呈现并要求用户自行保存 */
    function ShowRecoveryCodes(codes) {
        var html = '<p class="SectionHint SectionHintTop">'
            + "以下恢复码<b>只显示这一次</b>，请立刻保存到安全的地方。"
            + "每个码只能使用一次，在验证器不可用时顶替动态码登录。</p>"
            + '<div class="RecoveryCodeGrid">'
            + codes.map(function (code) {
                return '<code class="RecoveryCode">' + EscapeHtml(code) + "</code>";
            }).join("")
            + "</div>"
            + '<button id="CopyRecoveryButton" class="GhostButton" type="button" '
            + 'style="margin-top:16px">复制全部</button>';

        OpenDialog("请保存恢复码", html, CloseDialog, "我已保存，关闭");

        Element("CopyRecoveryButton").addEventListener("click", function () {
            var text = codes.join("\n");
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text)
                    .then(function () { Toast("已复制到剪贴板"); })
                    .catch(function () { Toast("复制失败，请手动记录", true); });
            } else {
                window.prompt("请手动复制以下恢复码：", text);
            }
        });
    }

    Element("TotpSetupButton").addEventListener("click", function () {
        var password = Element("TotpSetupPassword").value;
        if (!password) {
            Toast("请输入当前密码", true);
            return;
        }

        ApiRequest("/Admin/Api/Totp/Setup", "POST", { Password: password })
            .then(function (data) {
                Element("TotpQrBox").innerHTML = data.QrSvg;
                Element("TotpSecretText").textContent = data.Secret;
                Element("TotpSetupPassword").value = "";
                Element("TotpEnableCode").value = "";
                Element("TotpQrArea").hidden = false;
                Element("TotpEnableCode").focus();
                Toast("请用验证器扫描二维码");
            })
            .catch(function (error) { Toast(error.message, true); });
    });

    Element("TotpEnableButton").addEventListener("click", function () {
        ApiRequest("/Admin/Api/Totp/Enable", "POST", {
            Code: Element("TotpEnableCode").value.trim()
        }).then(function (data) {
            ShowRecoveryCodes(data.RecoveryCodes);
            return LoadOverview();
        }).catch(function (error) { Toast(error.message, true); });
    });

    Element("TotpRegenerateButton").addEventListener("click", function () {
        OpenDialog("重新生成恢复码",
            '<p class="SectionHint SectionHintTop">旧的恢复码会立即全部失效。</p>'
            + FieldRow("当前密码", "RegenPassword", "", "password")
            + FieldRow("当前动态码", "RegenCode", "", "text"),
            function () {
                ApiRequest("/Admin/Api/Totp/RegenerateRecoveryCodes", "POST", {
                    Password: FieldValue("RegenPassword"),
                    Code: FieldValue("RegenCode")
                }).then(function (data) {
                    ShowRecoveryCodes(data.RecoveryCodes);
                    return LoadOverview();
                }).catch(function (error) { Toast(error.message, true); });
            },
            "生成");
    });

    Element("TotpDisableButton").addEventListener("click", function () {
        OpenDialog("关闭两步验证",
            '<p class="SectionHint SectionHintTop">'
            + "关闭后登录只需账号密码。请填写当前密码，以及动态码或任意一个未使用的恢复码。</p>"
            + FieldRow("当前密码", "DisablePassword", "", "password")
            + FieldRow("动态码 / 恢复码", "DisableCode", "", "text"),
            function () {
                ApiRequest("/Admin/Api/Totp/Disable", "POST", {
                    Password: FieldValue("DisablePassword"),
                    Code: FieldValue("DisableCode")
                }).then(function () {
                    CloseDialog();
                    Toast("两步验证已关闭");
                    return LoadOverview();
                }).catch(function (error) { Toast(error.message, true); });
            },
            "确认关闭");
    });

    /* ---------------------------------------------------------- 事件委托 */

    Element("AdminMain").addEventListener("click", function (event) {
        var target = event.target.closest("[data-action]");
        if (!target) {
            return;
        }

        var action = target.getAttribute("data-action");
        var id = Number(target.getAttribute("data-id"));

        if (action === "EditLog") { EditLog(id); }
        if (action === "DeleteLog") { DeleteLog(id); }
        if (action === "EditCard") { EditCard(id); }
        if (action === "DeleteCard") { DeleteCard(id); }
        if (action === "SavePanel") { SavePanel(target.getAttribute("data-key")); }
        if (action === "SaveNotice") { SaveNotice(id); }
        if (action === "DeleteNotice") { DeleteNotice(id); }
    });

    Element("LogPanelFilter").addEventListener("change", RenderLogTable);
    Element("NewLogButton").addEventListener("click", function () { EditLog(0); });
    Element("NewCardButton").addEventListener("click", function () { EditCard(0); });
    Element("NewNoticeButton").addEventListener("click", function () { NoticeDialog(null); });
    Element("SaveSettingsButton").addEventListener("click", SaveSettings);

    Element("LogoutButton").addEventListener("click", function () {
        ApiRequest("/Admin/Api/Logout", "POST", {})
            .then(function () { window.location.href = "/Admin/Login"; })
            .catch(function () { window.location.href = "/Admin/Login"; });
    });

    Element("ChangePasswordButton").addEventListener("click", function () {
        var newPassword = Element("NewPassword").value;
        var confirmPassword = Element("ConfirmPassword").value;

        if (newPassword !== confirmPassword) {
            Toast("两次输入的新密码不一致", true);
            return;
        }

        ApiRequest("/Admin/Api/ChangePassword", "POST", {
            OldPassword: Element("OldPassword").value,
            NewPassword: newPassword
        }).then(function () {
            Toast("密码已更新");
            Element("OldPassword").value = "";
            Element("NewPassword").value = "";
            Element("ConfirmPassword").value = "";
        }).catch(function (error) { Toast(error.message, true); });
    });

    /* ---------------------------------------------------------- 数据加载 */

    function LoadOverview() {
        return ApiRequest("/Admin/Api/Overview", "GET").then(function (payload) {
            OverviewData = payload;
            RenderLogTable();
            RenderCardTable();
            RenderPanelEditors();
            RenderNoticeEditors();
            RenderSettingsForm();
            RenderTotpStatus(payload.Totp || { IsEnabled: false, UnusedRecoveryCodes: 0 });
        }).catch(function (error) {
            Toast("加载数据失败：" + error.message, true);
        });
    }

    LoadOverview();
})();