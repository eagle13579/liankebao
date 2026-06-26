import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import TemplateSelector from '../TemplateSelector';
import type { Template } from '../TemplateSelector';

const CUSTOM_TEMPLATES: Template[] = [
  {
    id: 'custom-1',
    name: '自定义模板一',
    description: '自定义描述的模板',
    gradient: 'from-red-500 to-orange-500',
    tags: ['自定义', '测试'],
  },
  {
    id: 'custom-2',
    name: '自定义模板二',
    description: '另一个自定义模板描述',
    gradient: 'from-cyan-400 to-blue-500',
    tags: ['创意'],
  },
];

describe('TemplateSelector', () => {
  test('渲染所有模板卡片', () => {
    const onSelect = jest.fn();
    render(<TemplateSelector templates={CUSTOM_TEMPLATES} selectedId={null} onSelect={onSelect} />);

    CUSTOM_TEMPLATES.forEach((tmpl) => {
      expect(screen.getByText(tmpl.name)).toBeInTheDocument();
      expect(screen.getByText(tmpl.description)).toBeInTheDocument();
    });
  });

  test('选中模板高亮', () => {
    const onSelect = jest.fn();
    render(<TemplateSelector templates={CUSTOM_TEMPLATES} selectedId="custom-1" onSelect={onSelect} />);

    const selectedButton = screen.getByRole('button', { name: /自定义模板一/ });
    expect(selectedButton).toHaveAttribute('aria-pressed', 'true');
    // Check that the selected card has the ring classes
    expect(selectedButton.className).toContain('ring-blue-600');
  });

  test('onSelect回调触发', () => {
    const onSelect = jest.fn();
    render(<TemplateSelector templates={CUSTOM_TEMPLATES} selectedId={null} onSelect={onSelect} />);

    const card = screen.getByRole('button', { name: /自定义模板二/ });
    fireEvent.click(card);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  test('选中的模板id正确传递', () => {
    const onSelect = jest.fn();
    render(<TemplateSelector templates={CUSTOM_TEMPLATES} selectedId={null} onSelect={onSelect} />);

    const card = screen.getByRole('button', { name: /自定义模板一/ });
    fireEvent.click(card);
    expect(onSelect).toHaveBeenCalledWith('custom-1');
  });

  test('未选中任何模板时无高亮', () => {
    const onSelect = jest.fn();
    render(<TemplateSelector templates={CUSTOM_TEMPLATES} selectedId={null} onSelect={onSelect} />);

    const buttons = screen.getAllByRole('button');
    buttons.forEach((btn) => {
      expect(btn).toHaveAttribute('aria-pressed', 'false');
      expect(btn.className).not.toContain('ring-blue-600');
    });
  });

  test('自定义模板列表渲染', () => {
    const onSelect = jest.fn();
    render(<TemplateSelector templates={CUSTOM_TEMPLATES} selectedId={null} onSelect={onSelect} />);

    // Verify tags are rendered
    expect(screen.getByText('自定义')).toBeInTheDocument();
    expect(screen.getByText('测试')).toBeInTheDocument();
    expect(screen.getByText('创意')).toBeInTheDocument();
  });
});
