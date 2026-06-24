/**
 * 链客宝开发者门户 — 主页面
 * 包含: API Key管理, Webhook配置, 调用统计仪表盘, API文档
 */
import React, { useState, useEffect } from 'react';
import { api } from '../../api/client';
import ApiKeysSection from './ApiKeysSection';
import WebhooksSection from './WebhooksSection';
import UsageDashboard from './UsageDashboard';
import ApiDocsViewer from './ApiDocsViewer';

type TabId = 'api-keys' | 'webhooks' | 'usage' | 'docs';

interface DashboardData {
  api_keys: { total: number; active: number };
  webhooks: { total: number; active: number };
  today: { calls: number; errors: number; error_rate: number };
}

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: 'api-keys', label: 'API Keys', icon: '🔑' },
  { id: 'webhooks', label: 'Webhooks', icon: '🔔' },
  { id: 'usage', label: '调用统计', icon: '📊' },
  { id: 'docs', label: 'API文档', icon: '📖' },
];

export default function DeveloperPortalPage() {
  const [activeTab, setActiveTab] = useState<TabId>('api-keys');
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setLoading(true);
    const res = await api.get('/api/developer/dashboard');
    if (res.code === 0 && res.data) {
      setDashboard(res.data as DashboardData);
    }
    setLoading(false);
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'api-keys':
        return <ApiKeysSection />;
      case 'webhooks':
        return <WebhooksSection />;
      case 'usage':
        return <UsageDashboard />;
      case 'docs':
        return <ApiDocsViewer />;
      default:
        return null;
    }
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>开发者门户</h1>
          <p style={styles.subtitle}>链客宝开放平台 — 构建您的应用</p>
        </div>
        <div style={styles.headerBadge}>
          <span style={styles.badge}>v1.0.0</span>
        </div>
      </div>

      {/* Dashboard Cards */}
      {dashboard && (
        <div style={styles.cardsRow}>
          <div style={{...styles.card, borderLeft: '4px solid #64ffda'}}>
            <div style={styles.cardIcon}>🔑</div>
            <div style={styles.cardContent}>
              <div style={styles.cardValue}>{dashboard.api_keys.active}/{dashboard.api_keys.total}</div>
              <div style={styles.cardLabel}>活跃 API Keys</div>
            </div>
          </div>
          <div style={{...styles.card, borderLeft: '4px solid #64b5f6'}}>
            <div style={styles.cardIcon}>🔔</div>
            <div style={styles.cardContent}>
              <div style={styles.cardValue}>{dashboard.webhooks.active}/{dashboard.webhooks.total}</div>
              <div style={styles.cardLabel}>活跃 Webhooks</div>
            </div>
          </div>
          <div style={{...styles.card, borderLeft: '4px solid #ffb74d'}}>
            <div style={styles.cardIcon}>📞</div>
            <div style={styles.cardContent}>
              <div style={styles.cardValue}>{dashboard.today.calls}</div>
              <div style={styles.cardLabel}>今日调用</div>
            </div>
          </div>
          <div style={{...styles.card, borderLeft: `4px solid ${dashboard.today.error_rate > 5 ? '#ef5350' : '#66bb6a'}`}}>
            <div style={styles.cardIcon}>⚠️</div>
            <div style={styles.cardContent}>
              <div style={{...styles.cardValue, color: dashboard.today.error_rate > 5 ? '#ef5350' : '#66bb6a'}}>{dashboard.today.error_rate}%</div>
              <div style={styles.cardLabel}>错误率</div>
            </div>
          </div>

        </div>
      )}

      {/* Tabs */}
      <div style={styles.tabsContainer}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              ...styles.tab,
              ...(activeTab === tab.id ? styles.tabActive : {}),
            }}
          >
            <span style={styles.tabIcon}>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={styles.tabContent}>
        {renderTabContent()}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: '32px 24px',
    maxWidth: 1200,
    margin: '0 auto',
    color: '#e0e0e0',
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 28,
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    margin: 0,
    color: '#ffffff',
    letterSpacing: '-0.5px',
  },
  subtitle: {
    fontSize: 14,
    color: '#888',
    margin: '4px 0 0 0',
  },
  headerBadge: {
    display: 'flex',
    gap: 8,
  },
  badge: {
    padding: '4px 12px',
    borderRadius: 20,
    background: 'rgba(100, 255, 218, 0.1)',
    color: '#64ffda',
    fontSize: 12,
    fontWeight: 600,
    border: '1px solid rgba(100, 255, 218, 0.2)',
  },
  cardsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: 16,
    marginBottom: 28,
  },
  card: {
    background: 'rgba(255,255,255,0.04)',
    borderRadius: 12,
    padding: '20px 24px',
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    border: '1px solid rgba(255,255,255,0.06)',
  },
  cardIcon: {
    fontSize: 28,
    width: 48,
    height: 48,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'rgba(255,255,255,0.05)',
    borderRadius: 12,
  },
  cardContent: {},
  cardValue: {
    fontSize: 24,
    fontWeight: 700,
    color: '#ffffff',
  },
  cardLabel: {
    fontSize: 13,
    color: '#888',
    marginTop: 2,
  },
  tabsContainer: {
    display: 'flex',
    gap: 4,
    background: 'rgba(255,255,255,0.03)',
    borderRadius: 12,
    padding: 4,
    marginBottom: 24,
    border: '1px solid rgba(255,255,255,0.06)',
  },
  tab: {
    flex: 1,
    padding: '12px 16px',
    border: 'none',
    borderRadius: 10,
    background: 'transparent',
    color: '#888',
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    transition: 'all 0.2s',
  },
  tabActive: {
    background: 'rgba(100, 255, 218, 0.1)',
    color: '#64ffda',
    fontWeight: 600,
  },
  tabIcon: {
    fontSize: 16,
  },
  tabContent: {
    minHeight: 400,
  },
};
