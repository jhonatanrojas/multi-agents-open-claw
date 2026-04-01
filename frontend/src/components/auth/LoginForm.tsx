import { useState, useEffect } from 'react';
import { useAuthStore } from '@/store';
import './LoginForm.css';

export function LoginForm() {
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const { login, isLoading, error, clearError, checkSession, sessionChecked } = useAuthStore();

  // Check session on mount
  useEffect(() => {
    if (!sessionChecked) {
      checkSession();
    }
  }, [checkSession, sessionChecked]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) return;
    
    const success = await login(apiKey.trim());
    if (success) {
      setApiKey('');
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <h1>🔐 Dev Squad Dashboard</h1>
          <p>Multi-Agent Programming Team</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="api-key">API Key</label>
            <div className="input-wrapper">
              <input
                id="api-key"
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  if (error) clearError();
                }}
                placeholder="Enter your API key"
                disabled={isLoading}
                autoFocus
              />
              <button
                type="button"
                className="toggle-visibility"
                onClick={() => setShowKey(!showKey)}
                tabIndex={-1}
              >
                {showKey ? '🙈' : '👁️'}
              </button>
            </div>
          </div>

          {error && (
            <div className="error-message">
              <span className="error-icon">⚠️</span>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="login-button"
            disabled={isLoading || !apiKey.trim()}
          >
            {isLoading ? (
              <>
                <span className="spinner"></span>
                Authenticating...
              </>
            ) : (
              'Login'
            )}
          </button>
        </form>

        <div className="login-footer">
          <p>
            <strong>Dev Squad</strong> — ARCH, BYTE, PIXEL
          </p>
          <p className="hint">
            Use your DASHBOARD_API_KEY to access the dashboard
          </p>
        </div>
      </div>
    </div>
  );
}
