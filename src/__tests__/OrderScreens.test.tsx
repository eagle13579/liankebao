import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Mock api / payment
const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('../api/client', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    put: vi.fn(),
    saveToken: vi.fn(),
    loadToken: vi.fn(),
    removeToken: vi.fn(),
  },
}));

vi.mock('../api/payment', () => ({
  paymentApi: {
    unifiedOrder: vi.fn(),
  },
}));

const mockNavigate = vi.fn();
let mockSearchParamsObj: Record<string, string> = {};

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => {
      const params = new URLSearchParams('');
      for (const [k, v] of Object.entries(mockSearchParamsObj)) {
        params.set(k, v);
      }
      return [params, vi.fn()];
    },
  };
});

import { OrderConfirmation, PaymentSuccessScreens, MyOrders, OrderManagement } from '../screens/OrderScreens';
import { paymentApi } from '../api/payment';

beforeEach(() => {
  vi.clearAllMocks();
  mockSearchParamsObj = {};
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/orders')) {
      return Promise.resolve({
        code: 200,
        data: {
          orders: [
            { id: 1, product_id: 1, product_name: '智能健康手表 S3', total_price: 1299, status: 'paid', created_at: '2025-05-28T10:00:00Z' },
            { id: 2, product_id: 2, product_name: '商务茶礼套装', total_price: 688, status: 'completed', created_at: '2025-05-27T10:00:00Z' },
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

// ─── OrderConfirmation Tests ──────────────────────────

describe('OrderConfirmation (订单确认) - Smoke Tests', () => {
  it('renders the page header with title', () => {
    renderWithRouter(<OrderConfirmation />);

    expect(screen.getByText('订单确认')).toBeInTheDocument();
  });

  it('renders shipping address section', () => {
    renderWithRouter(<OrderConfirmation />);

    expect(screen.getByText('张三')).toBeInTheDocument();
    expect(screen.getByText('13800138000')).toBeInTheDocument();
  });

  it('renders product info in order', () => {
    renderWithRouter(<OrderConfirmation />);

    expect(screen.getByText('高级护肝综合营养片')).toBeInTheDocument();
    // Price appears in multiple places; just verify it's rendered
    const prices = screen.getAllByText(/298\.00/);
    expect(prices.length).toBeGreaterThanOrEqual(1);
  });

  it('renders recommender info', () => {
    renderWithRouter(<OrderConfirmation />);

    expect(screen.getByText('推荐人：李四')).toBeInTheDocument();
  });

  it('renders order note input', () => {
    renderWithRouter(<OrderConfirmation />);

    expect(screen.getByPlaceholderText('订单备注（选填）')).toBeInTheDocument();
  });

  it('renders pay button', () => {
    renderWithRouter(<OrderConfirmation />);

    expect(screen.getByText('微信支付 ¥298.00')).toBeInTheDocument();
  });
});

describe('OrderConfirmation (订单确认) - Interaction Tests', () => {
  it('shows paying state when clicking pay button', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<OrderConfirmation />);

    const payBtn = screen.getByText('微信支付 ¥298.00');
    fireEvent.click(payBtn);

    await waitFor(() => {
      expect(screen.getByText('支付处理中...')).toBeInTheDocument();
    });
  });

  it('navigates to payment bridge on successful pay', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { order: {}, payment: {} },
    });

    renderWithRouter(<OrderConfirmation />);

    const payBtn = screen.getByText('微信支付 ¥298.00');
    fireEvent.click(payBtn);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(
        expect.stringContaining('/payment-bridge'),
        { state: { transition: 'push' } }
      );
    });
  });

  it('shows error message on pay failure', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 500,
      message: '支付初始化失败，请重试',
    });

    renderWithRouter(<OrderConfirmation />);

    const payBtn = screen.getByText('微信支付 ¥298.00');
    fireEvent.click(payBtn);

    await waitFor(() => {
      expect(screen.getByText('支付初始化失败，请重试')).toBeInTheDocument();
    });
  });
});

// ─── PaymentSuccessScreens Tests ───────────────────────

describe('PaymentSuccessScreens (支付成功) - Smoke Tests', () => {
  it('renders the page header with title', () => {
    mockSearchParamsObj = { order_no: 'ORD12345', amount: '298.00' };
    renderWithRouter(<PaymentSuccessScreens />);

    expect(screen.getByText('支付成功')).toBeInTheDocument();
  });

  it('renders success message and amount', () => {
    mockSearchParamsObj = { order_no: 'ORD12345', amount: '298.00' };
    renderWithRouter(<PaymentSuccessScreens />);

    expect(screen.getByText('支付成功！')).toBeInTheDocument();
    expect(screen.getByText(/298\.00/)).toBeInTheDocument();
  });

  it('renders order number from URL params', () => {
    mockSearchParamsObj = { order_no: 'ORD12345', amount: '298.00' };
    renderWithRouter(<PaymentSuccessScreens />);

    // Order number is rendered as "订单号：ORD12345"
    expect(screen.getByText(/订单号.*ORD12345/)).toBeInTheDocument();
  });

  it('renders promotion section', () => {
    mockSearchParamsObj = { order_no: 'ORD12345', amount: '298.00' };
    renderWithRouter(<PaymentSuccessScreens />);

    expect(screen.getByText('你也能赚')).toBeInTheDocument();
    expect(screen.getByText('成为推广员')).toBeInTheDocument();
  });

  it('renders action buttons: 查看订单详情 and 返回首页', () => {
    mockSearchParamsObj = { order_no: 'ORD12345', amount: '298.00' };
    renderWithRouter(<PaymentSuccessScreens />);

    expect(screen.getByText('查看订单详情')).toBeInTheDocument();
    expect(screen.getByText('返回首页')).toBeInTheDocument();
  });
});

