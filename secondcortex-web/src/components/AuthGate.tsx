'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import ContextGraph from '@/components/ContextGraph';
import Dashboard from '@/components/Dashboard';

type SessionMode = 'developer' | 'pm';

/**
 * AuthGate: protection wrapper for dashboard and live graph.
 * Supports:
 * - Standard developer login
 * - PM login (?pm=true)
 * - PM guest mode (?pm=true&guest=true)
 */
export default function AuthGate() {
  const router = useRouter();

  const [token, setToken] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'live'>('dashboard');
  const [sessionMode, setSessionMode] = useState<SessionMode>('developer');
  const [isPmGuest, setIsPmGuest] = useState(false);
  const [isDevGuest, setIsDevGuest] = useState(false);

  const [mcpKey, setMcpKey] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showMcpModal, setShowMcpModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const backendUrl = 'https://sc-backend-suhaan.azurewebsites.net';

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pmQuery = params.get('pm') === 'true';
    const guestQuery = params.get('guest') === 'true';
    const storedPmGuest = localStorage.getItem('sc_pm_guest_mode') === 'true';
    const storedPmAuth = localStorage.getItem('sc_pm_mode') === 'auth' || storedPmGuest;
    const storedDevGuest = localStorage.getItem('sc_dev_guest_mode') === 'true';

    const storedToken = localStorage.getItem('sc_jwt_token');
    if (!storedToken) {
      router.push('/');
      setIsChecking(false);
      return;
    }

    const nextMode: SessionMode = pmQuery || storedPmAuth ? 'pm' : 'developer';
    const nextGuest = nextMode === 'pm' && (guestQuery || storedPmGuest);
    setSessionMode(nextMode);
    setIsPmGuest(nextGuest);
    setIsDevGuest(nextMode === 'developer' && storedDevGuest);
    setToken(storedToken);
    if (nextGuest) {
      setActiveTab('dashboard');
    }

    if (nextMode === 'developer') {
      fetchMcpKey(storedToken);
    }

    setIsChecking(false);
  }, [router]);

  const fetchMcpKey = async (authToken: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/v1/auth/mcp-key`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.api_key) {
          setMcpKey(data.api_key);
        }
      }
    } catch (err) {
      console.error('Failed to fetch MCP key', err);
    }
  };

  const handleGenerateKey = async () => {
    if (!token) {
      return;
    }

    setIsGenerating(true);
    setError(null);
    try {
      const res = await fetch(`${backendUrl}/api/v1/auth/mcp-key`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMcpKey(data.api_key);
        setShowMcpModal(true);
      } else {
        setError('Failed to generate key. Please try again.');
      }
    } catch {
      setError('Connection error. Check your internet.');
    } finally {
      setIsGenerating(false);
    }
  };

  const copyToClipboard = () => {
    if (mcpKey) {
      navigator.clipboard.writeText(mcpKey);
      setNotice('API key copied to clipboard.');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('sc_jwt_token');
    localStorage.removeItem('sc_pm_mode');
    localStorage.removeItem('sc_pm_guest_mode');
    localStorage.removeItem('sc_dev_guest_mode');

    setToken(null);
    setSessionMode('developer');
    setIsPmGuest(false);
    setIsDevGuest(false);
    setActiveTab('dashboard');

    router.push('/');
  };

  if (isChecking) {
    return <div className="sc-shell sc-center-text">Authenticating...</div>;
  }

  if (!token) {
    return null;
  }

  return (
    <div className="sc-shell sc-app-shell">
      <div className="sc-app-topbar">
        <div className="nav-logo">
          Second<span>Cortex</span>
          {sessionMode === 'pm' && <span className="sc-role-badge">PM</span>}
          {sessionMode === 'developer' && isDevGuest && <span className="sc-role-badge">Guest</span>}
        </div>

        <div className="sc-app-tabs">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`sc-app-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          >
            {sessionMode === 'pm' ? 'PM Dashboard' : 'Dashboard'}
          </button>
          {!isPmGuest && (
            <button
              onClick={() => setActiveTab('live')}
              className={`sc-app-tab ${activeTab === 'live' ? 'active' : ''}`}
            >
              Live Context Graph
            </button>
          )}
        </div>

        {sessionMode === 'developer' && (
          <div className="sc-app-actions">
            <button
              onClick={mcpKey ? () => setShowMcpModal(true) : handleGenerateKey}
              disabled={isGenerating}
              className="btn-secondary sc-mcp-btn"
              title={mcpKey ? 'View MCP Integration' : 'Generate MCP API Key'}
            >
              {isGenerating ? '...' : mcpKey ? 'MCP Key' : 'MCP'}
            </button>
          </div>
        )}

        <button onClick={handleLogout} className="btn-secondary sc-logout" type="button">
          {isPmGuest ? 'Exit PM Guest' : 'Logout'}
        </button>
      </div>

      <div className="sc-app-content custom-scrollbar">
        {activeTab === 'dashboard' ? (
          <Dashboard token={token} mode={sessionMode} isGuestPm={isPmGuest} isGuestDeveloper={isDevGuest} />
        ) : sessionMode === 'pm' && isPmGuest ? (
          <div className="sc-dashboard-wrap">
            <div className="sc-dashboard-inner">
              <div className="sc-dashboard-panel">
                <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
                  <h2 className="sc-dashboard-h2">Live Context Graph Disabled in PM Guest Mode</h2>
                  <p className="sc-dashboard-p">
                    Use PM Dashboard to inspect teammate snapshots and compression summaries. Authenticated PM login
                    enables live graph access.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <ContextGraph token={token} onUnauthorized={handleLogout} />
        )}
      </div>

      <style jsx global>{`
        .sc-role-badge {
          display: inline-block;
          margin-left: 8px;
          padding: 2px 6px;
          border: 1px solid rgba(255, 255, 255, 0.4);
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.08em;
          vertical-align: middle;
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.2);
        }
      `}</style>

      {sessionMode === 'developer' && showMcpModal && (
        <div className="sc-modal-wrap">
          <div className="sc-modal-backdrop" onClick={() => setShowMcpModal(false)} />
          <div className="sc-modal-card">
            <div className="sc-modal-stack">
              <div className="sc-modal-head">
                <div className="sc-modal-emoji">Key</div>
                <h3 className="sc-modal-title">Your MCP API Key</h3>
                <p className="sc-modal-sub">Use this key to authorize external MCP clients.</p>
              </div>

              <div className="sc-modal-key">
                <span className="sc-modal-key-text">{mcpKey}</span>
                <button onClick={copyToClipboard} className="btn-secondary" title="Copy to clipboard">
                  Copy
                </button>
              </div>

              <div className="sc-modal-warn">
                <span>Warning</span>
                <p>Do not share this key publicly. It grants access to your snapshot history.</p>
              </div>

              {error && <p className="sc-auth-error">{error}</p>}
              {notice && <p className="sc-auth-sub">{notice}</p>}

              <button onClick={() => setShowMcpModal(false)} className="btn-primary sc-modal-close">
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
