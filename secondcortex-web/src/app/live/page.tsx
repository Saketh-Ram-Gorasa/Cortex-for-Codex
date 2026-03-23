import { Suspense } from 'react';
import AuthGate from '@/components/AuthGate';

export const metadata = {
    title: 'SecondCortex — Live Context Graph',
    description: 'Real-time visualization of the SecondCortex agent reasoning network.',
};

export default function LivePage() {
    return (
        <main className="min-h-screen w-full">
            <Suspense fallback={null}>
                <AuthGate />
            </Suspense>
        </main>
    );
}
