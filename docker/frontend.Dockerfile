# syntax=docker/dockerfile:1.7

# 依赖安装：默认使用腾讯云 npm 镜像，可通过 --build-arg 覆盖。
FROM node:22-alpine AS deps

ARG NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm config set registry "${NPM_REGISTRY}" \
    && npm ci --no-audit --no-fund

# 构建：API_BASE_URL 在构建期写入 Next.js 反向代理配置。
FROM node:22-alpine AS builder

ARG API_BASE_URL=http://api:8000

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    API_BASE_URL=${API_BASE_URL}

COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./
RUN npm run build

# 运行：仅保留构建产物与运行时依赖。
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json
COPY --from=builder --chown=nextjs:nodejs /app/next.config.ts ./next.config.ts

USER nextjs

EXPOSE 3000

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
