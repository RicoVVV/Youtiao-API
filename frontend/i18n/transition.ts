/** 语言切换过渡遮罩：交叉淡化，避免新页面渲染/资源加载期间的内容闪烁 */

const OVERLAY_ID = "locale-transition-overlay";
const FADE_MS = 200;

/** 切换开始时：全屏遮罩淡入，盖住旧语言内容 */
export function beginLocaleTransition() {
  if (typeof document === "undefined") return;
  if (document.getElementById(OVERLAY_ID)) return;
  const el = document.createElement("div");
  el.id = OVERLAY_ID;
  el.className =
    "pointer-events-none fixed inset-0 z-[9999] bg-background opacity-0 transition-opacity duration-200";
  document.body.appendChild(el);
  requestAnimationFrame(() => {
    el.classList.remove("opacity-0");
    el.classList.add("opacity-100");
  });
}

/** 新语言页面就绪后：遮罩淡出并移除 */
export function endLocaleTransition() {
  if (typeof document === "undefined") return;
  const el = document.getElementById(OVERLAY_ID);
  if (!el) return;
  el.classList.remove("opacity-100");
  el.classList.add("opacity-0");
  setTimeout(() => el.remove(), FADE_MS);
}
