import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import PaymentBridge from '../screens/PaymentBridge';
import { paymentApi } from '../api/payment';

// ─── Mocks ─────────────────────────────────────────────

vi.mock('../api/payment', () => ({
  paymentApi: {
    unifiedOrder: vi.fn(),
    queryOrder: vi.fn(),
    getConfig: vi.fn(),
  },
}));

const mockNavigate = vi.fn();
let searchParamsObj: Record<string, string> = {};

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => {
      const params = new URLSearchParams('');
      for (const [k, v] of Object.entries(searchParamsObj)) {
        params.set(k, v);
      }
      return [params, vi.fn()];
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsObj = {
    order_no: '12345',
    amount: '99.00',
    description: '测试商品',
  };
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── Tests ─────────────────────────────────────────────

describe('PaymentBridge - Payment Parameter Construction', () => {
  it('renders with order number from URL params', () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: {
        order: {},
        payment: { appId: 'wxappid', timeStamp: '1234567890', nonceStr: 'nonce', package: 'prepay_id=wx123', signType: 'RSA', paySign: 'signature' },
      },
    });

    renderWithRouter(<PaymentBridge />);

    // The order number 12345 should appear on the page
    expect(screen.getByText('12345')).toBeInTheDocument();
    expect(screen.getByText('¥99.00')).toBeInTheDocument();
  });

  it('makes unifiedOrder API call with correct order_id and description', async () => {
    const mockPaymentParams = {
      appId: 'wx123456789',
      timeStamp: '1717000000',
      nonceStr: 'testnonce123',
      package: 'prepay_id=wx_order_abc',
      signType: 'RSA',
      paySign: 'abc123signature',
    };

    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: {
        order: { id: 12345, amount: 99.00 },
        payment: mockPaymentParams,
      },
    });

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      // The API should be called with order_id and description
      expect(paymentApi.unifiedOrder).toHaveBeenCalledWith(12345, '测试商品');
    });
  });

  it('handles missing order_id gracefully', async () => {
    searchParamsObj = { amount: '50.00', description: 'test' };

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      expect(screen.getByText('订单号缺失')).toBeInTheDocument();
      expect(screen.getByText('无法获取订单信息')).toBeInTheDocument();
    });
  });

  it('shows error when backend returns invalid payment params', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: {
        order: { id: 12345 },
        payment: null,
      },
    });

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      expect(screen.getByText('支付参数异常')).toBeInTheDocument();
    });
  });

  it('handles API failure during unified order', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 500,
      message: '服务器内部错误',
    });

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      expect(screen.getByText('支付初始化失败')).toBeInTheDocument();
      expect(screen.getByText('服务器内部错误')).toBeInTheDocument();
    });
  });

  it('handles network error during API call', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('网络连接失败'));

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      expect(screen.getByText('支付调起失败')).toBeInTheDocument();
    });
  });
});

describe('PaymentBridge - Status Display', () => {
  it('shows preparing status as 正在获取支付参数...', () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<PaymentBridge />);

    // The useEffect calls invokeWechatPay which immediately sets message to '正在获取支付参数...'
    expect(screen.getByText('正在获取支付参数...')).toBeInTheDocument();
  });

  it('shows preparing spinner icon', () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<PaymentBridge />);

    expect(screen.getByText('支付中心')).toBeInTheDocument();
  });

  it('shows not_wechat status with copy link button when not in WeChat browser', async () => {
    // Mock user agent to non-wechat
    Object.defineProperty(navigator, 'userAgent', {
      value: 'Mozilla/5.0 Chrome/120.0',
      configurable: true,
    });

    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: {
        order: { id: 12345 },
        payment: { appId: 'wxappid', timeStamp: '123', nonceStr: 'nonce', package: 'prepay_id=wx123', signType: 'RSA', paySign: 'sig' },
      },
    });

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      expect(screen.getByText('请在微信中打开')).toBeInTheDocument();
    });

    expect(screen.getByText('复制链接')).toBeInTheDocument();
  });

  it('displays order information with amount', () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<PaymentBridge />);

    expect(screen.getByText('12345')).toBeInTheDocument();
    expect(screen.getByText(/¥99\.00/)).toBeInTheDocument();
  });

  it('shows retry button when in error state', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 500,
      message: '服务器错误',
    });

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      expect(screen.getByText('重新支付')).toBeInTheDocument();
    });
  });

  it('shows "查看订单列表" button', () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<PaymentBridge />);

    expect(screen.getByText('查看订单列表')).toBeInTheDocument();
  });

  it('shows "返回首页" button', () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<PaymentBridge />);

    expect(screen.getByText('返回首页')).toBeInTheDocument();
  });

  it('navigates to home when clicking 返回首页', () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<PaymentBridge />);

    const homeBtn = screen.getByText('返回首页');
    fireEvent.click(homeBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/home', { state: { transition: 'push_back' } });
  });

  it('shows error message when displayed', async () => {
    (paymentApi.unifiedOrder as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: {
        order: { id: 12345 },
        payment: null,
      },
    });

    renderWithRouter(<PaymentBridge />);

    await waitFor(() => {
      expect(screen.getByText('未获取到有效的支付参数')).toBeInTheDocument();
    });
  });
});

describe('PaymentBridge - Edge Cases', () => {
  it('uses order_id as fallback when order_no is empty', () => {
    searchParamsObj = { order_id: '67890', amount: '150.00' };

    renderWithRouter(<PaymentBridge />);

    expect(screen.getByText('67890')).toBeInTheDocument();
  });

  it('displays correct amount from URL params', () => {
    searchParamsObj = { order_no: '111', amount: '299.00' };

    renderWithRouter(<PaymentBridge />);

    expect(screen.getByText(/¥299\.00/)).toBeInTheDocument();
  });
});
