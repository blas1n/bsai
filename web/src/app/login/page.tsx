'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Bot, LogIn, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/hooks/useAuth';

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, isLoading, login } = useAuth();

  const error = searchParams.get('error');
  const errorDescription = searchParams.get('error_description');

  useEffect(() => {
    if (isAuthenticated) {
      router.push('/chat');
    }
  }, [isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background to-muted p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <Bot className="h-8 w-8 text-primary" />
          </div>
          <CardTitle className="text-2xl">Welcome to BSAI</CardTitle>
          <CardDescription>
            Multi-Agent LLM Orchestration System with automatic cost optimization,
            quality assurance, and context preservation.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-medium">Authentication Error</div>
                <div className="text-xs opacity-80">{errorDescription || error}</div>
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-4 text-center text-sm">
            <div className="rounded-lg border p-3">
              <div className="font-medium">Cost Optimization</div>
              <div className="text-xs text-muted-foreground">Auto LLM selection</div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="font-medium">QA Validation</div>
              <div className="text-xs text-muted-foreground">Quality checks</div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="font-medium">Context Memory</div>
              <div className="text-xs text-muted-foreground">Session persistence</div>
            </div>
          </div>

          <Button onClick={() => login()} className="w-full" size="lg">
            <LogIn className="mr-2 h-4 w-4" />
            Sign in with Keycloak
          </Button>

          <p className="text-center text-xs text-muted-foreground">
            By signing in, you agree to our Terms of Service and Privacy Policy.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    }>
      <LoginContent />
    </Suspense>
  );
}
