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
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import ContactsPage from '../pages/ContactsPage';

beforeEach(() => {
  vi.clearAllMocks();

  // Default: return contacts list + tags
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/contacts/tags')) {
      return Promise.resolve({
        code: 200,
        data: { tags: ['VIP', '潜在客户', '合作伙伴'] },
      });
    }
    if (url.includes('/api/contacts')) {
      return Promise.resolve({
        code: 200,
        data: {
          total: 3,
          items: [
            { id: 1, name: '张三', phone: '13800138001', company: '科技有限公司', position: 'CEO', tags: ['VIP'], created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' },
            { id: 2, name: '李四', phone: '13900139002', company: '贸易有限公司', position: '经理', tags: ['潜在客户'], created_at: '2025-02-01T00:00:00Z', updated_at: '2025-02-01T00:00:00Z' },
            { id: 3, name: '王五', phone: '13700137003', company: '咨询服务公司', position: '总监', tags: ['合作伙伴'], created_at: '2025-03-01T00:00:00Z', updated_at: '2025-03-01T00:00:00Z' },
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

describe('ContactsPage (企业列表页) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      expect(screen.getByText('人脉管理')).toBeInTheDocument();
    });
  });

  it('renders the search input with correct placeholder', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('搜索姓名、电话、公司...');
      expect(searchInput).toBeInTheDocument();
    });
  });

  it('renders import button', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      expect(screen.getByText('导入')).toBeInTheDocument();
    });
  });

  it('renders contacts list from API', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
      expect(screen.getByText('李四')).toBeInTheDocument();
      expect(screen.getByText('王五')).toBeInTheDocument();
    });
  });

  it('renders company names for contacts', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      // Company name may be combined with position text like "科技有限公司 · CEO"
      expect(screen.getByText((content) => content.includes('科技有限公司'))).toBeInTheDocument();
      expect(screen.getByText((content) => content.includes('贸易有限公司'))).toBeInTheDocument();
      expect(screen.getByText((content) => content.includes('咨询服务公司'))).toBeInTheDocument();
    });
  });

  it('renders view mode toggle buttons', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      // Should have card and table view options
      const viewButtons = document.querySelectorAll('[class*="rounded-lg"][class*="p-1.5"]');
      expect(viewButtons.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('shows total contact count', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      expect(screen.getByText((content) => content.includes('共') && content.includes('3') && content.includes('联系人'))).toBeInTheDocument();
    });
  });
});

describe('ContactsPage (企业列表页) - Interaction Tests', () => {
  it('filters contacts when typing search and pressing Enter', async () => {
    // Override mock for this test to simulate search
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/contacts/tags')) {
        return Promise.resolve({ code: 200, data: { tags: ['VIP', '潜在客户'] } });
      }
      if (url.includes('/api/contacts')) {
        if (url.includes('search=张三')) {
          return Promise.resolve({
            code: 200,
            data: { total: 1, items: [{ id: 1, name: '张三', phone: '13800138001', company: '科技有限公司', position: 'CEO', tags: ['VIP'], created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' }] },
          });
        }
        // Default: return empty for initial load
        return Promise.resolve({
          code: 200,
          data: { total: 3, items: [
            { id: 1, name: '张三', phone: '13800138001', company: '科技有限公司', position: 'CEO', tags: ['VIP'], created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' },
          ]},
        });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<ContactsPage />);

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
    });

    // Now type search and press Enter
    const searchInput = screen.getByPlaceholderText('搜索姓名、电话、公司...');
    fireEvent.change(searchInput, { target: { value: '张三' } });
    fireEvent.keyDown(searchInput, { key: 'Enter' });

    // After search, should still show the result
    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
    });
  });

  it('navigates to import page when clicking import button', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      const importBtn = screen.getByText('导入');
      fireEvent.click(importBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/contacts/import', { state: { transition: 'push' } });
  });

  it('navigates back when clicking back button', async () => {
    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      // Find the back button - it's the first button in the header that wraps a chevron-left icon
      const backBtn = document.querySelector('header button');
      if (backBtn) fireEvent.click(backBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  it('shows empty state when no contacts exist', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/contacts')) {
        return Promise.resolve({
          code: 200,
          data: { total: 0, items: [] },
        });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无联系人')).toBeInTheDocument();
    });
  });

  it('shows error state on API failure and retry works', async () => {
    // First call fails
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/contacts')) {
        return Promise.reject(new Error('网络错误'));
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<ContactsPage />);

    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument();
    });

    // Now make the retry succeed
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/contacts')) {
        return Promise.resolve({
          code: 200,
          data: { total: 1, items: [{ id: 1, name: '张三', phone: '13800138001', company: '科技有限公司', position: 'CEO', tags: [], created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z' }] },
        });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    // Click retry button
    const retryBtn = screen.getByText('重新加载');
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument();
    });
  });
});
