import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Mock api
const mockGet = vi.fn();
vi.mock('../api/client', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: vi.fn(),
    saveToken: vi.fn(),
    loadToken: vi.fn(),
    removeToken: vi.fn(),
    track: vi.fn(),
  },
}));

const mockNavigate = vi.fn();
const mockWindowOpen = vi.fn();
vi.spyOn(window, 'open').mockImplementation(mockWindowOpen);

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { LiankebaoHomepage } from '../screens/MainScreens';

beforeEach(() => {
  vi.clearAllMocks();
  // Default: return empty products list
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/notifications/unread-count')) {
      return Promise.resolve({ code: 200, data: { count: 0 } });
    }
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

describe('LiankebaoHomepage - Smoke Tests', () => {
  it('renders the header with brand name', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      expect(screen.getByText('链客宝')).toBeInTheDocument();
    });
  });

  it('renders the search bar with placeholder', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('搜产品、搜企业、搜品类...');
      expect(searchInput).toBeInTheDocument();
    });
  });

  it('renders all feature cards (using getAllByText for duplicates)', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      // These feature card labels appear in the feature cards section
      // Some also appear in bottom nav - use getAllByText and check count >= 1
      expect(screen.getAllByText('产品池').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('推广中心')).toBeInTheDocument();
      expect(screen.getByText('我的订单')).toBeInTheDocument();
      // 数据洞察 appears in both feature cards and quick tools
      expect(screen.getAllByText('数据洞察').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders the bottom navigation bar with unique nav labels', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      expect(screen.getByText('首页')).toBeInTheDocument();
      expect(screen.getByText('我的')).toBeInTheDocument();
    });
  });

  it('renders the recommended products section', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      expect(screen.getByText('为您推荐')).toBeInTheDocument();
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
      expect(screen.getByText('高端商务茶礼套装')).toBeInTheDocument();
    });
  });

  it('renders the banner carousel', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      expect(screen.getByText('精选推荐')).toBeInTheDocument();
      expect(screen.getByText('VIP会员')).toBeInTheDocument();
    });
  });

  it('renders quick tool links (AI名片, GEO, etc.)', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      // These may appear in multiple places, use getAllByText
      expect(screen.getAllByText('AI名片').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('GEO').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('信任对接').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows loading skeleton while products are loading', () => {
    // Make the API promise never resolve for loading state
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/notifications/unread-count')) {
        return Promise.resolve({ code: 200, data: { count: 0 } });
      }
      if (url.includes('/api/products')) {
        return new Promise(() => {}); // Never resolves
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<LiankebaoHomepage />);
    // The loading skeleton should be rendered
    const skeletons = document.querySelectorAll('.skeleton');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

describe('LiankebaoHomepage - Interaction Tests', () => {
  it('navigates to product pool when clicking 产品池 feature card', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      // Feature cards are buttons with text labels - click the first button containing "产品池"
      const productPoolBtns = screen.getAllByText('产品池');
      // The feature card version should be inside a button
      const btn = productPoolBtns[0].closest('button') || productPoolBtns[0].parentElement;
      if (btn) fireEvent.click(btn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/product-pool', { state: { transition: 'push' } });
  });

  it('navigates to supply-demand page when clicking 信任对接 feature card', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const trustBtns = screen.getAllByText('信任对接');
      const btn = trustBtns[0].closest('button') || trustBtns[0].parentElement;
      if (btn) fireEvent.click(btn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/supply-demand', { state: { transition: 'push' } });
  });

  it('navigates to notifications page when clicking bell icon', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      // Bell icon is wrapped in a button with position relative
      const bellSection = document.querySelector('[class*="w-9 h-9 rounded-full bg-slate-50"]');
      if (bellSection) fireEvent.click(bellSection);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/notifications');
  });

  it('updates search input value when typing', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('搜产品、搜企业、搜品类...') as HTMLInputElement;
      fireEvent.change(searchInput, { target: { value: '健康手表' } });
      expect(searchInput.value).toBe('健康手表');
    });
  });

  it('navigates to product detail when clicking a product', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const product = screen.getByText('智能健康手表 S3');
      fireEvent.click(product);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/product-detail', {
      state: { transition: 'push', productId: 1 },
    });
  });

  it('navigates to more products page', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const moreBtn = screen.getByText('更多产品');
      fireEvent.click(moreBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/product-pool', { state: { transition: 'push' } });
  });

  it('opens external link for AI名片 quick tool', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const aiCardBtns = screen.getAllByText('AI名片');
      const btn = aiCardBtns[0].closest('[class*="flex items-center gap-2"]') || aiCardBtns[0].parentElement;
      if (btn) fireEvent.click(btn);
    });

    expect(mockWindowOpen).toHaveBeenCalledWith('http://localhost:8003', '_blank');
  });
});
