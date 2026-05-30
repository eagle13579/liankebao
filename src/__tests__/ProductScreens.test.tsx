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
    loadToken: vi.fn(() => ({ user: { id: 1 } })),
    removeToken: vi.fn(),
  },
}));

const mockNavigate = vi.fn();
const mockLocationState: Record<string, any> = {};

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: () => ({ state: mockLocationState }),
  };
});

import { ProductDetailPage, MyProducts, AddProduct } from '../screens/ProductScreens';

beforeEach(() => {
  vi.clearAllMocks();
  Object.keys(mockLocationState).forEach(k => delete mockLocationState[k]);
  mockLocationState.productId = 1;

  mockGet.mockImplementation((url: string) => {
    if (url.includes('/api/products/1')) {
      return Promise.resolve({
        code: 200,
        data: { id: 1, name: '智能健康手表 S3', price: 1299, earn_per_share: 10, category: '大健康', stock: 100, status: 'active', owner_id: 1, images: '', description: '健康手表' },
      });
    }
    if (url.includes('/api/products')) {
      return Promise.resolve({
        code: 200,
        data: { total: 2, items: [
          { id: 1, name: '智能健康手表 S3', price: 1299, earn_per_share: 10, category: '大健康', stock: 100, status: 'active', owner_id: 1, images: '', description: '健康手表' },
          { id: 2, name: '高端商务茶礼套装', price: 688, earn_per_share: 15, category: '消费品', stock: 50, status: 'active', owner_id: 1, images: '', description: '茶礼套装' },
        ]},
      });
    }
    return Promise.resolve({ code: 200, data: null });
  });
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── ProductDetailPage Tests ───────────────────────────

describe('ProductDetailPage (产品详情) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('产品详情')).toBeInTheDocument();
    });
  });

  it('renders product name from API', async () => {
    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
    });
  });

  it('renders product price', async () => {
    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      // Price appears in multiple places (main price, spec, footer)
      const prices = screen.getAllByText(/1299\.00/);
      expect(prices.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders stock information', async () => {
    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      expect(screen.getByText(/库存:\s*100/)).toBeInTheDocument();
    });
  });

  it('renders purchase button', async () => {
    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('立即购买')).toBeInTheDocument();
    });
  });

  it('shows empty state when no productId provided', async () => {
    delete mockLocationState.productId;
    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('产品不存在')).toBeInTheDocument();
    });
  });

  it('shows error state on API failure', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/products')) {
        return Promise.reject(new Error('网络错误'));
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument();
    });
  });
});

describe('ProductDetailPage (产品详情) - Interaction Tests', () => {
  it('navigates back to home when clicking back button', async () => {
    renderWithRouter(<ProductDetailPage />);

    await waitFor(() => {
      const backBtn = document.querySelector('header button');
      if (backBtn) fireEvent.click(backBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/home', { state: { transition: 'push_back' } });
  });
});

// ─── MyProducts Tests ──────────────────────────────────

describe('MyProducts (我的产品) - Smoke Tests', () => {
  it('renders the page header with title', async () => {
    renderWithRouter(<MyProducts />);

    await waitFor(() => {
      expect(screen.getByText('我的产品')).toBeInTheDocument();
    });
  });

  it('renders tab navigation', async () => {
    renderWithRouter(<MyProducts />);

    await waitFor(() => {
      expect(screen.getByText('已上架')).toBeInTheDocument();
      expect(screen.getByText('审核中')).toBeInTheDocument();
      expect(screen.getByText('已下架')).toBeInTheDocument();
      expect(screen.getByText('审核驳回')).toBeInTheDocument();
    });
  });

  it('renders product list from API', async () => {
    renderWithRouter(<MyProducts />);

    await waitFor(() => {
      expect(screen.getByText('智能健康手表 S3')).toBeInTheDocument();
    });
  });

  it('renders 上架新品 button', async () => {
    renderWithRouter(<MyProducts />);

    await waitFor(() => {
      expect(screen.getByText('上架新品')).toBeInTheDocument();
    });
  });

  it('shows empty state when no products', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/api/products')) {
        return Promise.resolve({ code: 200, data: { total: 0, items: [] } });
      }
      return Promise.resolve({ code: 200, data: null });
    });

    renderWithRouter(<MyProducts />);

    await waitFor(() => {
      expect(screen.getByText('暂无产品')).toBeInTheDocument();
    });
  });
});

describe('MyProducts (我的产品) - Interaction Tests', () => {
  it('navigates to add-product when clicking 上架新品 button', async () => {
    renderWithRouter(<MyProducts />);

    await waitFor(() => {
      const addBtn = screen.getByText('上架新品');
      fireEvent.click(addBtn);
    });

    expect(mockNavigate).toHaveBeenCalledWith('/add-product', { state: { transition: 'push' } });
  });
});

// ─── AddProduct Tests ──────────────────────────────────

describe('AddProduct (上架新产品) - Smoke Tests', () => {
  it('renders the page header with title', () => {
    renderWithRouter(<AddProduct />);

    expect(screen.getByText('上架新产品')).toBeInTheDocument();
  });

  it('renders all form sections', () => {
    renderWithRouter(<AddProduct />);

    expect(screen.getByText('基本信息')).toBeInTheDocument();
    expect(screen.getByText('价格与库存')).toBeInTheDocument();
    expect(screen.getByText('规格选项')).toBeInTheDocument();
    expect(screen.getByText('产品主图')).toBeInTheDocument();
    expect(screen.getByText('推广分润比例')).toBeInTheDocument();
  });

  it('renders all form fields', () => {
    renderWithRouter(<AddProduct />);

    expect(screen.getByPlaceholderText('请输入产品名称')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入产品描述')).toBeInTheDocument();
    // Price and earnPerShare both have placeholder "0.00"
    const amountInputs = screen.getAllByPlaceholderText('0.00');
    expect(amountInputs.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByPlaceholderText('请输入库存数量')).toBeInTheDocument();
  });

  it('renders submit button', () => {
    renderWithRouter(<AddProduct />);

    expect(screen.getByText('提交上架')).toBeInTheDocument();
  });

  it('renders product category selector', () => {
    renderWithRouter(<AddProduct />);

    expect(screen.getByText('大健康 - 营养膳食')).toBeInTheDocument();
  });
});

describe('AddProduct (上架新产品) - Interaction Tests', () => {
  it('allows typing in product name field', () => {
    renderWithRouter(<AddProduct />);

    const nameInput = screen.getByPlaceholderText('请输入产品名称') as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: '新产品测试' } });
    expect(nameInput.value).toBe('新产品测试');
  });

  it('allows typing in price field', () => {
    renderWithRouter(<AddProduct />);

    const priceInputs = screen.getAllByPlaceholderText('0.00');
    const priceInput = priceInputs[0] as HTMLInputElement; // First one is price
    fireEvent.change(priceInput, { target: { value: '99.99' } });
    expect(priceInput.value).toBe('99.99');
  });

  it('submits form and navigates on success', async () => {
    mockPost.mockResolvedValue({ code: 200, data: { product: { id: 1 } } });

    renderWithRouter(<AddProduct />);

    const submitBtn = screen.getByText('提交上架');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled();
    });

    expect(mockNavigate).toHaveBeenCalledWith('/my-products', { state: { transition: 'push_back' } });
  });

  it('shows submitting state while posting', async () => {
    mockPost.mockReturnValue(new Promise(() => {})); // Never resolves

    renderWithRouter(<AddProduct />);

    const submitBtn = screen.getByText('提交上架');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('提交中...')).toBeInTheDocument();
    });
  });
});
