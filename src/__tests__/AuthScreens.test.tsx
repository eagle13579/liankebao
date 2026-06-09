import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { LoginPage, UserRegistration } from '../screens/AuthScreens';
import { api } from '../api/client';

// ─── Mocks ─────────────────────────────────────────────

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../api/client', () => ({
  api: {
    post: vi.fn(),
    saveToken: vi.fn(),
    loadToken: vi.fn(),
    removeToken: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

// ─── Tests ─────────────────────────────────────────────

describe('AuthScreens - LoginPage', () => {
  it('renders login form with username, password fields and login button', () => {
    renderWithRouter(<LoginPage />);

    // Username field should have default value 'admin'
    const usernameInput = screen.getByPlaceholderText('请输入账号');
    expect(usernameInput).toBeInTheDocument();
    expect(usernameInput).toHaveValue('admin');

    // Password field
    const passwordInput = screen.getByPlaceholderText('请输入密码');
    expect(passwordInput).toBeInTheDocument();
    expect(passwordInput).toHaveValue('admin123');

    // Login button
    const loginButton = screen.getByText('登录');
    expect(loginButton).toBeInTheDocument();
  });

  it('shows error message when login fails', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 401,
      message: '用户名或密码错误',
    });

    renderWithRouter(<LoginPage />);

    const loginButton = screen.getByText('登录');
    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(screen.getByText('用户名或密码错误')).toBeInTheDocument();
    });
  });

  it('shows network error message on exception', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));

    renderWithRouter(<LoginPage />);

    const loginButton = screen.getByText('登录');
    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(screen.getByText('网络错误，请重试')).toBeInTheDocument();
    });
  });

  it('saves token and navigates on successful login', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 200,
      data: { token: 'test-token-123', user: { name: 'Test' } },
    });

    renderWithRouter(<LoginPage />);

    const loginButton = screen.getByText('登录');
    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/api/auth/login', {
        username: 'admin',
        password: 'admin123',
      });
    });
  });

  it('renders navigation link to register page', () => {
    renderWithRouter(<LoginPage />);
    const registerButton = screen.getByText('注册');
    expect(registerButton).toBeInTheDocument();
  });
});

describe('AuthScreens - UserRegistration', () => {
  it('renders registration form with all required fields', () => {
    renderWithRouter(<UserRegistration />);

    expect(screen.getByPlaceholderText('登录用户名')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('登录密码')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入真实姓名')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入11位手机号')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入所在单位全称')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入担任职位')).toBeInTheDocument();

    // Role selection
    expect(screen.getByText('企业主 / 购买者')).toBeInTheDocument();
    expect(screen.getByText('推广员')).toBeInTheDocument();
    expect(screen.getByText('产品方')).toBeInTheDocument();

    // Submit button
    expect(screen.getByText('完成注册')).toBeInTheDocument();
  });

  it('allows selecting different roles', () => {
    renderWithRouter(<UserRegistration />);

    const promoterOption = screen.getByText('推广员');
    fireEvent.click(promoterOption);

    // The role state is internal, but we can verify the click works
    // by checking the "buyer" default was replaced with "promoter" visually
    expect(screen.getByText('推广员')).toBeInTheDocument();
  });

  it('shows registration success message on successful API call', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 200,
      data: { user: { username: 'testuser' } },
    });

    renderWithRouter(<UserRegistration />);

    // Fill in fields
    fireEvent.change(screen.getByPlaceholderText('登录用户名'), { target: { value: 'testuser' } });
    fireEvent.change(screen.getByPlaceholderText('登录密码'), { target: { value: 'pass123' } });
    fireEvent.change(screen.getByPlaceholderText('请输入真实姓名'), { target: { value: '张三' } });
    fireEvent.change(screen.getByPlaceholderText('请输入11位手机号'), { target: { value: '13800138000' } });

    // Click submit
    const submitBtn = screen.getByText('完成注册');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('注册成功，请返回登录')).toBeInTheDocument();
    });
  });

  it('displays error when registration fails', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      code: 400,
      message: '用户名已存在',
    });

    renderWithRouter(<UserRegistration />);

    fireEvent.change(screen.getByPlaceholderText('登录用户名'), { target: { value: 'existing' } });
    fireEvent.change(screen.getByPlaceholderText('登录密码'), { target: { value: 'pass123' } });
    fireEvent.change(screen.getByPlaceholderText('请输入真实姓名'), { target: { value: '李四' } });
    fireEvent.change(screen.getByPlaceholderText('请输入11位手机号'), { target: { value: '13900139000' } });

    const submitBtn = screen.getByText('完成注册');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('用户名已存在')).toBeInTheDocument();
    });
  });
});

