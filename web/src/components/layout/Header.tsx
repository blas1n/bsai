'use client';

import Link from 'next/link';
import { Activity, LayoutDashboard, Settings } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center">
        <div className="mr-4 flex">
          <Link href="/" className="mr-6 flex items-center space-x-2">
            <Activity className="h-6 w-6 text-primary" />
            <span className="font-bold">BSAI Dashboard</span>
          </Link>
          <nav className="flex items-center space-x-6 text-sm font-medium">
            <Link
              href="/sessions"
              className="transition-colors hover:text-foreground/80 text-foreground/60"
            >
              Sessions
            </Link>
            <Link
              href="/memories"
              className="transition-colors hover:text-foreground/80 text-foreground/60"
            >
              Memories
            </Link>
            <Link
              href="/monitoring"
              className="transition-colors hover:text-foreground/80 text-foreground/60"
            >
              Monitoring
            </Link>
          </nav>
        </div>
        <div className="flex flex-1 items-center justify-end space-x-2">
          <Button variant="ghost" size="icon">
            <Settings className="h-4 w-4" />
            <span className="sr-only">Settings</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
