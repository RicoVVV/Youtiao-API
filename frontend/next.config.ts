import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 隐藏开发模式 DevTools 悬浮按钮
  devIndicators: false,
  // 允许局域网/预览代理访问 dev 资源。
  // 具体来源不写死在仓库中，而是通过环境变量 ALLOWED_DEV_ORIGINS 注入（逗号分隔，例如
  // ALLOWED_DEV_ORIGINS=192.168.1.10,10.0.0.5）；未配置时为空数组，仅允许默认本地来源。
  allowedDevOrigins:
    process.env.ALLOWED_DEV_ORIGINS?.split(",")
      .map((origin) => origin.trim())
      .filter(Boolean) ?? [],
  async rewrites() {
    return [
      {
        // 排除 /api/auth/*（由 app/api/auth/... 手动代理，确保 Cookie 正确传递）
        source: "/api/:path((?!auth/).*)",
        destination: `${process.env.API_BASE_URL}/api/:path`,
      },
    ];
  },
};

export default nextConfig;
