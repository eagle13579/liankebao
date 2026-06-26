import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import StepIndicator from '../StepIndicator';
import type { Step } from '../StepIndicator';

const STEPS: Step[] = [
  { id: 1, label: '企业信息', description: '填写企业基本信息' },
  { id: 2, label: '需求偏好', description: '设置合作偏好与目标' },
  { id: 3, label: '模板选择', description: '选择名片模板并预览' },
];

describe('StepIndicator', () => {
  test('渲染所有步骤标题', () => {
    render(<StepIndicator steps={STEPS} currentStep={1} />);

    STEPS.forEach((step) => {
      expect(screen.getByText(step.label)).toBeInTheDocument();
    });
  });

  test('当前步骤高亮', () => {
    render(<StepIndicator steps={STEPS} currentStep={2} />);

    // current step should have aria-current="step"
    const currentButton = screen.getByRole('button', { name: /需求偏好/ });
    expect(currentButton).toHaveAttribute('aria-current', 'step');
  });

  test('已完成步骤显示勾选图标', () => {
    render(<StepIndicator steps={STEPS} currentStep={3} />);

    // Steps 1 and 2 are completed (stepNumber < currentStep) -> should show checkmark
    const completedStep1 = screen.getByText('✓');
    expect(completedStep1).toBeInTheDocument();
  });

  test('点击已完成步骤触发onStepClick', () => {
    const onStepClick = jest.fn();
    render(<StepIndicator steps={STEPS} currentStep={3} onStepClick={onStepClick} />);

    // Step 1 is completed; clicking it should fire onStepClick with id 1
    const step1Button = screen.getByRole('button', { name: /企业信息/ });
    fireEvent.click(step1Button);
    expect(onStepClick).toHaveBeenCalledWith(1);
  });

  test('正确显示步骤总数', () => {
    render(<StepIndicator steps={STEPS} currentStep={1} />);

    const listItems = screen.getAllByRole('button');
    expect(listItems).toHaveLength(STEPS.length);
  });

  test('步骤间连接线存在', () => {
    const { container } = render(<StepIndicator steps={STEPS} currentStep={1} />);

    // Connector lines are rendered inside nav > ol > li > div elements with flex-1
    // For 3 steps, there should be 2 connectors
    const connectorLines = container.querySelectorAll('nav ol li > div.flex-1');
    expect(connectorLines).toHaveLength(2);
  });
});
