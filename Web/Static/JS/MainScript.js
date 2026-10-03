/* ==========================================================================
   鼠鼠娱乐中心 —— 首页交互

   1. 深浅色切换（主题已在 <head> 的内联脚本里定好，这里只管切换）
   2. 服务卡片的指针跟随 3D 倾斜 + 高光
   3. 背景光斑视差

   2 和 3 都属于锦上添花，在「减少动态效果」或触屏设备上直接跳过，
   任何一个模块出错都不该影响页面本身的可用性。
   ========================================================================== */

(function () {
    "use strict";

    var themeToggle = document.getElementById("ThemeToggle");
    var backdropGlow = document.getElementById("BackdropGlow");

    var prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    var hasFinePointer = window.matchMedia("(hover: hover) and (pointer: fine)");

    /* ---------------------------------------------------------- 主题切换 */

    // 主题的解析与切换都在 ThemeBoot.js 里，这里只负责接线
    if (themeToggle && window.ShuShuTheme) {
        themeToggle.addEventListener("click", function () {
            window.ShuShuTheme.Toggle();
        });
    }

    /* ---------------------------------------------------------- 3D 倾斜 */

    var TILT_RANGE_DEGREES = 5;

    function InitializeCardTilt() {
        // 触屏没有真正的指针悬停，静止的倾斜会显得莫名其妙
        if (!hasFinePointer.matches || prefersReducedMotion.matches) {
            return;
        }

        var cards = document.querySelectorAll(".ServiceCard");
        var tiltCards = [];

        Array.prototype.forEach.call(cards, function (card) {
            var pendingFrame = null;
            var nextEvent = null;

            // 指针离开文档、窗口失焦或切到别的标签页时，
            // pointerleave 不一定触发，卡片会永久卡在倾斜 + 高亮边框的状态。
            // 统一登记一个复位函数，由下面的事件兜底调用。
            function Reset() {
                card.classList.remove("IsTilting");
                card.style.setProperty("--TiltX", "0deg");
                card.style.setProperty("--TiltY", "0deg");
                card.style.setProperty("--PointerX", "50%");
                card.style.setProperty("--PointerY", "50%");
            }

            tiltCards.push(Reset);

            function Render() {
                pendingFrame = null;
                if (!nextEvent) {
                    return;
                }

                var rect = card.getBoundingClientRect();
                if (!rect.width || !rect.height) {
                    return;
                }

                // 归一化到 0..1，中心为 0.5
                var ratioX = (nextEvent.clientX - rect.left) / rect.width;
                var ratioY = (nextEvent.clientY - rect.top) / rect.height;

                // 往指针方向翻，Y 轴取反才符合直觉
                var rotateX = (0.5 - ratioY) * TILT_RANGE_DEGREES * 2;
                var rotateY = (ratioX - 0.5) * TILT_RANGE_DEGREES * 2;

                card.style.setProperty("--TiltX", rotateX.toFixed(2) + "deg");
                card.style.setProperty("--TiltY", rotateY.toFixed(2) + "deg");
                card.style.setProperty("--PointerX", (ratioX * 100).toFixed(1) + "%");
                card.style.setProperty("--PointerY", (ratioY * 100).toFixed(1) + "%");
            }

            card.addEventListener("pointerenter", function () {
                card.classList.add("IsTilting");
            });

            card.addEventListener("pointermove", function (event) {
                if (event.pointerType !== "mouse") {
                    return;
                }
                nextEvent = event;
                if (pendingFrame === null) {
                    pendingFrame = window.requestAnimationFrame(Render);
                }
            });

            card.addEventListener("pointerleave", Reset);
        });

        // 兜底：指针离开文档 / 窗口失焦 / 切标签页时，把所有卡片复位
        function ResetAllCards() {
            tiltCards.forEach(function (Reset) { Reset(); });
        }

        document.addEventListener("pointerleave", ResetAllCards);
        window.addEventListener("blur", ResetAllCards);
        document.addEventListener("visibilitychange", function () {
            if (document.hidden) {
                ResetAllCards();
            }
        });
    }

    /* ---------------------------------------------------------- 背景视差 */

    var PARALLAX_RANGE_PIXELS = 16;

    function InitializeBackdropParallax() {
        if (!backdropGlow) {
            return;                 // 用自定义壁纸时没有这一层
        }
        if (!hasFinePointer.matches || prefersReducedMotion.matches) {
            return;
        }

        var pendingFrame = null;
        var nextEvent = null;

        function Render() {
            pendingFrame = null;
            if (!nextEvent) {
                return;
            }

            var ratioX = nextEvent.clientX / window.innerWidth - 0.5;
            var ratioY = nextEvent.clientY / window.innerHeight - 0.5;

            backdropGlow.style.setProperty(
                "--ParallaxX", (ratioX * PARALLAX_RANGE_PIXELS).toFixed(1) + "px"
            );
            backdropGlow.style.setProperty(
                "--ParallaxY", (ratioY * PARALLAX_RANGE_PIXELS).toFixed(1) + "px"
            );
        }

        document.addEventListener("pointermove", function (event) {
            if (event.pointerType !== "mouse") {
                return;
            }
            nextEvent = event;
            if (pendingFrame === null) {
                pendingFrame = window.requestAnimationFrame(Render);
            }
        }, { passive: true });
    }

    /* ---------------------------------------------------------- 启动 */

    function StartEnhancements() {
        InitializeCardTilt();
        InitializeBackdropParallax();
    }

    // 首屏渲染完再挂 3D，避免和布局计算抢时间
    if (window.requestAnimationFrame) {
        window.requestAnimationFrame(function () {
            window.requestAnimationFrame(StartEnhancements);
        });
    } else {
        StartEnhancements();
    }

    // 系统「减少动态效果」中途被打开时不用重载：CSS 里的
    // @media (prefers-reduced-motion: reduce) 已经把 transform 强制关掉了。
})();