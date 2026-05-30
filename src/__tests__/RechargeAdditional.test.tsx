import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { RechargeHistoryPage, BalanceDetailPage } from '../screens/RechargeScreens';
import * as rechargeApi from '../api/recharge';

// ─── Mocks ─────────────────────────────────────────────

vi.mock('../api/recharge', () => ({
  getRechargeBalance: vi.fn(),
  getRechargeList: vi.fn(),
  getBalanceLogs: vi.fn(),
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
  searchParamsObj = {};

  // Default mocks for RechargeHistoryPage
  (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
    code: 0,
    data: { balance: 1500, total_recharged: 3000, total_consumed: 1500, recent_logs: [] },
  });
  (rechargeApi.getRechargeList as ReturnType<typeof vi.fn>).mockResolvedValue({
    code: 0,
    data: {
      total: 3,
      items: [
        { id: 1, amount: 500, type: 'recharge', status: 'success', description: '账户充值', created_at: '2025-05-28T10:00:00Z' },
        { id: 2, amount: 200, type: 'consume', status: 'success', description: '购买商品', created_at: '2025-05-27T14:00:00Z' },
        { id: 3, amount: 300, type: 'recharge', status: 'success', description: '账户充值', created_at: '2025-05-26T08:00:00Z' },
      ],
    },
  });
  (rechargeApi.getBalanceLogs as ReturnType<typeof vi.fn>).mockResolvedValue({
    code: 0,
    data: {
      total: 2,
      items: [
        { id: 1, amount: 500, type: 'recharge', description: '余额充值', created_at: '2025-05-28T10:00:00Z' },
        { id: 2, amount: 200, type: 'consume', description: '购买商品 - 智能健康手表 S3', created_at: '2025-05-27T14:00:00Z' },
      ],
    },
  });
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── Tests: RechargeHistoryPage ──────────────────────

describe('RechargeHistoryPage (充值记录) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<RechargeHistoryPage />);

    await waitFor(() => {
      expect(screen.getByText('充值记录')).toBeInTheDocument();
    });
  });

  it('renders balance summary card', async () => {
    renderWithRouter(<RechargeHistoryPage />);

    await waitFor(() => {
      // ¥1500.00 appears for both balance and total_consumed
      const balanceItems = screen.getAllByText('¥1500.00');
      expect(balanceItems.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders accumulated stats', async () => {
    renderWithRouter(<RechargeHistoryPage />);

    await waitFor(() => {
      // Component shows "本月充值" and "本月消费" as labels, amounts in separate elements
      expect(screen.getByText('本月充值')).toBeInTheDocument();
      expect(screen.getByText('本月消费')).toBeInTheDocument();
      expect(screen.getByText('¥3000.00')).toBeInTheDocument();
    });
  });

  it('renders recharge list items', async () => {
    renderWithRouter(<RechargeHistoryPage />);

    await waitFor(() => {
      // Component renders formatAmount and platform info, not description
      expect(screen.getByText('¥500.00')).toBeInTheDocument();
      expect(screen.getByText('¥200.00')).toBeInTheDocument();
    });
  });

  it('shows loading skeletons while fetching', () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    (rechargeApi.getRechargeList as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<RechargeHistoryPage />);
    const skeletons = document.querySelectorAll('.skeleton');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows empty state when no records', async () => {
    (rechargeApi.getRechargeList as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { total: 0, items: [] },
    });

    renderWithRouter(<RechargeHistoryPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无充值记录')).toBeInTheDocument();
    });
  });
});

describe('RechargeHistoryPage (充值记录) - Interaction Tests', () => {
  it('navigates back when clicking back button', async () => {
    renderWithRouter(<RechargeHistoryPage />);

    await waitFor(() => {
      const backBtn = document.querySelector('header button');
      if (backBtn) fireEvent.click(backBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });
});

describe('RechargeHistoryPage (充值记录) - Edge Cases', () => {
  it('handles API error gracefully', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('网络错误'));

    renderWithRouter(<RechargeHistoryPage />);

    // Should still render without crashing
    await waitFor(() => {
      expect(screen.getByText('充值记录')).toBeInTheDocument();
    });
  });
});

// ─── Tests: BalanceDetailPage ─────────────────────────

describe('BalanceDetailPage (余额明细) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('余额明细')).toBeInTheDocument();
    });
  });

  it('renders current balance from API', async () => {
    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('¥1500.00')).toBeInTheDocument();
    });
  });

  it('renders balance log items', async () => {
    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('余额充值')).toBeInTheDocument();
      expect(screen.getByText('购买商品 - 智能健康手表 S3')).toBeInTheDocument();
    });
  });

  it('renders income/expense indicators', async () => {
    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      // Recharge should show + and Consume should show -
      expect(screen.getByText('充值')).toBeInTheDocument();
      expect(screen.getByText('消费')).toBeInTheDocument();
    });
  });

  it('shows loading skeletons while fetching', () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    (rechargeApi.getBalanceLogs as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    renderWithRouter(<BalanceDetailPage />);
    const skeletons = document.querySelectorAll('.skeleton');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows empty state when no logs', async () => {
    (rechargeApi.getBalanceLogs as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { total: 0, items: [] },
    });

    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无变动记录')).toBeInTheDocument();
    });
  });
});

describe('BalanceDetailPage (余额明细) - Interaction Tests', () => {
  it('navigates back when clicking back button', async () => {
    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      const backBtn = document.querySelector('header button');
      if (backBtn) fireEvent.click(backBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  it('loads more logs when clicking 加载更多', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { balance: 1500, total_recharged: 3000, total_consumed: 1500, recent_logs: [] },
    });
    (rechargeApi.getBalanceLogs as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 0,
      data: { total: 5, items: [
        { id: 1, amount: 500, type: 'recharge', description: '余额充值', created_at: '2025-05-28T10:00:00Z' },
        { id: 2, amount: 200, type: 'consume', description: '消费', created_at: '2025-05-27T14:00:00Z' },
      ]},
    });

    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      const loadMoreBtn = screen.getByText('加载更多');
      expect(loadMoreBtn).toBeInTheDocument();
      fireEvent.click(loadMoreBtn);
    });

    await waitFor(() => {
      expect(rechargeApi.getBalanceLogs).toHaveBeenCalledTimes(2);
    });
  });
});

describe('BalanceDetailPage (余额明细) - Edge Cases', () => {
  it('handles API error gracefully', async () => {
    (rechargeApi.getRechargeBalance as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('网络错误'));

    renderWithRouter(<BalanceDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('余额明细')).toBeInTheDocument();
    });
  });
});
