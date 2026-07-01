import React, { useEffect, useState, useCallback } from 'react';
import ForceGraph from './ForceGraph';

interface RelationSignal {
  source_type: string;
  from_entity_id: number;
  from_entity_type: string;
  to_entity_id: number;
  to_entity_type: string;
  signal_strength: number;
  evidence: string;
}

interface NetworkNode {
  id: number;
  name: string;
  type: 'user' | 'enterprise';
  connections: number;
}

const API_BASE = '/api';

const RelationGraphPage: React.FC = () => {
  const [signals, setSignals] = useState<RelationSignal[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchId, setSearchId] = useState('');
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSignals = useCallback(async (userId?: number) => {
    setLoading(true);
    setError(null);
    try {
      const url = userId 
        ? `${API_BASE}/relation-mining/signals/${userId}`
        : `${API_BASE}/relation-mining/signals?limit=100`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.success) {
        setSignals(data.data.signals || []);
        if (userId && data.data.strength !== undefined) {
          setStats({ user_id: userId, total: data.data.total_signals, strength: data.data.strength });
        }
      } else {
        setError(data.message || '获取信号失败');
      }
    } catch (e: any) {
      setError(e.message || '网络错误');
    } finally {
      setLoading(false);
    }
  }, []);

  const triggerScan = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/relation-mining/scan`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setStats({ type: 'scan', total_signals: data.data?.total_signals || 0 });
        loadSignals();
      } else {
        setError(data.message || '扫描失败');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const triggerAutoCreate = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/relation-mining/auto-create`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setStats({ type: 'auto-create', created: data.data?.created || 0 });
      } else {
        setError(data.message || '自动创建失败');
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSignals();
  }, [loadSignals]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const uid = parseInt(searchId);
    if (!isNaN(uid)) {
      loadSignals(uid);
    }
  };

  const graphData = {
    nodes: Array.from(new Set(signals.flatMap(s => [s.from_entity_id, s.to_entity_id]))).map(id => ({
      id,
      label: `${id}`,
      type: signals.find(s => s.from_entity_id === id)?.from_entity_type || 'user',
    })),
    links: signals.map(s => ({
      source: s.from_entity_id,
      target: s.to_entity_id,
      strength: s.signal_strength,
      type: s.source_type,
    })),
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'system-ui, sans-serif' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '16px' }}>
        🔗 关系图谱
      </h1>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px' }}>
          <input
            type="number"
            placeholder="搜索用户ID..."
            value={searchId}
            onChange={e => setSearchId(e.target.value)}
            style={{ padding: '8px 12px', border: '1px solid #ccc', borderRadius: '6px', fontSize: '14px' }}
          />
          <button type="submit" style={btnStyle}>搜索</button>
        </form>
        <button onClick={() => loadSignals()} style={btnStyle}>全部信号</button>
        <button onClick={triggerScan} style={{ ...btnStyle, background: '#1677ff' }}>🔍 扫描</button>
        <button onClick={triggerAutoCreate} style={{ ...btnStyle, background: '#52c41a' }}>🔗 自动创建关系</button>
      </div>

      {stats && (
        <div style={{ background: '#f6ffed', padding: '12px', borderRadius: '8px', marginBottom: '16px', fontSize: '14px' }}>
          {stats.type === 'scan' && `扫描完成: ${stats.total_signals} 条信号`}
          {stats.type === 'auto-create' && `自动创建: ${stats.created} 条关系`}
          {stats.user_id !== undefined && `用户 #${stats.user_id}: ${stats.total} 条信号, 综合强度 ${stats.strength}`}
        </div>
      )}

      {error && (
        <div style={{ background: '#fff2f0', padding: '12px', borderRadius: '8px', marginBottom: '16px', color: '#cf1322', fontSize: '14px' }}>
          ⚠️ {error}
        </div>
      )}

      <div style={{ background: '#fff', borderRadius: '12px', boxShadow: '0 2px 8px rgba(0,0,0,0.06)', padding: '16px', minHeight: '500px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: '#999' }}>加载中...</div>
        ) : graphData.nodes.length > 0 ? (
          <ForceGraph nodes={graphData.nodes} links={graphData.links} />
        ) : (
          <div style={{ textAlign: 'center', padding: '60px', color: '#999' }}>
            暂无关系数据，点击「扫描」触发关系挖掘
            <div style={{ marginTop: '12px', fontSize: '13px', color: '#bbb' }}>
              信号采集器会从合同、订单、企业互动中自动发现关系
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const btnStyle: React.CSSProperties = {
  padding: '8px 16px',
  border: 'none',
  borderRadius: '6px',
  background: '#f0f0f0',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: 500,
};

export default RelationGraphPage;
