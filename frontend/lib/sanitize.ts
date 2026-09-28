"use client";

import DOMPurify from "dompurify";

/** 净化后端返回的原始 HTML 内容，防 XSS（文档要求展示前完成净化） */
export function sanitizeHtml(html: string): string {
  if (!html) return "";
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ["target", "rel"],
  });
}
