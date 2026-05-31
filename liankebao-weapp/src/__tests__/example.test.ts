/**
 * 链客宝前端示例测试
 *
 * 验证 Jest 测试框架基础设施正常工作
 */

describe('测试框架', () => {
  it('Jest 环境正常运行', () => {
    expect(1 + 1).toBe(2);
  });

  it('支持异步测试', async () => {
    const result = await Promise.resolve(42);
    expect(result).toBe(42);
  });

  it('支持 TypeScript', () => {
    const greet = (name: string): string => `Hello, ${name}!`;
    expect(greet('链客宝')).toBe('Hello, 链客宝!');
  });
});
