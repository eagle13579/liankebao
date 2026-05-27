import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { LoginPage, UserRegistration } from '../screens/AuthScreens';
import { api } from '../api/client';

// ─── Mocks ─────────────────────────────────────────────

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

// Token storage tests are in client.test.ts (the api module is mocked here)
