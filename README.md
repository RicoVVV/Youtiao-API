<div align="center">

![Youtiao API](frontend/public/youtiao.svg)

# Youtiao API

**面向应用与团队的 AI 模型聚合网关**

<p align="center">
  <strong>简体中文</strong> |
  <a href="./README.en.md">English</a>
</p>

<p align="center">
  <a href="#项目简介">项目简介</a> •
  <a href="#功能特性">功能特性</a> •
  <a href="#协议与接口">协议与接口</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#部署">部署</a> •
  <a href="#开发">开发</a> •
  <a href="#使用文档">使用文档</a>
</p>

</div>

---

## 项目简介

Youtiao API 是一个可自托管的 AI 模型聚合网关：用一个 `sk-` 密钥统一接入文本、图像与视频模型，
对外提供一致的兼容接口，并在一个控制台内统一管理路由、鉴权、计费与用量。

它适合在团队内共享已获授权的模型能力、在不改动各客户端配置的前提下切换上游供应商，
或搭建一个带 Web 控制台的私有多云模型服务。上游覆盖 Anthropic（Claude）、Google Gemini、
OpenAI 兼容服务、阿里云 DashScope（千问）、火山方舟（豆包 Seed）、FAL、MiniMax 等。

> [!IMPORTANT]
> - 本项目仅用于合法、已获授权的 AI API 网关、组织级鉴权、多模型管理、用量分析与私有化部署场景。
> - 使用者须合法获取上游 API Key、账号、模型服务与接口权限，并遵守上游服务条款及所在地法律法规。
> - 对外提供生成式 AI 服务时，使用者应自行完成所需的备案、许可、内容安全、实名认证、日志留存与税务等合规义务。

> [!WARNING]
> 将本项目作为面向公众的生成式 AI 服务或 API 转售服务运营前，请先完成所有必需的备案、许可、内容安全、
> 实名认证、日志留存、税务、支付与上游授权义务。

---

## 功能特性

| 能力 | 说明 |
| --- | --- |
| 统一网关 | 一个 API Key 调用全部模型，改一行 `baseURL` 即可接入，兼容 OpenAI SDK |
| 多厂商适配 | 内置 Anthropic、Google Gemini、OpenAI 兼容、阿里云 DashScope（千问）、火山方舟（豆包 Seed）、FAL、MiniMax 等 Provider 适配器 |
| 多协议兼容 | 对外提供 OpenAI（文本 / 图像 / 视频 / 模型列表 / Responses）、Anthropic Messages、Gemini、火山方舟 Responses、DashScope 文本与多模态等协议面 |
| 智能调度与并发 | 多渠道路由、模型名称映射、分组并发限制与高峰分流 |
| 计费与定价 | 按 Token、图片张数、视频时长精确计量，支持定价规则、倍率修正与缓存计费项 |
| 用户与令牌 | 注册登录、令牌分组、Key 粒度的权限与额度管理 |
| 钱包与支付 | 余额、充值、兑换码，支持支付宝官方、易支付（Epay）、Stripe |
| 用量统计 | 调用记录与按日聚合统计，支持按类型、模型、密钥、状态筛选，实时可查 |
| 监控告警 | 分组 / 渠道业务指标与服务器资源监控，支持钉钉机器人 Webhook 告警 |
| 控制台与国际化 | Next.js 管理控制台、模型广场、调用文档与聊天画布，内置中英双语 |

## 协议与接口

| 接口 | 常用端点 |
| --- | --- |
| OpenAI Chat / Responses | `POST /v1/chat/completions`、`POST /v1/responses` |
| OpenAI 模型列表 | `GET /v1/models` |
| Anthropic Messages | `POST /v1/messages` |
| Gemini | `GET /v1beta/models`、`POST /v1beta/models/{model}:generateContent`、`POST /v1beta/models/{model}:streamGenerateContent` |
| OpenAI 图像 | `POST /v1/images/generations`、`POST /v1/images/edits` |
| OpenAI 视频 | `POST /v1/videos`、`GET /v1/videos/{video_id}`、`GET /v1/videos/{video_id}/content` |
| 阿里云 DashScope | `POST /api/v1/services/aigc/text-generation/generation`、`POST /api/v1/services/aigc/multimodal-generation/generation` |
| 火山方舟 Responses | `POST /api/v3/responses` |

对外接口按协议面挂在 `/v1/**`、`/v1beta/**` 与部分 `/api/**` 路径下；平台管理接口位于 `/api/**`。
具体可用能力取决于渠道、上游模型与该协议面的映射关系。

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

### 使用 Docker Compose

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

### 发起第一个请求

1. 在「渠道管理」新建渠道，填写上游地址与 API Key，勾选可用模型与令牌分组，并执行「测试」。
2. 在「模型」中登记对外模型并配置定价，确认用户已有余额或额度。
3. 在「API 密钥」中创建密钥，分组与模型范围需与渠道一致。
4. 将客户端 `baseURL` 设为 `http://localhost:3000/v1`，使用平台签发的 `sk-` 密钥。

