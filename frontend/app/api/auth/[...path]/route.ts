/**
 * 手动代理 /api/auth/* 到后端，确保 Set-Cookie / Cookie 在同源环境下正确传递。
 *
 * Next.js rewrite 有时会丢失 HttpOnly Cookie（Set-Cookie 头未透传到浏览器），
 * 此 Route Handler 在 Node 层手动转发，浏览器看到的始终是同源请求，
 * SameSite=Lax 可正常工作。
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.API_BASE_URL;

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const target = `${BACKEND}/api/auth/${path.join("/")}${req.nextUrl.search}`;

  // 转发原始请求头（去掉 host，后端不需要）
  const headers = new Headers(req.headers);
  headers.delete("host");

  const init: RequestInit = { method: req.method, headers };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  const res = await fetch(target, init);

  // 构造响应，手动处理 Set-Cookie（NextResponse 会正确合并同名头）
  const response = new NextResponse(res.body, {
    status: res.status,
    statusText: res.statusText,
  });

  res.headers.forEach((value, key) => {
    if (key.toLowerCase() === "set-cookie") {
      response.headers.append("Set-Cookie", value);
    } else {
      response.headers.set(key, value);
    }
  });

  return response;
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE, proxy as PATCH };