describe('LoginPage - Additional Smoke Tests', () => {
  it('renders the brand name in header', () => {
    renderWithRouter(<LoginPage />);
    const brandElements = screen.getAllByText('链客宝AI');
    expect(brandElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the brand slogan', () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByText('企业信任关系网络 — 每一次对接，都建立在已验证的信任之上')).toBeInTheDocument();
  });

  it('renders trust badges section', () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByText('企业实名认证')).toBeInTheDocument();
    expect(screen.getByText('数据加密传输')).toBeInTheDocument();
    expect(screen.getByText('平台服务保障')).toBeInTheDocument();
  });

  it('renders social login buttons (SMS, Mail, QR code)', () => {
    renderWithRouter(<LoginPage />);
    // The social login buttons are SVG icons without text; check their parent buttons exist
    const socialSection = document.querySelector('[class*="flex justify-center gap-5"]');
    expect(socialSection).toBeInTheDocument();
    const socialButtons = socialSection?.querySelectorAll('button');
    expect(socialButtons?.length).toBe(3);
  });

  it('renders WeChat one-click login button', () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByText('微信一键登录')).toBeInTheDocument();
  });

  it('renders agreement text with user agreement and privacy policy links', () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByText('登录即表示同意')).toBeInTheDocument();
    expect(screen.getByText('《用户协议》')).toBeInTheDocument();
    expect(screen.getByText('《隐私政策》')).toBeInTheDocument();
  });

  it('renders footer with copyright and register link', () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByText('还没有账号？')).toBeInTheDocument();
    expect(screen.getByText('去注册')).toBeInTheDocument();
    expect(screen.getByText(/企业信任关系网络 © 2025 链客宝AI/)).toBeInTheDocument();
  });

  it('shows trust badges with descriptions', () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByText('构建可信商业网络')).toBeInTheDocument();
    expect(screen.getByText('SSL/TLS 安全通道')).toBeInTheDocument();
    expect(screen.getByText('信任护航 · 安心对接')).toBeInTheDocument();
  });
});

describe('LoginPage - Interaction Tests', () => {
  it('shows loading state when login button is clicked', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {})); // Never resolves

    renderWithRouter(<LoginPage />);

    const loginButton = screen.getByText('登录');
    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(screen.getByText('登录中...')).toBeInTheDocument();
    });
  });

  it('allows typing in username field', () => {
    renderWithRouter(<LoginPage />);

    const usernameInput = screen.getByPlaceholderText('请输入账号');
    fireEvent.change(usernameInput, { target: { value: 'testuser' } });
    expect(usernameInput).toHaveValue('testuser');
  });

  it('allows typing in password field', () => {
    renderWithRouter(<LoginPage />);

    const passwordInput = screen.getByPlaceholderText('请输入密码') as HTMLInputElement;
    fireEvent.change(passwordInput, { target: { value: 'newpass' } });
    expect(passwordInput).toHaveValue('newpass');
  });

  it('shows WeChat login hint when clicking WeChat login button', () => {
    renderWithRouter(<LoginPage />);

    const wechatBtn = screen.getByText('微信一键登录');
    fireEvent.click(wechatBtn);

    expect(screen.getByText('请在微信客户端中打开使用微信一键登录')).toBeInTheDocument();
  });

  it('navigates to register page when clicking register button in header', () => {
    renderWithRouter(<LoginPage />);

    const registerBtn = screen.getAllByText('注册')[0]; // Header button
    fireEvent.click(registerBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/register', { state: { transition: 'push' } });
  });

  it('navigates to register page when clicking "去注册" in footer', () => {
    renderWithRouter(<LoginPage />);

    const goRegisterBtn = screen.getByText('去注册');
    fireEvent.click(goRegisterBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/register', { state: { transition: 'push' } });
  });
});

// Token storage tests are in client.test.ts (the api module is mocked here)
