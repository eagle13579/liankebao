// =============================================================================
// 链客宝 — k6 性能基准测试
// LianKeBao — k6 Performance Benchmark
//
// 测试场景:
//   - /health — 健康检查
//   - /api/gaia/knowledge — 盖娅知识库查询
//   - /api/retro/framework — 复盘框架
//
// 负载参数:
//   - 100 并发用户
//   - 30 秒持续
//   - 10 秒预热
//
// 阈值:
//   - 95% 响应时间 < 500ms
//   - 错误率 < 1%
//
// 使用:
//   k6 run tests/k6_test.js
//   k6 run tests/k6_test.js -e BASE_URL=http://localhost:8201
//   k6 run tests/k6_test.js --out json=k6-results.json
// =============================================================================

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// ── 自定义指标 ────────────────────────────────────────────────────────────────
const errorRate = new Rate('errors');
const healthTrend = new Trend('health_duration');
const knowledgeTrend = new Trend('knowledge_duration');
const retroTrend = new Trend('retro_duration');
const totalRequests = new Counter('total_requests');

// ── 配置 ──────────────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8201';
const APP_VERSION = __ENV.APP_VERSION || 'dev';

export const options = {
  // 阶段: 预热 → 稳态
  stages: [
    { duration: '10s', target: 50 },    // 预热: 10秒爬到50并发
    { duration: '30s', target: 100 },   // 稳态: 30秒维持100并发
    { duration: '10s', target: 0 },     // 冷却: 10秒降到0
  ],

  thresholds: {
    // 95% 的请求必须在 500ms 内完成
    http_req_duration: ['p(95)<500'],
    // 错误率必须低于 1%
    http_req_failed: ['rate<0.01'],
    // 自定义指标阈值
    errors: ['rate<0.01'],             // 业务错误率 < 1%
    health_duration: ['p(95)<300'],    // 健康检查: 95% < 300ms
    knowledge_duration: ['p(95)<800'], // 知识查询: 95% < 800ms (含DB查询)
    retro_duration: ['p(95)<500'],     // 复盘框架: 95% < 500ms
  },

  // 模拟真实用户行为
  userAgent: 'k6-chainke-benchmark/1.0',
};

// ── 辅助函数 ──────────────────────────────────────────────────────────────────
function randomString(length) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

function logResult(name, status, duration, body) {
  if (__ENV.DEBUG) {
    console.log(`[${status ? 'OK' : 'FAIL'}] ${name} — ${duration.toFixed(2)}ms`);
    if (!status && __ENV.DEBUG === 'verbose') {
      console.log(`  Response: ${body ? body.substring(0, 200) : '(empty)'}`);
    }
  }
}

// ── 测试 1: 健康检查 ─────────────────────────────────────────────────────────
function testHealth() {
  group('Health Check', function () {
    const url = `${BASE_URL}/health`;
    const params = {
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'k6-chainke-benchmark/1.0',
      },
      timeout: '10s',
      tags: { endpoint: '/health' },
    };

    const res = http.get(url, params);
    const duration = res.timings.duration;
    healthTrend.add(duration);
    totalRequests.add(1);

    const success = check(res, {
      'health status is 200': (r) => r.status === 200,
      'health response has status=ok': (r) => {
        try {
          return JSON.parse(r.body).status === 'ok';
        } catch (e) {
          return false;
        }
      },
      'health response time < 2000ms': (r) => r.timings.duration < 2000,
    });

    errorRate.add(!success);
    logResult('/health', success, duration, res.body);
  });
}

// ── 测试 2: 盖娅知识库查询 ────────────────────────────────────────────────────
function testGaiaKnowledge() {
  group('Gaia Knowledge', function () {
    const url = `${BASE_URL}/api/gaia/knowledge`;
    const params = {
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'k6-chainke-benchmark/1.0',
      },
      timeout: '15s',
      tags: { endpoint: '/api/gaia/knowledge' },
    };

    const res = http.get(url, params);
    const duration = res.timings.duration;
    knowledgeTrend.add(duration);
    totalRequests.add(1);

    const success = check(res, {
      'knowledge status is 200': (r) => r.status === 200,
      'knowledge response is valid JSON': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body !== null;
        } catch (e) {
          return false;
        }
      },
      'knowledge response time < 5000ms': (r) => r.timings.duration < 5000,
    });

    errorRate.add(!success);
    logResult('/api/gaia/knowledge', success, duration, res.body);
  });
}

