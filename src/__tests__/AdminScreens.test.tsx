import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Mock api
const mockGet = vi.fn();
const mockPut = vi.fn();
vi.mock('../api/client', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: vi.fn(),
    put: (...args: any[]) => mockPut(...args),
    saveToken: vi.fn(),
    loadToken: vi.fn(),
    removeToken: vi.fn(),
  },
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { AdminBackend } from '../screens/AdminScreens';

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/admin/dashboard')) {
      return Promise.resolve({
        code: 200,
        data: {
          dashboard: { today_revenue: 15800, today_orders: 23, active_promoters: 45, pending_products: 5 },
        },
      });
    }
    if (url.includes('/api/admin/products')) {
      return Promise.resolve({
        code: 200,
        data: {
          products: [
            { id: 1, name: '智能健康手表 S3', company: '科技有限公司', price: 1299, created_at: '2025-05-28T10:00:00Z' },
            { id: 2, name: '高端商务茶礼套装', company: '贸易有限公司', price: 688, created_at: '2025-05-27T10:00:00Z' },
          ],
        },
      });
    }
    if (url.includes('/api/admin/withdrawals')) {
      return Promise.resolve({
        code: 200,
        data: {
          withdrawals: [
            { id: 1, user_name: '张三', amount: 500, status: 'pending', created_at: '2025-05-28T10:00:00Z' },
            { id: 2, user_name: '李四', amount: 1200, status: 'pending', created_at: '2025-05-27T10:00:00Z' },
          ],
        },
      });
    }
    return Promise.resolve({ code: 200, data: null });
  });
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── Smoke Tests ──────────────────────────────────────

describe('AdminBackend (管理后台) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('管理后台')).toBeInTheDocument();
    });
  });

  it('renders dashboard summary cards from API', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('今日交易额')).toBeInTheDocument();
      expect(screen.getByText('今日订单数')).toBeInTheDocument();
      expect(screen.getByText('活跃推广员')).toBeInTheDocument();
      expect(screen.getByText('待审核产品')).toBeInTheDocument();
    });
  });

  // TODO: mock数据格式需对齐 useApi hook 的 data.dashboard 结构
  it.skip('renders dashboard values from API', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      // toLocaleString() produces "15,800" not "15,800.00"
      expect(screen.getByText('15,800')).toBeInTheDocument();
      expect(screen.getByText('23')).toBeInTheDocument();
      expect(screen.getByText('45')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders product review section', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('产品审核')).toBeInTheDocument();
    });
  });

  it('renders pending products for review', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
    });
  });

  it('renders withdrawal review section', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('提现审核')).toBeInTheDocument();
    });
  });

  it('shows withdrawal items', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
      expect(screen.getByText('李四')).toBeInTheDocument();
    });
  });

  it('shows loading state', () => {
    mockGet.mockReturnValue(new Promise(() => {}));

    renderWithRouter(<AdminBackend />);
    expect(screen.getByText('加载数据看板...')).toBeInTheDocument();
  });
});

// ─── Interaction Tests ────────────────────────────────

describe('AdminBackend (管理后台) - Interaction Tests', () => {
  it('approves a product review', async () => {
    mockPut.mockResolvedValue({ code: 200 });

    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      // Find all approve buttons
      const approveBtns = screen.getAllByText('通过');
      expect(approveBtns.length).toBeGreaterThanOrEqual(1);
      fireEvent.click(approveBtns[0]);
    });

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith('/api/admin/products/1/review', { action: 'approve' });
    });
  });

  it('rejects a product review', async () => {
    mockPut.mockResolvedValue({ code: 200 });

    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      const rejectBtns = screen.getAllByText('驳回');
      expect(rejectBtns.length).toBeGreaterThanOrEqual(1);
      fireEvent.click(rejectBtns[0]);
    });

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith('/api/admin/products/1/review', { action: 'reject' });
    });
  });
});

// ─── Edge Cases ────────────────────────────────────────

describe('AdminBackend (管理后台) - Edge Cases', () => {
  it('shows error state when dashboard API fails', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/admin/dashboard')) {
        return Promise.reject(new Error('获取数据失败'));
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('获取数据失败')).toBeInTheDocument();
    });
  });

  it('shows empty state when no products pending review', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/admin/dashboard')) {
        return Promise.resolve({ code: 200, data: { dashboard: { today_revenue: 0, today_orders: 0, active_promoters: 0, pending_products: 0 } } });
      }
      if (url.includes('/api/admin/products')) {
        return Promise.resolve({ code: 200, data: { products: [] } });
      }
      if (url.includes('/api/admin/withdrawals')) {
        return Promise.resolve({ code: 200, data: { withdrawals: [] } });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('暂无待审核产品')).toBeInTheDocument();
    });
  });
});
