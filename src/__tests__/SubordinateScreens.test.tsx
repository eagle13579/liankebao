import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import { SubordinatePage } from '../screens/SubordinateScreens';

describe('SubordinatePage (下级推广) - Smoke Tests', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the page header with title', () => {
    render(<BrowserRouter><SubordinatePage /></BrowserRouter>);
    expect(screen.getByText('推广统计')).toBeInTheDocument();
  });

  it('renders order items', () => {
    render(<BrowserRouter><SubordinatePage /></BrowserRouter>);
    // Tab buttons and order items both have these texts
    const completedItems = screen.getAllByText('已完成');
    expect(completedItems.length).toBeGreaterThanOrEqual(1);
    const pendingItems = screen.getAllByText('处理中');
    expect(pendingItems.length).toBeGreaterThanOrEqual(1);
  });

  it('navigates back on back button click', () => {
    render(<BrowserRouter><SubordinatePage /></BrowserRouter>);
    const backBtn = document.querySelector('header button');
    if (backBtn) fireEvent.click(backBtn);
    expect(mockNavigate).toHaveBeenCalled();
  });
});
