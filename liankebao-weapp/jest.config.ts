import type { Config } from 'jest';

const config: Config = {
  preset: 'ts-jest',
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    // Taro 模块映射到 mock
    '^@tarojs/components$': '<rootDir>/__mocks__/@tarojs/components.js',
    '^@tarojs/taro$': '<rootDir>/__mocks__/@tarojs/taro.js',
    '^@/components/(.*)$': '<rootDir>/src/components/$1',
    '^@/utils/(.*)$': '<rootDir>/src/utils/$1',
    '\\.(css|less|scss|sass)$': '<rootDir>/__mocks__/styleMock.js',
  },
  testMatch: ['**/__tests__/**/*.test.(ts|tsx|js|jsx)'],
  transform: {
    '^.+\\.tsx?$': [
      'ts-jest',
      {
        tsconfig: 'tsconfig.json',
      },
    ],
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json'],
  // 不收集 node_modules 和 dist 的覆盖率
  coveragePathIgnorePatterns: ['/node_modules/', '/dist/'],
};

export default config;
