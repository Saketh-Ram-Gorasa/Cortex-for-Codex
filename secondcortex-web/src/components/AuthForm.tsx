'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

interface AuthFormProps {
    mode: 'login' | 'signup';
}

export default function AuthForm({ mode }: AuthFormProps) {
    const router = useRouter();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const guestEmail = process.env.NEXT_PUBLIC_GUEST_LOGIN_EMAIL || 'suhaan@secondcortex.local';
    const guestPassword = process.env.NEXT_PUBLIC_GUEST_LOGIN_PASSWORD || 'suhaan-guest';
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://sc-backend-suhaan.azurewebsites.net';

    const persistSession = (token: string, isGuestLogin: boolean) => {
        localStorage.setItem('sc_jwt_token', token);
        localStorage.setItem('sc_dev_guest_mode', isGuestLogin ? 'true' : 'false');
        router.push('/live');
    };

    const loginWithCredentials = async (loginEmail: string, loginPassword: string, isGuestLogin = false) => {
        const endpoint = '/api/v1/auth/login';

        const res = await fetch(`${backendUrl}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: loginEmail, password: loginPassword })
        });

        if (res.ok) {
            const data = await res.json();
            persistSession(data.token, isGuestLogin);
            return;
        }

        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Login failed. Please check your credentials.');
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const emailTrim = email.trim();
        if (!emailTrim || !password) {
            setError('Please enter both email and password.');
            return;
        }

        setIsLoading(true);
        setError('');

        try {
            if (mode === 'login') {
                await loginWithCredentials(emailTrim, password);
                return;
            }

            const res = await fetch(`${backendUrl}/api/v1/auth/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: emailTrim, password, display_name: displayName.trim() })
            });

            if (res.ok) {
                const data = await res.json();
                persistSession(data.token, false);
            } else {
                const errData = await res.json().catch(() => ({}));
                setError(errData.detail || 'Signup failed. Please check your credentials.');
            }
        } catch (err) {
            if (mode === 'login' && err instanceof Error) {
                setError(err.message);
                return;
            }

            setError('Cannot reach the backend. Is it running?');
        } finally {
            setIsLoading(false);
        }
    };

    const handleGuestLogin = async () => {
        setIsLoading(true);
        setError('');

        try {
            await loginWithCredentials(guestEmail, guestPassword, true);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Guest login failed.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <main className="sc-shell sc-auth-shell">
            <div className="sc-auth-card">
                <div className="sc-auth-header">
                    <p className="sc-auth-eyebrow">SecondCortex Access</p>
                    <h1 className="sc-auth-title">{mode === 'login' ? 'Resume Session' : 'Create Session'}</h1>
                    <p className="sc-auth-sub">{mode === 'login' ? 'Authenticate to open your live memory graph.' : 'Create an account to start building persistent context.'}</p>
                </div>

                <form onSubmit={handleSubmit} className="sc-auth-form">
                    <label className="sc-auth-label" htmlFor="auth-email">Email</label>
                    <input
                        id="auth-email"
                        className="sc-auth-input"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        required
                    />

                    <label className="sc-auth-label" htmlFor="auth-password">Password</label>
                    <input
                        id="auth-password"
                        className="sc-auth-input"
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="********"
                        required
                    />

                    {mode === 'signup' && (
                        <>
                            <label className="sc-auth-label" htmlFor="auth-display-name">Display Name (optional)</label>
                            <input
                                id="auth-display-name"
                                className="sc-auth-input"
                                type="text"
                                value={displayName}
                                onChange={(e) => setDisplayName(e.target.value)}
                                placeholder="Your Name"
                            />
                        </>
                    )}

                    {error && <div className="sc-auth-error">{error}</div>}

                    <button type="submit" disabled={isLoading} className="btn-primary sc-auth-submit">
                        {isLoading ? 'Please wait...' : mode === 'login' ? 'Log In' : 'Create Account'}
                    </button>

                    {mode === 'login' && (
                        <button
                            type="button"
                            disabled={isLoading}
                            onClick={handleGuestLogin}
                            className="btn-secondary sc-auth-submit sc-guest-btn"
                        >
                            {isLoading ? 'Please wait...' : 'Guest Login'}
                        </button>
                    )}
                </form>

                <p className="sc-auth-switch">
                    {mode === 'login' ? (
                        <>
                            Don&apos;t have an account? <Link href="/signup">Sign up</Link>
                        </>
                    ) : (
                        <>
                            Already have an account? <Link href="/login">Log in</Link>
                        </>
                    )}
                </p>
            </div>
        </main>
    );
}
