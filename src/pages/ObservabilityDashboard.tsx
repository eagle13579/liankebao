/**
 * 全链路可观测性看板
 * ==================
 * 对标 Stripe Dashboard / Grafana
 * 展示: 健康状态 / 延迟百分位 / 错误率 / 系统资源 / 慢查询
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Activity, AlertTriangle, Clock, Cpu, Database, HardDrive, Server, Zap } from 'lucide-react';

// ===== 类型定义 =====

interface DashboardData {
  health: string;
  uptime_hours: number;
  latency_p50: number;
  latency_p99: number;
  error_rate_per_minute: number;
  requests_per_minute: number;
  active_connections: number;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
}

interface HealthData {
  status: string;
  uptime_seconds: number;
  components: Record<string, string>;
}

interface LatencyData {
  overall: Record<string, number>;
  endpoints: Record<string, Record<string, number>>;
  sample_count: number;
}

interface ErrorData {
  total_errors: number;
  error_rate_per_minute: number;
  errors_by_type: Record<string, number>;
  recent_errors: Array<{ time: string; type: string }>;
}

interface SlowQuery {
  query: string;
  duration_ms: number;
  timestamp: string;
  endpoint?: string;
}

// ===== 组件 =====

function MetricCard({ icon: Icon, label, value, unit, color, sub }: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  unit?: string;
  color: 'green' | 'yellow' | 'red' | 'blue';
  sub?: string;
}) {
  const colors = {
    green: 'from-emerald-500/20 to-emerald-600/10 border-emerald-500/30 text-emerald-400',
    yellow: 'from-amber-500/20 to-amber-600/10 border-amber-500/30 text-amber-400',
    red: 'from-red-500/20 to-red-600/10 border-red-500/30 text-red-400',
    blue: 'from-blue-500/20 to-blue-600/10 border-blue-500/30 text-blue-400',
  };

  return (
    <div className={`bg-gradient-to-br ${colors[color]} border rounded-xl p-4`}>
      <div className="flex items-center gap-3 mb-2">
        <Icon className="w-5 h-5 opacity-70" />
        <span className="text-sm text-white/60">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white">
        {typeof value === 'number' ? value.toLocaleString() : value}
        {unit && <span className="text-sm ml-1 text-white/50">{unit}</span>}
      </div>
      {sub && <div className="text-xs text-white/40 mt-1">{sub}</div>}
    </div>
  );
}

function ProgressBar({ label, value, max, color }: {
  label: string;
  value: number;
  max?: number;
  color: 'green' | 'yellow' | 'red';
}) {
  const pct = max ? Math.min(100, (value / max) * 100) : Math.min(100, value);
  const colors = {
    green: 'bg-emerald-500',
    yellow: 'bg-amber-500',
    red: 'bg-red-500',
  };

  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-white/60">{label}</span>
        <span className="text-white/80">{max ? `${value}/${max}` : `${value}%`}</span>
      </div>
      <div className="h-2 bg-white/10 rounded-full overflow-hidden">
        <div
          className={`h-full ${colors[color]} rounded-full transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ===== 主组件 =====

export default function ObservabilityDashboard() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [latency, setLatency] = useState<LatencyData | null>(null);
  const [errors, setErrors] = useState<ErrorData | null>(null);
  const [slowQueries, setSlowQueries] = useState<SlowQuery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const baseUrl = '/lkapi';
      const [dashRes, healthRes, latRes, errRes, sqRes] = await Promise.all([
        fetch(`${baseUrl}/api/observability/dashboard`).then(r => r.json()),
        fetch(`${baseUrl}/api/observability/health`).then(r => r.json()),
        fetch(`${baseUrl}/api/observability/latency`).then(r => r.json()),
        fetch(`${baseUrl}/api/observability/errors`).then(r => r.json()),
        fetch(`${baseUrl}/api/observability/slow-queries`).then(r => r.json()),
      ]);

      setDashboard(dashRes);
      setHealth(healthRes);
      setLatency(latRes);
      setErrors(errRes);
      setSlowQueries(sqRes?.queries || []);
      setError('');
    } catch (e) {
      setError('获取数据失败，请检查后端服务');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000); // 15秒刷新
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0c0e19] flex items-center justify-center">
        <div className="text-white/60 animate-pulse">加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0c0e19] flex items-center justify-center">
        <div className="text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-5 h-5" />
          {error}
        </div>
      </div>
    );
  }

  const healthColor = dashboard?.health === 'healthy' ? 'green' :
    dashboard?.health === 'degraded' ? 'yellow' : 'red';

  return (
    <div className="min-h-screen bg-[#0c0e19] p-6">
      {/* 头部 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Activity className="w-7 h-7 text-emerald-400" />
            全链路可观测性看板
          </h1>
          <p className="text-white/40 text-sm mt-1">
            运行时间: {dashboard?.uptime_hours?.toFixed(1)}h |
            请求速率: {dashboard?.requests_per_minute} req/min
          </p>
        </div>
        <div className={`px-4 py-2 rounded-full text-sm font-semibold ${
          healthColor === 'green' ? 'bg-emerald-500/20 text-emerald-400' :
          healthColor === 'yellow' ? 'bg-amber-500/20 text-amber-400' :
          'bg-red-500/20 text-red-400'
        }`}>
          {dashboard?.health?.toUpperCase() || 'UNKNOWN'}
        </div>
      </div>

      {/* 核心指标卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetricCard
          icon={Clock}
          label="P50 延迟"
          value={dashboard?.latency_p50?.toFixed(1) || 0}
          unit="ms"
          color={dashboard && dashboard.latency_p50 < 200 ? 'green' : 'yellow'}
          sub="目标 < 200ms"
        />
        <MetricCard
          icon={Clock}
          label="P99 延迟"
          value={dashboard?.latency_p99?.toFixed(1) || 0}
          unit="ms"
          color={dashboard && dashboard.latency_p99 < 1000 ? 'green' : 'red'}
          sub="目标 < 1000ms"
        />
        <MetricCard
          icon={AlertTriangle}
          label="错误率"
          value={dashboard?.error_rate_per_minute?.toFixed(2) || 0}
          unit="/min"
          color={dashboard && dashboard.error_rate_per_minute < 1 ? 'green' : 'red'}
          sub={errors ? `总计 ${errors.total_errors} 个错误` : ''}
        />
        <MetricCard
          icon={Zap}
          label="活跃连接"
          value={dashboard?.active_connections || 0}
          color="blue"
        />
      </div>

      {/* 系统资源 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="bg-white/5 border border-white/10 rounded-xl p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Server className="w-4 h-4 text-blue-400" />
            系统资源
          </h2>
          <ProgressBar
            label="CPU"
            value={dashboard?.cpu_percent || 0}
            color={dashboard && dashboard.cpu_percent > 80 ? 'red' : 'green'}
          />
          <ProgressBar
            label="内存"
            value={dashboard?.memory_percent || 0}
            color={dashboard && dashboard.memory_percent > 85 ? 'red' : 'green'}
          />
          <ProgressBar
            label="磁盘"
            value={dashboard?.disk_percent || 0}
            color={dashboard && dashboard.disk_percent > 85 ? 'red' : 'green'}
          />
        </div>

        {/* 组件健康 */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            组件健康状态
          </h2>
          <div className="space-y-2">
            {health?.components && Object.entries(health.components).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between py-2 border-b border-white/5">
                <span className="text-white/70 capitalize">{name.replace('_', ' ')}</span>
                <span className={`text-sm px-2 py-0.5 rounded ${
                  status.startsWith('healthy') ? 'text-emerald-400 bg-emerald-500/10' :
                  status.startsWith('degraded') ? 'text-amber-400 bg-amber-500/10' :
                  'text-red-400 bg-red-500/10'
                }`}>
                  {status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 延迟百分位详情 */}
      {latency && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-5 mb-6">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-purple-400" />
            延迟百分位 (样本: {latency.sample_count})
          </h2>
          <div className="grid grid-cols-4 gap-4">
            {Object.entries(latency.overall).map(([key, val]) => (
              <div key={key} className="text-center">
                <div className="text-white/40 text-xs uppercase mb-1">{key}</div>
                <div className="text-xl font-bold text-white">{Number(val).toFixed(1)}</div>
                <div className="text-white/30 text-xs">ms</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 错误列表 + 慢查询 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 最近错误 */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            最近错误 ({errors?.recent_errors?.length || 0})
          </h2>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {errors?.recent_errors?.length === 0 && (
              <div className="text-white/30 text-sm">暂无错误</div>
            )}
            {errors?.recent_errors?.map((e, i) => (
              <div key={i} className="text-sm text-white/60 py-1 border-b border-white/5 flex justify-between">
                <span className="text-red-400">{e.type}</span>
                <span className="text-white/30">{new Date(e.time).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 慢查询 */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-5">
          <h2 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Database className="w-4 h-4 text-amber-400" />
            慢查询 ({slowQueries.length})
          </h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {slowQueries.length === 0 && (
              <div className="text-white/30 text-sm">暂无慢查询</div>
            )}
            {slowQueries.map((q, i) => (
              <div key={i} className="text-xs text-white/60 py-1 border-b border-white/5">
                <div className="flex justify-between mb-1">
                  <span className="text-amber-400 font-mono">{q.duration_ms}ms</span>
                  <span className="text-white/30">{new Date(q.timestamp).toLocaleTimeString()}</span>
                </div>
                <div className="text-white/40 truncate">{q.query?.substring(0, 100)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