describe('PaymentSuccessScreens (支付成功) - Interaction Tests', () => {
  it('navigates to my-orders when clicking 查看订单详情', () => {
    mockSearchParamsObj = { order_no: 'ORD12345', amount: '298.00' };
    renderWithRouter(<PaymentSuccessScreens />);

    const orderBtn = screen.getByText('查看订单详情');
    fireEvent.click(orderBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/my-orders', { state: { transition: 'push' } });
  });

  it('navigates to home when clicking 返回首页', () => {
    mockSearchParamsObj = { order_no: 'ORD12345', amount: '298.00' };
    renderWithRouter(<PaymentSuccessScreens />);

    const homeBtn = screen.getByText('返回首页');
    fireEvent.click(homeBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/home', { state: { transition: 'push' } });
  });
});

// ─── MyOrders Tests ────────────────────────────────────

describe('MyOrders (我的订单) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<MyOrders />);

    await waitFor(() => {
      expect(screen.getByText('我的订单')).toBeInTheDocument();
    });
  });

  it('renders order tab navigation', async () => {
    renderWithRouter(<MyOrders />);

    await waitFor(() => {
      expect(screen.getByText('全部')).toBeInTheDocument();
      expect(screen.getByText('待支付')).toBeInTheDocument();
      expect(screen.getByText('待发货')).toBeInTheDocument();
      expect(screen.getByText('待收货')).toBeInTheDocument();
      expect(screen.getByText('已完成')).toBeInTheDocument();
    });
  });

  it('renders order items from API', async () => {
    renderWithRouter(<MyOrders />);

    await waitFor(() => {
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
      expect(screen.getByText('商务茶礼套装')).toBeInTheDocument();
    });
  });

  it('renders order prices', async () => {
    renderWithRouter(<MyOrders />);

    await waitFor(() => {
      // Prices appear in multiple places (item price and total), use getAllByText
      const prices = screen.getAllByText(/1299\.00/);
      expect(prices.length).toBeGreaterThanOrEqual(1);
      const prices2 = screen.getAllByText(/688\.00/);
      expect(prices2.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows empty state when no orders', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/orders')) {
        return Promise.resolve({ code: 200, data: { orders: [] } });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<MyOrders />);

    await waitFor(() => {
      expect(screen.getByText('暂无订单')).toBeInTheDocument();
    });
  });
});

describe('MyOrders (我的订单) - Interaction Tests', () => {
  it('switches tab when clicking tab', async () => {
    renderWithRouter(<MyOrders />);

    await waitFor(() => {
      const paidTab = screen.getByText('待支付');
      fireEvent.click(paidTab);
    });

    // Tab switching triggers re-fetch with status filter
    await waitFor(() => {
      const calls = mockGet.mock.calls.filter((c: any) => c[0].includes('/api/orders'));
      // The last call should contain the new status
      expect(calls.length).toBeGreaterThanOrEqual(2);
    });
  });
});

// ─── OrderManagement Tests ─────────────────────────────

describe('OrderManagement (订单管理) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<OrderManagement />);

    await waitFor(() => {
      expect(screen.getByText('订单管理')).toBeInTheDocument();
    });
  });

  it('renders management tabs', async () => {
    renderWithRouter(<OrderManagement />);

    await waitFor(() => {
      expect(screen.getByText('待发货')).toBeInTheDocument();
      expect(screen.getByText('配送中')).toBeInTheDocument();
      expect(screen.getByText('已完成')).toBeInTheDocument();
      expect(screen.getByText('全部')).toBeInTheDocument();
    });
  });

  it('renders order items from API', async () => {
    renderWithRouter(<OrderManagement />);

    await waitFor(() => {
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
    });
  });

  it('renders merchant order prices', async () => {
    renderWithRouter(<OrderManagement />);

    await waitFor(() => {
      expect(screen.getByText('¥1299.00')).toBeInTheDocument();
    });
  });

  it('renders ship button for orders', async () => {
    renderWithRouter(<OrderManagement />);

    await waitFor(() => {
      expect(screen.getAllByText('立即发货').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows empty state when no merchant orders', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/orders')) {
        return Promise.resolve({ code: 200, data: { orders: [] } });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<OrderManagement />);

    await waitFor(() => {
      expect(screen.getByText('暂无订单')).toBeInTheDocument();
    });
  });
});
