"use client";

import CrystallineBrain from "./CrystallineBrain";

export default function HeroSection() {
    return (
        <section
            className="relative min-h-screen max-w-7xl mx-auto px-6 lg:px-8 pt-32 lg:pt-0 flex items-center z-10 w-full"
            style={{
                background:
                    "radial-gradient(ellipse at 68% 52%, rgba(139,92,246,0.14) 0%, rgba(6,182,212,0.08) 38%, rgba(7,14,40,0) 70%)",
            }}
        >
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-8 items-center w-full">
                {/* Left Column - Text Content */}
                <div className="flex flex-col gap-6 opacity-0 hero-content translate-y-8">
                    <h1 className="text-5xl lg:text-7xl font-bold tracking-tight text-white leading-[1.1]">
                        Building The Future of Inter-Agent Context
                    </h1>

                    <p className="text-lg lg:text-xl text-gray-400 max-w-xl leading-relaxed">
                        A step change from discrete prompt-response cycles. SecondCortex enables persistent, multi-agent reasoning graphs that evolve in real time.
                    </p>

                    <div className="flex flex-col sm:flex-row gap-4 mt-4">
                        <button className="px-8 py-4 bg-white text-black font-semibold rounded-full hover:scale-105 transition-transform duration-200">
                            Get Started
                        </button>
                        <button className="px-8 py-4 bg-transparent border border-white text-white font-semibold rounded-full hover:scale-105 transition-transform duration-200">
                            Read Documentation
                        </button>
                    </div>
                </div>

                {/* Right Column - 3D Object */}
                <div className="w-full flex justify-center lg:justify-end">
                    <CrystallineBrain />
                </div>
            </div>
        </section>
    );
}
