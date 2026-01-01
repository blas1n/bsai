import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/providers/AuthProvider';
import { ThemeProvider } from '@/components/theme';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'BSAI - Multi-Agent LLM Orchestration',
  description: 'Multi-agent LLM orchestration system with cost optimization and quality assurance',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