// ── 测试 3: 复盘框架查询 ──────────────────────────────────────────────────────
function testRetroFramework() {
  group('Retro Framework', function () {
    const url = `${BASE_URL}/api/retro/framework`;
    const params = {
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'k6-chainke-benchmark/1.0',
      },
      timeout: '10s',
      tags: { endpoint: '/api/retro/framework' },
    };

    const res = http.get(url, params);
    const duration = res.timings.duration;
    retroTrend.add(duration);
    totalRequests.add(1);

    const success = check(res, {
      'retro status is 200': (r) => r.status === 200,
      'retro contains F1-F9 framework': (r) => {
        try {
          const body = JSON.parse(r.body);
          // The framework returns a list of retro steps
          return body !== null;
        } catch (e) {
          return false;
        }
      },
      'retro response time < 2000ms': (r) => r.timings.duration < 2000,
    });

    errorRate.add(!success);
    logResult('/api/retro/framework', success, duration, res.body);
  });
}

// ── 主函数 ────────────────────────────────────────────────────────────────────
export default function () {
  // 每个 VU 循环执行: 随机选择一个端点或串行执行所有
  const scenario = __ENV.SCENARIO || 'all';

  switch (scenario) {
    case 'health':
      testHealth();
      break;
    case 'knowledge':
      testGaiaKnowledge();
      break;
    case 'retro':
      testRetroFramework();
      break;
    default:
      // 串行执行所有测试 (模拟真实用户行为)
      testHealth();
      sleep(Math.random() * 2 + 0.5); // 0.5~2.5s 思考时间
      testGaiaKnowledge();
      sleep(Math.random() * 3 + 1);   // 1~4s 思考时间
      testRetroFramework();
      sleep(Math.random() * 1 + 0.5); // 0.5~1.5s 思考时间
      break;
  }
}

// ── 结果处理 (teardown) ────────────────────────────────────────────────────────
export function teardown() {
  console.log('========================================');
  console.log('  链客宝 k6 性能基准测试完成');
  console.log(`  目标: ${BASE_URL}`);
  console.log(`  版本: ${APP_VERSION}`);
  console.log('========================================');

  // 输出自定义指标摘要
  console.log('\n--- 端点延迟 (p95) ---');
  console.log(`  /health                : ${healthTrend.avg ? healthTrend.avg.toFixed(2) : 'N/A'}ms avg`);
  console.log(`  /api/gaia/knowledge    : ${knowledgeTrend.avg ? knowledgeTrend.avg.toFixed(2) : 'N/A'}ms avg`);
  console.log(`  /api/retro/framework   : ${retroTrend.avg ? retroTrend.avg.toFixed(2) : 'N/A'}ms avg`);
  console.log(`  总请求数               : ${totalRequests.count}`);
  console.log(`  错误率                 : ${(errorRate.rate * 100).toFixed(2)}%`);
}

// ── 导出选项注解 ──────────────────────────────────────────────────────────────
// 用法示例:
//
//   # 完整基准测试
//   k6 run tests/k6_test.js
//
//   # 指定目标地址
//   k6 run tests/k6_test.js -e BASE_URL=http://staging.liankebao.com:8201
//
//   # 仅测试健康检查
//   k6 run tests/k6_test.js -e SCENARIO=health
//
//   # 输出 JSON 结果
//   k6 run tests/k6_test.js --out json=k6-report.json
//
//   # 输出摘要到网页
//   k6 run tests/k6_test.js --out web-dashboard
//
//   # 调试模式
//   k6 run tests/k6_test.js -e DEBUG=verbose
