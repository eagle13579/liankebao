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

import NotificationsScreen from '../screens/NotificationsScreen';

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/notifications')) {
      return Promise.resolve({
        code: 200,
        data: [
          { id: 1, title: '订单通知', content: '您的订单已发货', is_read: false, created_at: new Date().toISOString(), type: 'order' },
          { id: 2, title: '系统消息', content: '欢迎使用链客宝', is_read: true, created_at: new Date(Date.now() - 86400000).toISOString(), type: 'system' },
          { id: 3, title: '推广通知', content: '您有新的分润到账', is_read: false, created_at: new Date(Date.now() - 3600000).toISOString(), type: 'promotion' },
        ],
      });
    }
    return Promise.resolve({ code: 200, data: null });
  });
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── Smoke Tests ──────────────────────────────────────

describe('NotificationsScreen (消息中心) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('消息中心')).toBeInTheDocument();
    });
  });

  it('renders notification items from API', async () => {
    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('订单通知')).toBeInTheDocument();
      expect(screen.getByText('系统消息')).toBeInTheDocument();
      expect(screen.getByText('推广通知')).toBeInTheDocument();
    });
  });

  it('renders notification content', async () => {
    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('您的订单已发货')).toBeInTheDocument();
    });
  });

  it('shows unread count indicator', async () => {
    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('2条未读')).toBeInTheDocument();
    });
  });

  it('renders relative timestamps', async () => {
    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      // The first notification was just created so it shows "刚刚"
      expect(screen.getByText('刚刚')).toBeInTheDocument();
    });
  });

  it('shows loading state initially', () => {
    mockGet.mockReturnValue(new Promise(() => {}));

    renderWithRouter(<NotificationsScreen />);
    expect(screen.getByText('加载消息中...')).toBeInTheDocument();
  });

  it('shows empty state when no notifications', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/notifications')) {
        return Promise.resolve({ code: 200, data: [] });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('暂无消息')).toBeInTheDocument();
    });
  });
});

// ─── Interaction Tests ────────────────────────────────

describe('NotificationsScreen (消息中心) - Interaction Tests', () => {
  it('navigates back on back button click', async () => {
    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      const backBtn = document.querySelector('header button');
      if (backBtn) fireEvent.click(backBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  it('marks notification as read when clicked', async () => {
    mockPut.mockResolvedValue({ code: 200 });

    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      // Click on the first notification (unread)
      const notificationTitle = screen.getByText('订单通知');
      fireEvent.click(notificationTitle);
    });

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith('/api/notifications/1/read', {});
    });
  });
});

// ─── Edge Cases ────────────────────────────────────────

describe('NotificationsScreen (消息中心) - Edge Cases', () => {
  it('handles API failure gracefully', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/notifications')) {
        return Promise.reject(new Error('网络错误'));
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument();
    });
  });

  it('handles empty data from API', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/notifications')) {
        return Promise.resolve({ code: 200, message: '获取通知失败' });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<NotificationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('获取通知失败')).toBeInTheDocument();
    });
  });
});
