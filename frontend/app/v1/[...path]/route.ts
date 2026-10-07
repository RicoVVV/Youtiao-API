/**
 * 手动代理 /v1/* 到后端 OpenAI 兼容调用面。
 *
 * 替代 next.config.ts 的 rewrite：Next dev 代理对慢请求有 ~30s 默认超时，
 * 图像/视频生成等长耗时接口会在 30s 时被截断。
 * 此 Route Handler 在 Node 层直接转发，不缓冲、支持 SSE/流式响应逐块透传，
 * 且不受 Next dev 代理默认超时限制。
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.API_BASE_URL;

/** 上游读取超时：覆盖图像/视频等慢生成场景（毫秒） */
const UPSTREAM_TIMEOUT_MS = 300_000;

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  // /v1/* 走调用面；/v1/admin/* 走管理面（路径中第一个 segment 为 admin 时剥离）
  const isAdmin = path[0] === "admin";
  const targetPath = isAdmin ? path.slice(1).join("/") : path.join("/");
  const target = isAdmin
    ? `${BACKEND}/api/${targetPath}${req.nextUrl.search}`
    : `${BACKEND}/v1/${targetPath}${req.nextUrl.search}`;

  // 转发原始请求头（去掉 host，后端不需要）
  const headers = new Headers(req.headers);
  headers.delete("host");

  const init: RequestInit = {
    method: req.method,
    headers,
    // @ts-expect-error Node fetch 需要 duplex 才能转发流式 body
    duplex: "half",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    // 直接透传 body 流（支持 multipart/FormData 与 SSE 请求体），不读为 text
    init.body = req.body;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(target, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }

  // 直接透传响应体流（SSE 逐块下发，不缓冲），复制全部响应头
  const response = new NextResponse(res.body, {
    status: res.status,
    statusText: res.statusText,
  });
  res.headers.forEach((value, key) => {
    // content-length 在流式/分块时可能不准，交由 Next 重新计算
    if (key.toLowerCase() === "content-length") return;
    response.headers.set(key, value);
  });

  return response;
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE, proxy as PATCH };
