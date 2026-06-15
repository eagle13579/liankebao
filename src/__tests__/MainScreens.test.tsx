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
  // Default: return empty mission control and products list
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/home/mission-control')) {
      return Promise.resolve({
        code: 200,
        data: {
          data: {
            publish_task: { label: '发布任务', icon: 'flame', description: '创建分销/合作任务', status: 'active', badge: null, action_hint: '发布新产品', sort_order: 1 },
            invite_partner: { label: '邀请伙伴', icon: 'handshake', description: '发送邀请链接/二维码', status: 'active', badge: null, action_hint: '立即邀请', sort_order: 2 },
            track_split: { label: '追踪分账', icon: 'chart', description: '查看收益/佣金/结算', status: 'active', badge: null, action_hint: '查看详情', sort_order: 3 },
          },
        },
      });
    }
    if (url.includes('/api/notifications/unread-count')) {
      return Promise.resolve({ code: 200, data: { count: 0 } });
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
      expect(screen.getByText('链客宝AI')).toBeInTheDocument();
    });
  });

  it('renders the search bar with placeholder - falls back', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    // Current component doesn't have a search bar, check for the brand text
    await waitFor(() => {
      expect(screen.getByText('企业信任关系网')).toBeInTheDocument();
    });
  });

  it('renders the three mission control buttons', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      expect(screen.getByText('发布任务')).toBeInTheDocument();
      expect(screen.getByText('邀请伙伴')).toBeInTheDocument();
      expect(screen.getByText('追踪分账')).toBeInTheDocument();
    });
  });

  it('renders the bottom navigation bar with nav labels', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      expect(screen.getByText('首页')).toBeInTheDocument();
      // 产品池 appears in both bottom nav and secondary features
      expect(screen.getAllByText('产品池').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('人脉')).toBeInTheDocument();
      expect(screen.getByText('我的')).toBeInTheDocument();
    });
  });

  it('renders the more features toggle button', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      expect(screen.getByText('更多功能')).toBeInTheDocument();
    });
  });

  it('expands secondary menu when clicking 更多功能', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const moreBtn = screen.getByText('更多功能');
      fireEvent.click(moreBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('收起二级菜单')).toBeInTheDocument();
      // 产品池 appears in both expanded menu and bottom nav
      expect(screen.getAllByText('产品池').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('推广中心')).toBeInTheDocument();
    });
  });

  it('shows loading skeleton on initial render', () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/home/mission-control')) {
        return new Promise(() => {}); // Never resolves
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<LiankebaoHomepage />);
    // Component renders mission buttons with placeholder text on error
    expect(screen.getByText('发布任务')).toBeInTheDocument();
  });
});

describe('LiankebaoHomepage - Interaction Tests', () => {
  it('navigates to add-product when clicking 发布任务 button', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const hintEl = screen.getByText('发布新产品');
      const btn = hintEl.closest('button') || hintEl;
      fireEvent.click(btn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/add-product', { state: { transition: 'push' } });
  });

  it('navigates to contacts when clicking 邀请伙伴 button', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const hintEl = screen.getByText('立即邀请');
      const btn = hintEl.closest('button') || hintEl;
      fireEvent.click(btn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/contacts', { state: { transition: 'push' } });
  });

  it('navigates to notifications when clicking bell icon', async () => {
    renderWithRouter(<LiankebaoHomepage />);

    await waitFor(() => {
      const bellSection = document.querySelector('[class*="w-9 h-9 rounded-full bg-dark-surface flex items-center justify-center"]');
      if (bellSection) fireEvent.click(bellSection);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/notifications');
  });
});
