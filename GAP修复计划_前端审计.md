# 链客宝AI前端 GAP 修复计划（审计结果）

审计时间: 2026-05-27
审计范围: liankebao-weapp/ (Taro), liankebao-miniapp/ (原生微信小程序)

---

## 审计发现

| # | GAP | 当前状态 | 严重程度 |
|:-:|:----|:---------|:--------:|
| GAP-1 | **前端零测试** | 两个前端项目均无任何测试文件、无测试框架依赖、无测试脚本 | 🔴 严重 |
| GAP-2 | **TypeScript strict 配置** | tsconfig.json 中 `strict: true` 已开启（原始 GAP 假设已过时） | 🟢 已满足 |
| GAP-3 | **页面 vs API 覆盖率差距** | 11 个前端页面/组件 vs 59 条后端 API 路由，覆盖比 ~1:5.4 | 🟡 中等 |
| GAP-4 | **缺失测试基础设施** | `package.json` 的 devDependencies 不含任何测试框架 (jest/vitest等) | 🔴 严重 |
| GAP-5 | **liankebao-miniapp (原生小程序)** | 15 个页面，无 TypeScript 支持（纯 JS），无测试 | 🟡 中等 |

---

## 修复计划

| GAP | 当前状态 | 修复方案 | 预计工时 |
|:----|:---------|:---------|:--------:|
| **GAP-1: 前端零测试** | `liankebao-weapp/src/` 无任何 `__tests__/` 目录、`.test.ts` 或 `.spec.ts` 文件；`liankebao-miniapp/` 同理 | **liankebao-weapp (Taro):** 引入 Jest + Taro 测试工具链 `@tarojs/mini-runner` 或 `@tarojs/test-utils`，在 `src/` 下按模块建立 `__tests__/` 目录。优先级: (1) API client (`src/api/client.ts`) 单元测试 → (2) 核心组件 (`ProductCard`) 组件测试 → (3) 各页面逻辑测试。**liankebao-miniapp (原生):** 使用微信小程序官方测试工具 `miniprogram-simulate` + Jest，按页面建立测试 | 8-12 人天 |
| **GAP-2: TypeScript strict** | `tsconfig.json` 中已有 `"strict": true`，同时有 `"skipLibCheck": true` | ✅ 已满足，无需修改。可通过编译检查确认当前代码在 strict 模式下零错误：`npx tsc --noEmit` | 0（仅验证） |
| **GAP-3: 页面覆盖率不足** | weapp 11 个页面组件 vs 59 条后端 API（routers/ 下 13 个路由文件），覆盖率比约 19% | 按业务模块对标: (1) 确认 weapp 当前页面覆盖的后端 API 清单；(2) 根据后端 routers/ 清单补充缺失页面（如: needs 供需匹配、promoter 推广、activities 活动、admin 管理后台）；(3) 优先补充核心业务路径（订单/支付/供需）对应的页面 | 5-8 人天 |
| **GAP-4: 缺失测试基础设施** | `package.json` devDependencies 只有 `@tarojs/cli`、`@types/react`、`typescript`；无测试框架 | 在 `liankebao-weapp/package.json` 中增加: `jest`, `@types/jest`, `ts-jest`, `@tarojs/test-utils`（或 `@testing-library/react` + `jest-environment-jsdom`）；创建 `jest.config.ts`；在 scripts 中增加 `"test": "jest"`, `"test:coverage": "jest --coverage"`；并配置 CI 门禁确保测试通过方可合并 | 2-3 人天 |
| **GAP-5: liankebao-miniapp 原生小程序** | 15 个页面，纯 JS + WXML/WXSS，无 TS、无测试 | **方案 A（推荐）：** 逐步迁移至 Taro 统一技术栈，复用 weapp 的测试基础设施。**方案 B（短期）：** 保留原生，增加 `miniprogram-simulate` + Jest 测试，关键页面（login/orders/product）先行 | 方案 A: 15-20 人天 方案 B: 5-8 人天 |

---

## 建议优先级排序

1. **P0 (本轮必须修):** GAP-4 测试基础设施 → GAP-1 核心模块单元测试 (API client + ProductCard 组件)
2. **P1 (高优先级):** GAP-3 页面覆盖率补齐（needs 供需匹配页面、支付流程页面）
3. **P2 (优化项):** GAP-5 liankebao-miniapp 测试覆盖或技术栈统一

## 补充说明

- **tsconfig.json 误报:** 原始 GAP 清单中 `strict: false` 的结论与当前代码不符（当前为 `strict: true`），建议在 GAP 清单中更新此条目为「已关闭」
- **代码量估算:** liankebao-weapp/src/ 共 33 个文件（含 scss），核心逻辑 11 个 TSX 页面组件 + 1 个 API client + 1 个通用组件，测试编写工作量可控
