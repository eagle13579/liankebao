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
    track: vi.fn(),
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
          total_revenue: 15800,
          today_orders: 23,
          total_orders: 230,
          total_users: 1200,
          total_products: 45,
          pending_review_products: 5,
          pending_withdrawals: 3,
        },
      });
    }
    if (url.includes('/api/admin/products')) {
      return Promise.resolve({
        code: 200,
        data: {
          total: 2,
          items: [
            { id: 1, name: '智能健康手表 S3', company: '科技有限公司', price: 1299, status: 'pending', created_at: '2025-05-28T10:00:00Z' },
            { id: 2, name: '高端商务茶礼套装', company: '贸易有限公司', price: 688, status: 'pending', created_at: '2025-05-27T10:00:00Z' },
          ],
        },
      });
    }
    if (url.includes('/api/admin/withdrawals')) {
      return Promise.resolve({
        code: 200,
        data: {
          total: 2,
          items: [
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
      expect(screen.getByText('企盟 · 管理后台')).toBeInTheDocument();
    });
  });

  it('renders dashboard summary cards from API', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('总交易额')).toBeInTheDocument();
      expect(screen.getByText('总订单数')).toBeInTheDocument();
      expect(screen.getByText('注册用户')).toBeInTheDocument();
      expect(screen.getByText('全部产品')).toBeInTheDocument();
    });
  });

  it('renders dashboard values from API', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      // Value is rendered as "¥15,800.00" — use regex to match the number
      expect(screen.getByText(/15,800/)).toBeInTheDocument();
      expect(screen.getByText('23')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it('renders product review section with 待审核产品 heading', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      // Appears as both section heading and in the pending items list
      expect(screen.getAllByText('待审核产品').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders pending products for review', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
    });
  });

  it('shows pending review alert when there are pending products', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('5 个产品待审核')).toBeInTheDocument();
    });
  });

  it('shows withdrawal pending alert when there are pending withdrawals', async () => {
    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('3 笔提现待处理')).toBeInTheDocument();
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
        return Promise.resolve({ code: 200, data: { total_revenue: 0, today_orders: 0, total_orders: 0, total_users: 0, total_products: 0, pending_review_products: 0, pending_withdrawals: 0 } });
      }
      if (url.includes('/api/admin/products')) {
        return Promise.resolve({ code: 200, data: { total: 0, items: [] } });
      }
      if (url.includes('/api/admin/withdrawals')) {
        return Promise.resolve({ code: 200, data: { total: 0, items: [] } });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<AdminBackend />);

    await waitFor(() => {
      expect(screen.getByText('暂无待审核产品')).toBeInTheDocument();
    });
  });
});
