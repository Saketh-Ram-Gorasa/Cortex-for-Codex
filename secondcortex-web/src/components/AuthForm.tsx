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
            const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://sc-backend-suhaan.azurewebsites.net';
            const endpoint = mode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/signup';

            const payload = mode === 'login'
                ? { email: emailTrim, password }
                : { email: emailTrim, password, display_name: displayName.trim() };

            const res = await fetch(`${backendUrl}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                const data = await res.json();
                localStorage.setItem('sc_jwt_token', data.token);
                router.push('/live');
            } else {
                const errData = await res.json().catch(() => ({}));
                setError(errData.detail || `${mode === 'login' ? 'Login' : 'Signup'} failed. Please check your credentials.`);
            }
        } catch {
            setError('Cannot reach the backend. Is it running?');
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
