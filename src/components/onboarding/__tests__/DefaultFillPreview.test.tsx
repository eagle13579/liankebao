import React from 'react';
import { render, screen } from '@testing-library/react';
import DefaultFillPreview from '../DefaultFillPreview';
import type { UserInfo } from '../DefaultFillPreview';

const FULL_USER_INFO: UserInfo = {
  name: '张三',
  position: '技术总监',
  company: '链可科技',
  phone: '138-0000-0000',
  email: 'zhangsan@chainke.com',
  wechat: 'zhangsan_wx',
  website: 'https://chainke.com',
};

const PARTIAL_USER_INFO: UserInfo = {
  name: '李四',
  company: '示例公司',
};

describe('DefaultFillPreview', () => {
  test('显示用户姓名/公司/职位', () => {
    render(<DefaultFillPreview userInfo={FULL_USER_INFO} templateId="modern-blue" />);

    expect(screen.getByText('张三')).toBeInTheDocument();
    expect(screen.getByText('技术总监')).toBeInTheDocument();
    expect(screen.getByText('链可科技')).toBeInTheDocument();
  });

  test('显示联系方式', () => {
    render(<DefaultFillPreview userInfo={FULL_USER_INFO} templateId="modern-blue" />);

    expect(screen.getByText('138-0000-0000')).toBeInTheDocument();
    expect(screen.getByText('zhangsan@chainke.com')).toBeInTheDocument();
    expect(screen.getByText('zhangsan_wx')).toBeInTheDocument();
    expect(screen.getByText('https://chainke.com')).toBeInTheDocument();
  });

  test('不同templateId切换主题色', () => {
    const { container: container1 } = render(
      <DefaultFillPreview userInfo={FULL_USER_INFO} templateId="modern-blue" />
    );
    const { container: container2 } = render(
      <DefaultFillPreview userInfo={FULL_USER_INFO} templateId="warm-gold" />
    );

    // The card div should have different background gradients
    const cards = container1.querySelectorAll('.max-w-sm');
    const card1 = cards[0] || container1.querySelector('[class*="from-blue-500"]');
    const card2 = container2.querySelector('[class*="from-amber-400"]');

    expect(card1?.className).toContain('from-blue-500');
    expect(card2?.className).toContain('from-amber-400');
  });

  test('无userInfo时显示占位', () => {
    const emptyUserInfo: UserInfo = { name: '' };
    render(<DefaultFillPreview userInfo={emptyUserInfo} />);

    // When name is empty, it shows '您的姓名' as fallback
    expect(screen.getByText('您的姓名')).toBeInTheDocument();
  });

  test('空字段不显示', () => {
    render(<DefaultFillPreview userInfo={PARTIAL_USER_INFO} />);

    // name and company are rendered
    expect(screen.getByText('李四')).toBeInTheDocument();
    expect(screen.getByText('示例公司')).toBeInTheDocument();

    // Fields not in PARTIAL_USER_INFO should not appear
    expect(screen.queryByText('技术总监')).not.toBeInTheDocument();
    expect(screen.queryByText('138-0000-0000')).not.toBeInTheDocument();
  });

  test('响应式布局存在', () => {
    const { container } = render(<DefaultFillPreview userInfo={FULL_USER_INFO} />);

    // The card container should have responsive classes
    const cardWrapper = container.querySelector('.w-full');
    expect(cardWrapper).toBeInTheDocument();

    // Check that the card has max-w-sm and mx-auto for responsive centering
    const card = container.querySelector('.max-w-sm');
    expect(card?.className).toContain('mx-auto');

    // Check that the hint text at the bottom exists
    expect(screen.getByText('系统已根据您的信息自动填充名片')).toBeInTheDocument();
    expect(screen.getByText('您可以在后续步骤中进一步编辑')).toBeInTheDocument();
  });
});
