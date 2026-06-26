/**
 * 链客宝 前端测试配置 — Jest + React Testing Library + TypeScript
 * =============================================================================
 * 本配置文件为 React/TypeScript 前端项目提供标准的单元测试基础设施。
 *
 * 测试文件命名约定：
 *   - src/**/__tests__/**/*.{ts,tsx}
 *   - src/**/*.{test,spec}.{ts,tsx}
 *
 * 运行方式：
 *   npx jest                 # 运行所有测试
 *   npx jest --watch         # 监听模式
 *   npx jest --coverage      # 带覆盖率报告
 * =============================================================================
 */

/** @type {import('jest').Config} */
module.exports = {
  // ── 基础环境 ──────────────────────────────────────────────────────────────
  testEnvironment: 'jsdom',

  // ── 根目录 ────────────────────────────────────────────────────────────────
  roots: ['<rootDir>/src'],

  // ── 测试文件匹配 ──────────────────────────────────────────────────────────
  testMatch: [
    '**/__tests__/**/*.{ts,tsx}',
    '**/*.{test,spec}.{ts,tsx}',
  ],

  // ── 模块解析 ──────────────────────────────────────────────────────────────
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],

  moduleNameMapper: {
    // 支持 @/ 路径别名 → src/
    '^@/(.*)$': '<rootDir>/src/$1',
    // CSS/样式模块 mock
    '\\.(css|less|scss|sass)$': 'identity-obj-proxy',
    // 静态资源 mock
    '\\.(jpg|jpeg|png|gif|webp|svg)$': '<rootDir>/__mocks__/fileMock.js',
  },

  // ── 转换器 ────────────────────────────────────────────────────────────────
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {
      tsconfig: '<rootDir>/tsconfig.json',
    }],
  },

  // ── 覆盖率 ────────────────────────────────────────────────────────────────
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/__tests__/**',
    '!src/**/*.{test,spec}.{ts,tsx}',
  ],

  coverageDirectory: '<rootDir>/coverage',

  coverageReporters: ['text', 'lcov', 'clover', 'html'],

  // ── 测试前设置 ────────────────────────────────────────────────────────────
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],

  // ── 其他 ──────────────────────────────────────────────────────────────────
  clearMocks: true,
  errorOnDeprecated: true,
  maxWorkers: '50%',
};
