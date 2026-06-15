import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

import { PromotionTutorial } from '../screens/TutorialScreens';

describe('PromotionTutorial (推广教程) - Smoke Tests', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the page header with title', () => {
    render(<BrowserRouter><PromotionTutorial /></BrowserRouter>);
    expect(screen.getByText('推广教程')).toBeInTheDocument();
  });

  it('renders tutorial steps section', () => {
    render(<BrowserRouter><PromotionTutorial /></BrowserRouter>);
    expect(screen.getByText('如何分享产品')).toBeInTheDocument();
  });

  it('navigates back on back button click', () => {
    render(<BrowserRouter><PromotionTutorial /></BrowserRouter>);
    const backBtn = document.querySelector('header button');
    if (backBtn) fireEvent.click(backBtn);
    expect(mockNavigate).toHaveBeenCalled();
  });
});
