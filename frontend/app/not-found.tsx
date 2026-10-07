import Link from "next/link";

export default function NotFound() {
  return (
    <html lang="zh-CN">
      <body style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100vh", fontFamily: "sans-serif" }}>
        <h1>404 — 页面不存在</h1>
        <p>您访问的页面不存在。</p>
        <Link href="/zh" style={{ color: "#4c6fff" }}>返回首页</Link>
      </body>
    </html>
  );
}
