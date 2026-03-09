import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import LenisProvider from "@/components/landing/LenisProvider";
import CursorLayer from "@/components/CursorLayer";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SecondCortex — Live Context Graph",
  description: "Real-time visualization of the SecondCortex agent reasoning network.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased selection:bg-accent-green selection:text-white`}
      >
        <LenisProvider>
          {children}
          <CursorLayer />
        </LenisProvider>
      </body>
    </html>
  );
}
