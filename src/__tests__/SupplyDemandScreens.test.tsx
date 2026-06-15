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
  },
}));

const mockNavigate = vi.fn();
const mockSearchParamsObj: Record<string, string> = {};

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

import { SupplyDemandHall } from '../screens/SupplyDemandScreens';

beforeEach(() => {
  vi.clearAllMocks();
  Object.keys(mockSearchParamsObj).forEach(k => delete mockSearchParamsObj[k]);

  // Default: return needs list
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/needs')) {
      return Promise.resolve({
        code: 200,
        data: {
          total: 3,
          page: 1,
          page_size: 20,
          items: [
            {
              id: 1, user_id: 1, title: '寻找大健康产品供应商', description: '需要优质保健品',
              category: '大健康', budget: '10万-50万', region: '北京', status: 'open',
              contact_name: '赵总', contact_phone: '13800138000',
              created_at: '2025-05-28T08:00:00Z', updated_at: '2025-05-28T08:00:00Z',
              user: { id: 1, name: '赵总', company: '健康科技有限公司' },
            },
            {
              id: 2, user_id: 2, title: '企业数字化转型服务需求', description: '需要ERP系统',
              category: '企业服务', budget: '20万-100万', region: '上海', status: 'open',
              contact_name: '钱经理', contact_phone: '13900139000',
              created_at: '2025-05-27T10:00:00Z', updated_at: '2025-05-27T10:00:00Z',
              user: { id: 2, name: '钱经理', company: '信息科技有限公司' },
            },
            {
              id: 3, user_id: 3, title: '急需编程培训课程', description: 'Python培训',
              category: '教育培训', budget: '5万', region: '深圳', status: 'closed',
              contact_name: '孙老师', contact_phone: '13700137000',
              created_at: '2025-05-25T14:00:00Z', updated_at: '2025-05-25T14:00:00Z',
              user: { id: 3, name: '孙老师', company: '教育咨询公司' },
            },
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

describe('SupplyDemandHall (供需匹配页) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getByText('需求大厅')).toBeInTheDocument();
      expect(screen.getByText('发现商机 · 精准对接')).toBeInTheDocument();
    });
  });

  it('renders the search input', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('搜索需求...');
      expect(searchInput).toBeInTheDocument();
    });
  });

  it('renders all category tabs', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getByText('全部')).toBeInTheDocument();
      expect(screen.getByText('大健康')).toBeInTheDocument();
      expect(screen.getByText('企业服务')).toBeInTheDocument();
      expect(screen.getByText('科技产品')).toBeInTheDocument();
      expect(screen.getByText('教育培训')).toBeInTheDocument();
      expect(screen.getByText('消费品')).toBeInTheDocument();
    });
  });

  it('renders need items from API', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getByText('寻找大健康产品供应商')).toBeInTheDocument();
      expect(screen.getByText('企业数字化转型服务需求')).toBeInTheDocument();
      expect(screen.getByText('急需编程培训课程')).toBeInTheDocument();
    });
  });

  it('renders status badges (开放中 / 已关闭)', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getAllByText('开放中').length).toBeGreaterThanOrEqual(2);
      expect(screen.getByText('已关闭')).toBeInTheDocument();
    });
  });

  it('renders category tags on need items', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getByText('大健康')).toBeInTheDocument();
      expect(screen.getByText('教育培训')).toBeInTheDocument();
    });
  });

  it('renders user names and company info', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getByText('赵总')).toBeInTheDocument();
      expect(screen.getByText('钱经理')).toBeInTheDocument();
      // Company name may be concatenated with separator
      expect(screen.getByText((content) => content.includes('健康科技有限公司'))).toBeInTheDocument();
      expect(screen.getByText((content) => content.includes('信息科技有限公司'))).toBeInTheDocument();
    });
  });

  it('renders the FAB (发布需求) button', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      // The FAB has a Plus icon and navigates to /supply-demand/post
      const fabBtn = document.querySelector('[class*="fixed bottom-24 right-5"]');
      expect(fabBtn).toBeInTheDocument();
    });
  });

  it('shows total needs count', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getByText(/共.*3.*条需求/)).toBeInTheDocument();
    });
  });

  it('shows loading skeleton while fetching', () => {
    mockGet.mockReturnValue(new Promise(() => {})); // Never resolves

    renderWithRouter(<SupplyDemandHall />);
    const skeletons = document.querySelectorAll('.skeleton');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

describe('SupplyDemandHall (供需匹配页) - Interaction Tests', () => {
  it('filters by category when clicking a category tab', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      const healthBtn = screen.getByText('大健康');
      fireEvent.click(healthBtn);
    });

    // Should fetch with category=大健康
    await waitFor(() => {
      const calls = mockGet.mock.calls.filter((c: any) => c[0].includes('/api/needs'));
      const lastCall = calls[calls.length - 1][0] as string;
      expect(lastCall).toContain('category=' + encodeURIComponent('大健康'));
    });
  });

  it('searches needs on Enter key press', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('搜索需求...');
      fireEvent.change(searchInput, { target: { value: 'ERP' } });
      fireEvent.keyDown(searchInput, { key: 'Enter' });
    });

    // Should call API with search=ERP
    await waitFor(() => {
      const calls = mockGet.mock.calls.filter((c: any) => c[0].includes('/api/needs'));
      const lastCall = calls[calls.length - 1][0] as string;
      expect(lastCall).toContain('search=' + encodeURIComponent('ERP'));
    });
  });

  it('navigates to need detail when clicking a need item', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      const needItem = screen.getByText('寻找大健康产品供应商');
      fireEvent.click(needItem);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/supply-demand/1', { state: { transition: 'push' } });
  });

  it('navigates to post need page when clicking FAB', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      const fabBtn = document.querySelector('[class*="fixed bottom-24 right-5"]');
      if (fabBtn) fireEvent.click(fabBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/supply-demand/post', { state: { transition: 'slide_up' } });
  });

  it('navigates back to home when clicking back button', async () => {
    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      const backBtn = document.querySelector('[class*="bg-white/20 text-white active:scale-90"]');
      if (backBtn) fireEvent.click(backBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/home');
  });

  it('shows empty state when no needs found', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/needs')) {
        return Promise.resolve({
          code: 200,
          data: { total: 0, page: 1, page_size: 20, items: [] },
        });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<SupplyDemandHall />);

    await waitFor(() => {
      expect(screen.getByText('暂无相关需求')).toBeInTheDocument();
      expect(screen.getByText('发布一条需求，让更多伙伴找到你')).toBeInTheDocument();
    });
  });
});
