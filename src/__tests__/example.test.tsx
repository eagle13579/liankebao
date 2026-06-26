/**
 * 示例测试文件
 * =============================================================================
 * 此文件演示 React 组件测试的标准模式。
 * 使用 Jest + @testing-library/react。
 *
 * 运行方式：
 *   npx jest src/__tests__/example.test.tsx
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

// ── 测试一个简单的组件 ───────────────────────────────────────────────────

/** 一个简单的问候组件，用于演示测试 */
function Greeting({ name }: { name?: string }) {
  return <h1>你好，{name ?? '世界'}！</h1>;
}

describe('Greeting 组件', () => {
  test('渲染默认问候语', () => {
    render(<Greeting />);
    expect(screen.getByText('你好，世界！')).toBeInTheDocument();
  });

  test('渲染带名字的问候语', () => {
    render(<Greeting name="链客宝" />);
    expect(screen.getByText('你好，链客宝！')).toBeInTheDocument();
  });
});

// ── 测试工具函数 ────────────────────────────────────────────────────────

/** 一个简单的加法函数，用于演示纯函数测试 */
function add(a: number, b: number): number {
  return a + b;
}

describe('工具函数', () => {
  test('add 函数正确求和', () => {
    expect(add(1, 2)).toBe(3);
    expect(add(-1, 1)).toBe(0);
    expect(add(0, 0)).toBe(0);
  });
});
