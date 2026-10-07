# Youtiao API 前端

Youtiao API 的官网与管理控制台前端，基于 Next.js（App Router）+ React + TypeScript + Tailwind CSS。
完整的项目介绍、整体架构与部署方式见仓库根目录的 [README](../README.md)。

## 本地开发

```bash
npm install
# 新建 .env.local 并指向后端地址（next.config.ts 的 rewrites 依赖该变量把 /api 代理到后端）
# API_BASE_URL=http://localhost:8000
npm run dev
```

启动后访问 http://localhost:3000 。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 启动开发服务器 |
| `npm run build` | 生产构建 |
| `npm run start` | 启动生产服务 |
| `npm run lint` | ESLint 检查 |

## 目录概览

- `app/[locale]/`：页面路由（首页、模型广场、调用文档、登录、控制台、系统设置），内置中英双语。
- `components/`：UI 与业务组件（控制台各面板、聊天画布、监控、支付网关等）。
- `i18n/`：中英文案与 i18n 配置。
- `lib/`：请求封装与业务 API 客户端。
