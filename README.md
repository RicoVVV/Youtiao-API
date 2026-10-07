# Youtiao API

[English](README.en.md) | **简体中文**

Youtiao API 是一个开源的 AI 模型聚合网关：用一个 `sk-` 密钥统一接入文本、图像与视频模型，
提供多厂商协议适配、按量计费、钱包支付、用量统计、监控告警与完整的管理控制台。

## 功能特性

- **统一网关**：一个 API Key 调用全部模型，改一行 `baseURL` 即可接入，兼容 OpenAI SDK。
- **多厂商适配**：内置 Anthropic（Claude）、Google Gemini、OpenAI 兼容、阿里云 DashScope（千问）、火山方舟（豆包 Seed）、FAL、MiniMax 等 Provider 适配器。
- **多协议兼容**：对外提供 OpenAI（文本 / 图像 / 视频 / 模型列表 / Responses）、Anthropic Messages、Gemini、火山方舟 Responses、DashScope 文本与多模态等协议面。
- **智能调度与并发控制**：多渠道路由、模型映射、分组并发限制与高峰分流。
- **计费与定价**：按 Token、图片张数、视频时长精确计量，支持定价规则、倍率与缓存计费项。
- **用户与令牌体系**：注册登录、令牌分组、Key 粒度权限与额度管理。
- **钱包与支付**：余额、充值、兑换码，支持支付宝官方、易支付、Stripe。
- **用量统计**：调用记录与按日聚合统计，实时可查。
- **监控告警**：分组业务指标与服务器资源监控，支持钉钉机器人 Webhook 告警。
- **控制台与国际化**：Next.js 管理控制台 / 模型广场 / 调用文档，内置中英双语。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python ≥ 3.11、FastAPI、SQLAlchemy / SQLModel、Alembic、Pydantic v2 |
| 数据库 / 缓存 | PostgreSQL 16、Redis 7 |
| 前端 | Next.js 16（App Router）、React 19、TypeScript、Tailwind CSS v4、Radix UI、i18next |
| 部署 | Docker、Docker Compose、Nginx、Gunicorn + Uvicorn |

## 架构概览

```
                    ┌───────────────┐
   浏览器 / SDK ───▶ │  Nginx :80    │
                    └───────┬───────┘
             /（页面）│                │ /api、/v1、/v1beta（接口）
                    ▼                ▼
            ┌───────────────┐  ┌───────────────┐
            │ Frontend      │  │ API（FastAPI）│
            │ Next.js :3000 │  │ Gunicorn :8000│
            └───────────────┘  └───────┬───────┘
                                      ▼
                          ┌───────────────────────┐
                          │ PostgreSQL  /  Redis  │
                          └───────────────────────┘
                                      ▼
                     上游 Provider（Anthropic / Gemini / OpenAI / 千问 / 豆包 / FAL / MiniMax …）
```

Nginx 是唯一对外入口：页面路由转发到前端，`/api`、`/v1`、`/v1beta` 直接转发到后端，
并对流式接口关闭响应缓冲与 gzip。

## 目录结构

```
Youtiao-API/
├── backend/          FastAPI 服务
│   ├── app/
│   │   ├── bootstrap/      应用装配（路由、中间件、生命周期）
│   │   ├── core/           配置、鉴权、数据库、日志、错误、协议注册
│   │   ├── infrastructure/ HTTP、Redis、系统指标
│   │   ├── modules/        领域模块（详见下）
│   │   └── web/            请求上下文、响应与流式封装
│   ├── alembic/            数据库迁移
│   └── tests/              测试
├── frontend/         Next.js 官网与控制台
│   ├── app/[locale]/       页面路由（首页、模型广场、文档、控制台、系统设置）
│   ├── components/         UI 与业务组件
│   └── i18n/               中英文案
├── docker/           Dockerfile、docker-compose.yml、Nginx 配置与部署环境变量模板
├── LICENSE
├── README.md
└── README.en.md
```

后端领域模块：`admin`（管理接口）、`user`（认证 / 令牌 / 用户）、`channels`（渠道与路由）、
`providers`（上游适配器）、`generation`（文本 / 图像生成）、`video`（异步视频任务）、
`pricing` 与 `billing`（定价与计费）、`wallet` 与 `payment`（钱包与支付）、`usage`（用量统计）、
`monitoring`（监控告警）、`marketplace` 与 `model_catalog`（模型广场与自动匹配）、
`system_settings` 与 `system_tasks`（系统设置与定时任务调度）。

## 快速开始

### 方式一：Docker Compose（推荐）

需要已安装 Docker 与 Docker Compose。

```bash
cd docker
cp .env.example .env
# 编辑 .env，至少填写以下三项（缺省会直接启动报错）：
#   POSTGRES_PASSWORD      数据库口令
#   JWT_SIGNING_KEY        至少 32 位随机字符串
#   REFRESH_TOKEN_PEPPER   另一个至少 32 位随机字符串
docker compose up -d --build
```

启动完成后访问 `http://localhost:3000`（可通过 `FRONTEND_PORT` 修改端口）。
首次访问会引导你在 `/setup` 创建管理员账号。

### 方式二：本地开发

后端（需本地 PostgreSQL；Redis 可选，用于会话缓存，不可用时会回源数据库）：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # 至少配置 DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm install
# 新建 .env.local 并设置 API_BASE_URL=http://localhost:8000
# （Next.js rewrites 会据此把 /api 代理到后端）
npm run dev
```

访问 `http://localhost:3000`。

## 配置说明

| 文件 | 用途 |
| --- | --- |
| [docker/.env.example](docker/.env.example) | Docker Compose 部署，复制为 `docker/.env` |
| [backend/.env.example](backend/.env.example) | 本机直接运行后端，复制为 `backend/.env` |

仅 `DATABASE_URL` 为后端必填项，其余变量均有代码默认值（见
[backend/app/core/config.py](backend/app/core/config.py)）。非 `development` 环境会强制校验
JWT 密钥与刷新令牌 Pepper 的强度。

## 安全须知

- **不要把 `.env` 提交到仓库**：`.gitignore` 已忽略 `.env`、`docker/.env` 等文件。
- **密钥由环境注入**：数据库口令、JWT 密钥、支付加密密钥均不写死在代码中，请通过环境变量提供。
- **JWT_SIGNING_KEY / REFRESH_TOKEN_PEPPER** 泄露将导致令牌可被伪造，请使用足够长度的随机值并妥善保管。
- **PAYMENT_CONFIG_ENCRYPTION_KEY** 用于加密支付凭据（Fernet），生成方式：
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。更换该密钥会导致已存支付凭据无法解密。

## API 兼容面

对外接口按协议面挂在以下路径（由 Nginx 直连后端）：

- `/v1/**`、`/v1beta/**`：面向客户端 SDK 的兼容接口（OpenAI / Anthropic / Gemini / 火山方舟 / DashScope 等协议）。
- `/api/**`：平台管理面接口，以及千问、方舟等厂商原生面接口。

开发环境下后端自带交互式文档：`http://localhost:8000/api/docs`（生产环境默认关闭）。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
