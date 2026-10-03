/* ==========================================================================
   主题启动脚本 —— 必须在 <head> 里同步加载

   在首屏绘制前把 data-theme 定成 light / dark 两种终态之一，
   CSS 因此只需要处理这两种情况，不必把深色变量写两遍，也不会闪白。

   首页、后台、登录页三处共用这一份。切换按钮调用 window.ShuShuTheme.Toggle()。
   ========================================================================== */

(function () {
    "use strict";

    var STORAGE_KEY = "ShuShuTheme";
    var root = document.documentElement;

    var saved = null;
    try {
        saved = window.localStorage.getItem(STORAGE_KEY);
    } catch (error) {
        saved = null;   // 隐私模式下读不到，退回站点默认值
    }

    // 优先级：用户手动选择 > 站点默认主题 > 跟随系统
    var theme = saved || root.getAttribute("data-theme") || "auto";
    if (theme === "auto") {
        theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    root.setAttribute("data-theme", theme);

    function SyncThemeColor() {
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.setAttribute(
                "content",
                root.getAttribute("data-theme") === "dark" ? "#000000" : "#F5F5F7"
            );
        }
    }

    SyncThemeColor();

    // 用户没手动选过，就跟着系统走
    if (!saved) {
        var query = window.matchMedia("(prefers-color-scheme: dark)");
        var OnSystemThemeChange = function (event) {
            root.setAttribute("data-theme", event.matches ? "dark" : "light");
            SyncThemeColor();
        };

        if (query.addEventListener) {
            query.addEventListener("change", OnSystemThemeChange);
        } else if (query.addListener) {
            query.addListener(OnSystemThemeChange);
        }
    }

    window.ShuShuTheme = {
        Toggle: function () {
            var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
            root.setAttribute("data-theme", next);
            SyncThemeColor();
            try {
                window.localStorage.setItem(STORAGE_KEY, next);
            } catch (error) {
                /* 写不进去也不影响本次使用 */
            }
            return next;
        }
    };
})();