把密钥写入环境变量后，先列出可用模型：

```bash
export YOUTIAO_API_KEY=sk-xxxxxxxx
curl --fail-with-body http://localhost:3000/v1/models \
  -H "Authorization: Bearer ${YOUTIAO_API_KEY}"
```

再发起一次对话补全，把 `your-enabled-model` 换成已启用的模型名：

```bash
curl --fail-with-body http://localhost:3000/v1/chat/completions \
  -H "Authorization: Bearer ${YOUTIAO_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"your-enabled-model","messages":[{"role":"user","content":"你好"}]}'
```

## 部署

### Docker Compose（推荐）

[Compose 配置](docker/docker-compose.yml) 默认启动 **Nginx + 前端 + API + PostgreSQL + Redis** 五个服务，
仅 Nginx 对外暴露端口，其余服务仅在内部网络互通。

```bash
cd docker
cp .env.example .env
docker compose up -d --build
docker compose logs -f api
```

### 存储与配置

| 组件 | 选项 |
| --- | --- |
| 主数据库 | PostgreSQL 16 |
| 缓存 | Redis 7（JWT 会话验证缓存；不可用时认证会回源数据库） |
| 媒体存储 | API 容器内 `/app/media` 挂载卷（视频成品与输入素材） |
| 容器平台 | Linux amd64 / arm64 |

| 变量 | 用途 |
| --- | --- |
| `POSTGRES_PASSWORD` | 数据库口令，**必填**，缺失时 compose 直接报错退出 |
| `JWT_SIGNING_KEY` | 访问令牌 HS256 签名密钥，**必填**，非开发环境强制校验强度 |
| `REFRESH_TOKEN_PEPPER` | 刷新令牌摘要盐值，**必填**，非开发环境强制校验强度 |
| `DATABASE_URL` | 数据库连接串；Compose 部署时由 `POSTGRES_*` 自动拼接注入 |
| `AUTH_REDIS_URL` | Redis 连接地址，仅用于会话验证缓存 |
| `PAYMENT_CONFIG_ENCRYPTION_KEY` | 支付凭据加密密钥（Fernet），仅在启用支付时需要 |
| `PUBLIC_BASE_URL` | 对外公开地址，用于生成成品下载等绝对地址 |
| `FRONTEND_PORT` | Nginx 对外端口，默认 `3000` |
| `APP_ENV` | 运行环境；非 `development` 会强制校验密钥强度 |

完整的变量说明与默认值见 [docker/.env.example](docker/.env.example)、
[backend/.env.example](backend/.env.example) 与 [backend/app/core/config.py](backend/app/core/config.py)。

### 安全须知

- **不要把 `.env` 提交到仓库**：`.gitignore` 已忽略 `.env`、`docker/.env` 等文件。
- **密钥由环境注入**：数据库口令、JWT 密钥、支付加密密钥均不写死在代码中，请通过环境变量提供。
- **JWT_SIGNING_KEY / REFRESH_TOKEN_PEPPER** 泄露将导致令牌可被伪造，请使用足够长度的随机值并妥善保管。
- **PAYMENT_CONFIG_ENCRYPTION_KEY** 用于加密支付凭据（Fernet），生成方式：
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。
  更换该密钥会导致已存支付凭据无法解密。

## 开发

后端使用 Python ≥ 3.11 与 FastAPI，前端使用 Next.js（App Router）与 React。

### 后端（需本地 PostgreSQL；Redis 可选）

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # 至少配置 DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

开发环境下后端自带交互式文档：`http://localhost:8000/api/docs`（生产环境默认关闭）。

### 前端

```bash
cd frontend
npm install
# 新建 .env.local 并设置 API_BASE_URL=http://localhost:8000
# （Next.js rewrites 会据此把 /api 代理到后端）
npm run dev
```

访问 `http://localhost:3000`。

| 位置 | 职责 |
| --- | --- |
| [backend/app/bootstrap](backend/app/bootstrap) | 应用装配：路由注册、中间件、生命周期 |
| [backend/app/core](backend/app/core) | 配置、鉴权、数据库、日志、错误与协议注册表 |
| [backend/app/modules](backend/app/modules) | 领域模块与上游 Provider 适配器 |
| [backend/app/web](backend/app/web) | 请求上下文、统一响应与流式封装 |
| [frontend/app](frontend/app) | 页面路由（首页、模型广场、文档、控制台、系统设置） |
| [frontend/components](frontend/components) | UI 与业务组件 |
| [docker](docker) | Dockerfile、Compose、Nginx 配置与部署环境变量模板 |

后端测试与检查：

```bash
cd backend
pytest
ruff check .
```

## 使用文档

| 资源 | 链接 |
| --- | --- |
| 开发环境 API 文档 | `http://localhost:8000/api/docs` |

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
