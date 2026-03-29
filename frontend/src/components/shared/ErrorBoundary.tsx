import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div style={{
          padding: '40px',
          textAlign: 'center',
          background: '#f0ede6',
          minHeight: '100vh',
        }}>
          <h1 style={{ marginBottom: '16px', color: '#e24b4a' }}>
            Algo salió mal
          </h1>
          <p style={{ color: '#5f5e5a', marginBottom: '20px' }}>
            {this.state.error?.message || 'Error desconocido'}
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              background: '#1a1916',
              color: '#fff',
              border: 'none',
              padding: '10px 24px',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            Recargar página
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}