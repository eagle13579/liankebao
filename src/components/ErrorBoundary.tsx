import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] Caught:', error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-neutral-bg p-6 text-center">
          <div className="w-16 h-16 bg-red-50 rounded-full flex items-center justify-center mb-4">
            <span className="text-red-500 text-3xl">!</span>
          </div>
          <h1 className="text-xl font-bold text-on-surface mb-2">页面出现异常</h1>
          <p className="text-sm text-text-muted mb-6 max-w-xs">
            {this.state.error?.message || '应用遇到了意外错误，请重试'}
          </p>
          <div className="flex gap-3">
            <button
              onClick={this.handleRetry}
              className="px-6 py-2.5 bg-primary-container text-white rounded-xl font-bold text-sm active:scale-95 transition-transform shadow-lg"
            >
              重试
            </button>
            <button
              onClick={() => { this.handleRetry(); window.location.href = '/'; }}
              className="px-6 py-2.5 bg-white border border-border-light text-on-surface rounded-xl font-bold text-sm active:scale-95 transition-transform"
            >
              返回首页
            </button>
          </div>
          <p className="mt-8 text-[10px] text-text-muted">链客宝 - 一站式AI营销增长引擎</p>
        </div>
      );
    }

    return this.props.children;
  }
}
