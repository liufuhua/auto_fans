# Web Admin

抖音自动化测试管理后台，使用 `Vue 3 + Vite + TypeScript + Element Plus` 开发。

## 环境变量

复制 `.env.example` 为 `.env.local` 后按需调整：

```bash
cp .env.example .env.local
```

默认使用 mock 数据：

```text
VITE_API_BASE_URL=/api
VITE_USE_MOCK_API=true
VITE_USE_MOCK_AUTH=true
```

后端 API 完成后可切换为真实接口：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_USE_MOCK_API=false
VITE_USE_MOCK_AUTH=false
```

## 常用命令

```bash
npm install
npm run dev
npm run typecheck
npm run lint
npm run format:check
npm run build
```

## 工程质量

- TypeScript 类型检查：`npm run typecheck`
- ESLint：`npm run lint`
- Prettier 格式检查：`npm run format:check`
- 生产构建验证：`npm run build`

API 路径集中维护在 `src/api/endpoints.ts`，业务请求封装在 `src/api/request.ts`。
