'use client';

import { useEffect, useState } from 'react';
import { Activity, Database, Server, Wifi } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api, HealthResponse } from '@/lib/api';

export function SystemHealth() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    try {
      const response = await api.getHealth();
      setHealth(response);
      setError(null);
    } catch (err) {
      setError('Failed to fetch health status');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const getStatusVariant = (status: string) => {
    return status === 'healthy' || status === 'ok' ? 'success' : 'destructive';
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Activity className="h-8 w-8 animate-pulse text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-destructive">{error}</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          System Health
          <Badge variant={getStatusVariant(health?.status || 'unknown')}>
            {health?.status || 'unknown'}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
            <Server className="h-8 w-8 text-primary" />
            <div>
              <p className="text-sm font-medium">API Server</p>
              <p className="text-xs text-muted-foreground">
                Version: {health?.version || 'N/A'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
            <Database className="h-8 w-8 text-primary" />
            <div>
              <p className="text-sm font-medium">Database</p>
              <Badge variant={getStatusVariant(health?.database || 'unknown')} className="mt-1">
                {health?.database || 'unknown'}
              </Badge>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 bg-muted rounded-lg">
            <Wifi className="h-8 w-8 text-primary" />
            <div>
              <p className="text-sm font-medium">Redis</p>
              <Badge variant={getStatusVariant(health?.redis || 'unknown')} className="mt-1">
                {health?.redis || 'unknown'}
              </Badge>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
