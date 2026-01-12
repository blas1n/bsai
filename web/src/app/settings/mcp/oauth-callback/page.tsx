'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';

/**
 * OAuth callback content component.
 * Handles the actual OAuth callback logic.
 */
function McpOAuthCallbackContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const error = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');

    if (error) {
      setStatus('error');
      setErrorMessage(errorDescription || error);

      // Send error to parent window
      if (window.opener) {
        window.opener.postMessage({
          type: 'mcp-oauth-callback',
          error: errorDescription || error,
        }, window.location.origin);
      }
      return;
    }

    if (!code || !state) {
      setStatus('error');
      setErrorMessage('Missing authorization code or state parameter');
      return;
    }

    // Send code to parent window
    if (window.opener) {
      window.opener.postMessage({
        type: 'mcp-oauth-callback',
        code,
        state,
      }, window.location.origin);

      setStatus('success');

      // Close popup after a short delay
      setTimeout(() => {
        window.close();
      }, 1500);
    } else {
      setStatus('error');
      setErrorMessage('This page must be opened from the MCP settings page');
    }
  }, [searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4 p-8">
        {status === 'processing' && (
          <>
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
            <p className="text-muted-foreground">Processing authentication...</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="h-8 w-8 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center mx-auto">
              <svg className="h-5 w-5 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-green-600 dark:text-green-400 font-medium">Authentication successful!</p>
            <p className="text-sm text-muted-foreground">This window will close automatically...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="h-8 w-8 rounded-full bg-red-100 dark:bg-red-900 flex items-center justify-center mx-auto">
              <svg className="h-5 w-5 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <p className="text-red-600 dark:text-red-400 font-medium">Authentication failed</p>
            <p className="text-sm text-muted-foreground">{errorMessage}</p>
            <button
              onClick={() => window.close()}
              className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm"
            >
              Close Window
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * OAuth callback page for MCP server authentication.
 * This page is opened in a popup and receives the OAuth authorization code.
 * It then sends the code back to the parent window via postMessage.
 */
export default function McpOAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-4 p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    }>
      <McpOAuthCallbackContent />
    </Suspense>
  );
}
