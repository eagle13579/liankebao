import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import PartnerPolicy from '../screens/PartnerPolicy';

describe('PartnerPolicy (分润政策) - Smoke Tests', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the page header with title', () => {
    render(<BrowserRouter><PartnerPolicy /></BrowserRouter>);
    expect(screen.getByText('分润政策')).toBeInTheDocument();
  });

  it('renders policy content section', () => {
    render(<BrowserRouter><PartnerPolicy /></BrowserRouter>);
    expect(screen.getByText('推广赚钱，就这么简单')).toBeInTheDocument();
  });

  it('navigates back on back button click', () => {
    render(<BrowserRouter><PartnerPolicy /></BrowserRouter>);
    const backBtn = document.querySelector('header button');
    if (backBtn) fireEvent.click(backBtn);
    expect(mockNavigate).toHaveBeenCalled();
  });
});
