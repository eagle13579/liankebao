import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Mock api
const mockGet = vi.fn();
vi.mock('../api/client', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: vi.fn(),
    put: vi.fn(),
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

import { ProductPool, PromotionCenter } from '../screens/MainScreens';

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/products')) {
      return Promise.resolve({
        code: 200,
        data: {
          total: 2,
          items: [
            { id: 1, name: '智能健康手表 S3', price: 1299, earn_per_share: 10, category: '大健康', stock: 100, status: 'active', owner_id: 1, images: '', description: '健康手表' },
            { id: 2, name: '高端商务茶礼套装', price: 688, earn_per_share: 15, category: '消费品', stock: 50, status: 'active', owner_id: 1, images: '', description: '茶礼套装' },
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

// ─── ProductPool Tests ─────────────────────────────────

describe('ProductPool (产品池) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      // 产品池 appears in both header and bottom nav
      const titles = screen.getAllByText('产品池');
      expect(titles.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders search input with placeholder', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('搜产品、搜企业、搜品类');
      expect(searchInput).toBeInTheDocument();
    });
  });

  it('renders product items from API', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
      expect(screen.getByText('高端商务茶礼套装')).toBeInTheDocument();
    });
  });

  it('renders category tabs', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      expect(screen.getByText('全部')).toBeInTheDocument();
      expect(screen.getByText('大健康')).toBeInTheDocument();
      expect(screen.getByText('企业服务')).toBeInTheDocument();
    });
  });

  it('renders price on product cards', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      expect(screen.getByText('¥1299.00')).toBeInTheDocument();
      expect(screen.getByText('¥688.00')).toBeInTheDocument();
    });
  });

  it('shows loading skeleton while fetching products', () => {
    mockGet.mockReturnValue(new Promise(() => {}));

    renderWithRouter(<ProductPool />);
    const skeletons = document.querySelectorAll('.skeleton');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows empty state when no products exist', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/products')) {
        return Promise.resolve({ code: 200, data: { total: 0, items: [] } });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      expect(screen.getByText('暂无产品')).toBeInTheDocument();
    });
  });
});

describe('ProductPool (产品池) - Interaction Tests', () => {
  it('navigates to product detail when clicking a product card', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      const product = screen.getByText('智能健康手表 S3');
      fireEvent.click(product);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/product-detail', {
      state: { transition: 'push', productId: 1 },
    });
  });

  it('filters by category when clicking category tab', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      const healthTab = screen.getByText('大健康');
      fireEvent.click(healthTab);
    });

    await waitFor(() => {
      const calls = mockGet.mock.calls.filter((c: any) => c[0].includes('/api/products'));
      const lastCall = calls[calls.length - 1][0] as string;
      expect(lastCall).toContain('category=' + encodeURIComponent('大健康'));
    });
  });

  it('updates search input when typing', async () => {
    renderWithRouter(<ProductPool />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('搜产品、搜企业、搜品类') as HTMLInputElement;
      fireEvent.change(searchInput, { target: { value: '手表' } });
      expect(searchInput.value).toBe('手表');
    });
  });
});

// ─── PromotionCenter Tests ─────────────────────────────

describe('PromotionCenter (推广中心) - Smoke Tests', () => {
  it('renders the page header with title', () => {
    renderWithRouter(<PromotionCenter />);

    expect(screen.getByText('推广中心')).toBeInTheDocument();
  });

  it('renders user profile section with name', () => {
    renderWithRouter(<PromotionCenter />);

    expect(screen.getByText('林峰')).toBeInTheDocument();
    expect(screen.getByText('铂金会员')).toBeInTheDocument();
  });

  it('renders quick action cards', () => {
    renderWithRouter(<PromotionCenter />);

    expect(screen.getByText('我的订单')).toBeInTheDocument();
    expect(screen.getByText('分享海报')).toBeInTheDocument();
    expect(screen.getByText('我的下级')).toBeInTheDocument();
    expect(screen.getByText('推广教程')).toBeInTheDocument();
    expect(screen.getByText('合伙人政策')).toBeInTheDocument();
    expect(screen.getByText('会员中心')).toBeInTheDocument();
    expect(screen.getByText('我的产品')).toBeInTheDocument();
    expect(screen.getByText('上架新品')).toBeInTheDocument();
  });

  it('renders hot products section', () => {
    renderWithRouter(<PromotionCenter />);

    expect(screen.getByText('本月热推产品')).toBeInTheDocument();
    expect(screen.getByText('旗舰版智能健康手表 S3')).toBeInTheDocument();
  });

  it('renders earnings summary section', () => {
    renderWithRouter(<PromotionCenter />);

    expect(screen.getByText('今日收入 (元)')).toBeInTheDocument();
  });
});

describe('PromotionCenter (推广中心) - Interaction Tests', () => {
  it('navigates to subordinates page when clicking 我的下级', () => {
    renderWithRouter(<PromotionCenter />);

    const subordinateBtn = screen.getByText('我的下级');
    fireEvent.click(subordinateBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/subordinates', { state: { transition: 'push' } });
  });

  it('navigates to orders page when clicking 我的订单', () => {
    renderWithRouter(<PromotionCenter />);

    const ordersBtn = screen.getByText('我的订单');
    fireEvent.click(ordersBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/my-orders', { state: { transition: 'push' } });
  });

  it('navigates to tutorial page when clicking 推广教程', () => {
    renderWithRouter(<PromotionCenter />);

    const tutorialBtn = screen.getByText('推广教程');
    fireEvent.click(tutorialBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/promotion-tutorial', { state: { transition: 'push' } });
  });

  it('navigates to partner policy page when clicking 合伙人政策', () => {
    renderWithRouter(<PromotionCenter />);

    const policyBtn = screen.getByText('合伙人政策');
    fireEvent.click(policyBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/partner-policy', { state: { transition: 'push' } });
  });

  it('navigates to membership page when clicking 会员中心', () => {
    renderWithRouter(<PromotionCenter />);

    const membershipBtn = screen.getByText('会员中心');
    fireEvent.click(membershipBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/membership', { state: { transition: 'push' } });
  });

  it('navigates to my-products page when clicking 我的产品', () => {
    renderWithRouter(<PromotionCenter />);

    const myProductsBtn = screen.getByText('我的产品');
    fireEvent.click(myProductsBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/my-products', { state: { transition: 'push' } });
  });

  it('navigates to add-product page when clicking 上架新品', () => {
    renderWithRouter(<PromotionCenter />);

    const addProductBtn = screen.getByText('上架新品');
    fireEvent.click(addProductBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/add-product', { state: { transition: 'push' } });
  });
});
