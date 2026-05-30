import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import { MembershipCenter } from '../screens/MembershipScreens';

describe('MembershipCenter (会员中心) - Smoke Tests', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the page header with title', () => {
    render(<BrowserRouter><MembershipCenter /></BrowserRouter>);
    expect(screen.getByText('会员中心')).toBeInTheDocument();
  });

  it('renders membership info section', () => {
    render(<BrowserRouter><MembershipCenter /></BrowserRouter>);
    expect(screen.getByText('当前等级')).toBeInTheDocument();
  });

  it('navigates back on back button click', () => {
    render(<BrowserRouter><MembershipCenter /></BrowserRouter>);
    const backBtn = document.querySelector('header button');
    if (backBtn) fireEvent.click(backBtn);
    expect(mockNavigate).toHaveBeenCalled();
  });
});
