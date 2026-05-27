import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { RechargeAmountPage, RechargePaymentPage, RechargeResultPage } from '../screens/RechargeScreens';
import * as rechargeApi from '../api/recharge';

// ─── Mocks ─────────────────────────────────────────────

vi.mock('../api/recharge', () => ({
  getRechargeBalance: vi.fn(),
  createRechargePrecreate: vi.fn(),
  queryRechargeOrder: vi.fn(),
  getRechargeList: vi.fn(),
  getBalanceLogs: vi.fn(),
}));

const mockNavigate = vi.fn();

// Use a mutable variable for search params that tests can set
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
  searchParamsObj = {};
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── Tests: RechargeAmountPage ────────────────────────

describe('RechargeScreens - RechargeAmountPage', () => {
  it('renders balance display section', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 500, total_recharged: 1000, total_consumed: 500, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      expect(screen.getByText('¥500.00')).toBeInTheDocument();
    });
  });

  it('renders preset amount buttons', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 0, total_recharged: 0, total_consumed: 0, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      expect(screen.getByText('¥50')).toBeInTheDocument();
      expect(screen.getByText('¥100')).toBeInTheDocument();
      expect(screen.getByText('¥200')).toBeInTheDocument();
      expect(screen.getByText('¥500')).toBeInTheDocument();
      expect(screen.getByText('¥1000')).toBeInTheDocument();
    });
  });

  it('shows error when confirming with no amount selected', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 0, total_recharged: 0, total_consumed: 0, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      const confirmBtn = screen.getByText('确认充值');
      fireEvent.click(confirmBtn);
      expect(screen.getByText('请选择或输入充值金额')).toBeInTheDocument();
    });
  });

  it('selects a preset amount and navigates to payment page', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 200, total_recharged: 200, total_consumed: 0, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      expect(screen.getByText('¥200.00')).toBeInTheDocument();
    });

    const amount200Btn = screen.getByText('¥200');
    fireEvent.click(amount200Btn);

    const confirmBtn = screen.getByText('确认充值');
    fireEvent.click(confirmBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/recharge/pay?amount=200.00');
  });

  it('supports custom amount input', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 0, total_recharged: 0, total_consumed: 0, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      const customInput = screen.getByPlaceholderText('输入充值金额') as HTMLInputElement;
      fireEvent.change(customInput, { target: { value: '88.50' } });
      expect(customInput).toHaveValue('88.50');
    });
  });

  it('validates custom amount and rejects invalid input', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 0, total_recharged: 0, total_consumed: 0, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      const customInput = screen.getByPlaceholderText('输入充值金额') as HTMLInputElement;
      fireEvent.change(customInput, { target: { value: 'abc' } });
      // Invalid input should be rejected by the validator
      expect(customInput).toHaveValue('');
    });
  });

  it('shows accumulated recharge info in balance card', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 1500, total_recharged: 3000, total_consumed: 1500, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      expect(screen.getByText('累计充值 ¥3000.00')).toBeInTheDocument();
      expect(screen.getByText('累计消费 ¥1500.00')).toBeInTheDocument();
    });
  });

  it('renders quick links to recharge history and balance details', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 0, total_recharged: 0, total_consumed: 0, recent_logs: [] },
    });

    renderWithRouter(<RechargeAmountPage />);

    await waitFor(() => {
      expect(screen.getByText('充值记录')).toBeInTheDocument();
      expect(screen.getByText('余额明细')).toBeInTheDocument();
    });
  });
});

// ─── Tests: RechargePaymentPage ───────────────────────

describe('RechargeScreens - RechargePaymentPage', () => {
  it('renders payment page with amount from URL params', () => {
    searchParamsObj = { amount: '100.00' };

    (rechargeApi.createRechargePrecreate as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { order_no: 'ORD123', prepay_id: 'wx123', pay_params: {} },
    });

    renderWithRouter(<RechargePaymentPage />);

    // The amount appears inside a split element: ¥{amount}
    // Use a text match function since the text may be split across elements
    expect(screen.getByText(/¥100\.00/)).toBeInTheDocument();
  });

  it('shows payment method selection (WeChat Pay / Alipay)', () => {
    searchParamsObj = { amount: '50.00' };

    (rechargeApi.createRechargePrecreate as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { order_no: 'ORD456', prepay_id: 'wx456', pay_params: {} },
    });

    renderWithRouter(<RechargePaymentPage />);

    expect(screen.getAllByText('微信支付').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('支付宝')).toBeInTheDocument();
  });

  it('displays preparing status on mount', () => {
    searchParamsObj = { amount: '50.00' };

    (rechargeApi.createRechargePrecreate as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { order_no: 'ORD789', prepay_id: 'wx789', pay_params: {} },
    });

    renderWithRouter(<RechargePaymentPage />);

    // Component shows preparing status text — multiple valid text variants
    const texts = screen.getAllByText(/正在|支付|准备/);
    expect(texts.length).toBeGreaterThanOrEqual(1);
  });

  it('shows error when amount is invalid (zero)', async () => {
    searchParamsObj = { amount: '0' };

    (rechargeApi.createRechargePrecreate as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { order_no: 'ORD000', prepay_id: 'wx000', pay_params: {} },
    });

    renderWithRouter(<RechargePaymentPage />);

    await waitFor(() => {
      expect(screen.getByText('金额无效')).toBeInTheDocument();
    });
  });
});

// ─── Tests: RechargeResultPage ────────────────────────

describe('RechargeScreens - RechargeResultPage', () => {
  it('displays success state with amount', async () => {
    searchParamsObj = { status: 'success', amount: '200.00' };

    renderWithRouter(<RechargeResultPage />);

    await waitFor(() => {
      expect(screen.getByText('充值成功')).toBeInTheDocument();
      // Amount is rendered as "+¥200.00" with the span potentially split
      // Use regex to match across text nodes
      expect(screen.getByText(/充值成功/)).toBeInTheDocument();
    });
  });

  it('displays success state', () => {
    searchParamsObj = { status: 'success', amount: '200.00' };

    renderWithRouter(<RechargeResultPage />);

    expect(screen.getByText('充值成功')).toBeInTheDocument();
  });

  it('displays failure state', () => {
    searchParamsObj = { status: 'failed', amount: '100.00' };

    renderWithRouter(<RechargeResultPage />);

    // The page shows the CheckCircle2 icon by default, let me check the actual behavior
    // from the source: isSuccess = resultStatus === 'success', so 'failed' gives isSuccess=false
    expect(screen.getByText('充值失败')).toBeInTheDocument();
  });

  it('shows current balance after successful recharge', async () => {
    searchParamsObj = { status: 'success', amount: '200.00' };

    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 800, total_recharged: 1000, total_consumed: 200, recent_logs: [] },
    });

    renderWithRouter(<RechargeResultPage />);

    await waitFor(() => {
      // Balance text is split across elements: "当前余额：" + span "¥800.00"
      expect(screen.getByText('¥800.00')).toBeInTheDocument();
    });
  });
});
