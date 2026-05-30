import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

// Mock api
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

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import { PostNeed } from '../screens/PostNeedScreen';
import { NeedDetail } from '../screens/SupplyDemandScreens';

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, 'location', {
    value: { pathname: '/supply-demand/1' },
    writable: true,
  });

  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/needs/1')) {
      return Promise.resolve({
        code: 200,
        data: {
          id: 1, user_id: 1, title: '寻找大健康产品供应商', description: '需要优质保健品',
          category: '大健康', budget: '10万-50万', region: '北京', status: 'open',
          contact_name: '赵总', contact_phone: '13800138000',
          created_at: '2025-05-28T08:00:00Z', updated_at: '2025-05-28T08:00:00Z',
          user: { id: 1, name: '赵总', company: '健康科技有限公司' },
        },
      });
    }
    return Promise.resolve({ code: 200, data: null });
  });
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── PostNeed Tests ───────────────────────────────────

describe('PostNeed (发布需求) - Smoke Tests', () => {
  it('renders the page header with title', () => {
    renderWithRouter(<PostNeed />);

    expect(screen.getByText('发布需求')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderWithRouter(<PostNeed />);

    expect(screen.getByText('填写商机信息，快速对接合作伙伴')).toBeInTheDocument();
  });

  it('renders all form sections', () => {
    renderWithRouter(<PostNeed />);

    expect(screen.getByText('需求标题 *')).toBeInTheDocument();
    expect(screen.getByText('需求品类')).toBeInTheDocument();
    expect(screen.getByText('需求描述')).toBeInTheDocument();
    expect(screen.getByText('预算范围')).toBeInTheDocument();
    expect(screen.getByText('所在地区')).toBeInTheDocument();
    expect(screen.getByText('联系方式')).toBeInTheDocument();
  });

  it('renders input fields with correct placeholders', () => {
    renderWithRouter(<PostNeed />);

    expect(screen.getByPlaceholderText('例如：寻找大健康产品供应链合作伙伴')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请详细描述您的需求，包括具体要求、期望合作方式等...')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('面议')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('如：北京')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('联系人 *')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('联系电话')).toBeInTheDocument();
  });

  it('renders category selection buttons', () => {
    renderWithRouter(<PostNeed />);

    expect(screen.getByText('大健康')).toBeInTheDocument();
    expect(screen.getByText('企业服务')).toBeInTheDocument();
    expect(screen.getByText('科技产品')).toBeInTheDocument();
    expect(screen.getByText('教育培训')).toBeInTheDocument();
    expect(screen.getByText('消费品')).toBeInTheDocument();
  });

  it('renders submit button', () => {
    renderWithRouter(<PostNeed />);

    expect(screen.getByText('确认发布需求')).toBeInTheDocument();
  });
});

describe('PostNeed (发布需求) - Interaction Tests', () => {
  it('allows typing in title field', () => {
    renderWithRouter(<PostNeed />);

    const titleInput = screen.getByPlaceholderText('例如：寻找大健康产品供应链合作伙伴') as HTMLInputElement;
    fireEvent.change(titleInput, { target: { value: '新需求测试' } });
    expect(titleInput.value).toBe('新需求测试');
  });

  it('allows selecting a category', () => {
    renderWithRouter(<PostNeed />);

    const healthCategory = screen.getByText('大健康');
    fireEvent.click(healthCategory);
    // Category should now be selected (rose bg)
    expect(healthCategory.className).toContain('rose');
  });

  it('submits form and navigates on success', async () => {
    mockPost.mockResolvedValue({ code: 200, data: {} });

    renderWithRouter(<PostNeed />);

    // Fill required fields
    const titleInput = screen.getByPlaceholderText('例如：寻找大健康产品供应链合作伙伴');
    fireEvent.change(titleInput, { target: { value: '测试需求' } });
    const contactInput = screen.getByPlaceholderText('联系人 *');
    fireEvent.change(contactInput, { target: { value: '测试人' } });

    const submitBtn = screen.getByText('确认发布需求');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled();
    });

    expect(mockNavigate).toHaveBeenCalledWith('/supply-demand', { state: { transition: 'push_back' } });
  });

  it('shows error when title is empty', () => {
    renderWithRouter(<PostNeed />);

    const submitBtn = screen.getByText('确认发布需求');
    fireEvent.click(submitBtn);

    expect(screen.getByText('请填写需求标题')).toBeInTheDocument();
  });

  it('shows error when contact name is empty but title is filled', () => {
    renderWithRouter(<PostNeed />);

    const titleInput = screen.getByPlaceholderText('例如：寻找大健康产品供应链合作伙伴');
    fireEvent.change(titleInput, { target: { value: '测试需求' } });

    const submitBtn = screen.getByText('确认发布需求');
    fireEvent.click(submitBtn);

    expect(screen.getByText('请填写联系人')).toBeInTheDocument();
  });

  it('shows submitting state while posting', async () => {
    mockPost.mockReturnValue(new Promise(() => {}));

    renderWithRouter(<PostNeed />);

    const titleInput = screen.getByPlaceholderText('例如：寻找大健康产品供应链合作伙伴');
    fireEvent.change(titleInput, { target: { value: '测试' } });
    const contactInput = screen.getByPlaceholderText('联系人 *');
    fireEvent.change(contactInput, { target: { value: '测试人' } });

    const submitBtn = screen.getByText('确认发布需求');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('发布中...')).toBeInTheDocument();
    });
  });
});

// ─── NeedDetail Tests ─────────────────────────────────

describe('NeedDetail (需求详情) - Smoke Tests', () => {
  it('renders loading state initially', () => {
    mockGet.mockReturnValue(new Promise(() => {}));

    renderWithRouter(<NeedDetail />);
    expect(document.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
  });

  it('renders need title from API', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('寻找大健康产品供应商')).toBeInTheDocument();
    });
  });

  it('renders need description', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('需要优质保健品')).toBeInTheDocument();
    });
  });

  it('renders contact name', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('赵总')).toBeInTheDocument();
    });
  });

  it('renders budget information', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('10万-50万')).toBeInTheDocument();
    });
  });

  it('renders region information', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('北京')).toBeInTheDocument();
    });
  });

  it('renders status badge (开放中)', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('开放中')).toBeInTheDocument();
    });
  });

  it('renders category tag', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('大健康')).toBeInTheDocument();
    });
  });

  it('renders 查看联系方式 button', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('查看联系方式')).toBeInTheDocument();
    });
  });

  it('renders 返回需求大厅 button', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('返回需求大厅')).toBeInTheDocument();
    });
  });
});

describe('NeedDetail (需求详情) - Interaction Tests', () => {
  it('shows phone number when clicking 查看联系方式', async () => {
    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      const contactBtn = screen.getByText('查看联系方式');
      fireEvent.click(contactBtn);
    });

    await waitFor(() => {
      expect(screen.getByText('13800138000')).toBeInTheDocument();
    });
  });
});

describe('NeedDetail (需求详情) - Edge Cases', () => {
  it('shows not found when need does not exist', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/needs/1')) {
        return Promise.resolve({ code: 200 });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<NeedDetail />);

    await waitFor(() => {
      expect(screen.getByText('该需求已删除或不存在')).toBeInTheDocument();
    });
  });
});
