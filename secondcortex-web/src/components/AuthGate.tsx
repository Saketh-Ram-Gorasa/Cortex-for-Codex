'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import ContextGraph from '@/components/ContextGraph';
import Dashboard from '@/components/Dashboard';

/**
 * AuthGate — protection wrapper for the live graph and dashboard.
 * If no token is found in localStorage, it redirects to /login.
 */
export default function AuthGate() {
    const router = useRouter();
    const [token, setToken] = useState<string | null>(null);
    const [isChecking, setIsChecking] = useState(true);
    const [activeTab, setActiveTab] = useState<'dashboard' | 'live'>('dashboard');

    useEffect(() => {
        const stored = localStorage.getItem('sc_jwt_token');
        if (!stored) {
            router.push('/login');
        } else {
            setToken(stored);
        }
        setIsChecking(false);
    }, [router]);

    const handleLogout = () => {
        localStorage.removeItem('sc_jwt_token');
        setToken(null);
        router.push('/login');
    };

    if (isChecking) {
        return (
            <div className="sc-shell sc-center-text">
                Authenticating...
            </div>
        );
    }

    if (!token) {
        return null;
    }

    return (
        <div className="sc-shell sc-app-shell">
            <div className="sc-app-topbar">
                <div className="nav-logo">
                    Second<span>Cortex</span>
                </div>

                <div className="sc-app-tabs">
                <button
                    onClick={() => setActiveTab('dashboard')}
                    className={`sc-app-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
                >
                    Dashboard
                </button>
                <button
                    onClick={() => setActiveTab('live')}
                    className={`sc-app-tab ${activeTab === 'live' ? 'active' : ''}`}
                >
                    Live Context Graph
                </button>
                </div>

                <button
                    onClick={handleLogout}
                    className="btn-secondary sc-logout"
                    type="button"
                >
                    Logout
                </button>
            </div>

            <div className="sc-app-content custom-scrollbar">
                {activeTab === 'dashboard' ? (
                    <Dashboard token={token} />
                ) : (
                    <ContextGraph token={token} onUnauthorized={handleLogout} />
                )}
            </div>

            <style jsx global>{`
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
        </div>
    );
}
