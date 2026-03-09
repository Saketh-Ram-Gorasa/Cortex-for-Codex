"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function Navbar() {
    const [scrolled, setScrolled] = useState(false);

    useEffect(() => {
        const handleScroll = () => {
            setScrolled(window.scrollY > 100);
        };

        window.addEventListener("scroll", handleScroll, { passive: true });
        handleScroll();

        return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    return (
        <nav
            className={`fixed top-0 left-0 w-full z-50 transition-all duration-300 ${scrolled ? "bg-black/60 backdrop-blur-md border-b border-white/10 py-4" : "bg-transparent py-6"
                }`}
        >
            <div className="max-w-7xl mx-auto px-6 lg:px-8 flex justify-between items-center">
                <div className="text-white font-semibold tracking-wide flex items-center gap-2">
                    {/* We will animate 'Second Cortex' text in IntroSequence and have this replace it */}
                    <span className="opacity-0 navbar-logo-text transition-opacity duration-1000">
                        Second Cortex
                    </span>
                </div>

                <div className="hidden md:flex items-center gap-8 text-sm text-gray-300 font-medium">
                    <Link href="#features" className="hover:text-white transition-colors">Features</Link>
                    <Link href="#platform" className="hover:text-white transition-colors">Platform</Link>
                    <Link href="#company" className="hover:text-white transition-colors">Company</Link>
                    <Link
                        href="/live"
                        className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-md transition-all border border-white/5 navbar-live-btn opacity-0"
                    >
                        Live Graph
                    </Link>
                </div>
            </div>
        </nav>
    );
}
