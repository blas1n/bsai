'use client';

import { useEffect, useState } from 'react';
import { SystemHealth } from '@/components/monitoring/SystemHealth';
import { TokenUsageChart } from '@/components/monitoring/TokenUsageChart';
import { CostTracker } from '@/components/monitoring/CostTracker';
import { useAuth } from '@/hooks/useAuth';
import { api, SessionResponse } from '@/lib/api';

// Generate usage data from sessions
const generateUsageData = (sessions: SessionResponse[]) => {
  const data: { date: string; input: number; output: number }[] = [];
  const now = new Date();

  for (let i = 6; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    const dateStr = date.toDateString();

    // Filter sessions for this day
    const daySessions = sessions.filter(
      (s) => new Date(s.created_at).toDateString() === dateStr
    );

    const inputTokens = daySessions.reduce((sum, s) => sum + s.total_input_tokens, 0);
    const outputTokens = daySessions.reduce((sum, s) => sum + s.total_output_tokens, 0);

    data.push({
      date: date.toLocaleDateString('en-US', { weekday: 'short' }),
      input: inputTokens,
      output: outputTokens,
    });
  }
  return data;
};

export default function MonitoringPage() {
  const { accessToken, isAuthenticated } = useAuth();
  const [usageData, setUsageData] = useState<{ date: string; input: number; output: number }[]>([]);
  const [stats, setStats] = useState({
    totalCost: 0,
    dailyCost: 0,
    dailyLimit: 50,
    activeSessions: 0,
    totalInputTokens: 0,
    totalOutputTokens: 0,
  });

  // Set API token when auth changes
  useEffect(() => {
    if (accessToken) {
      api.setToken(accessToken);
    }
  }, [accessToken]);

  useEffect(() => {
    const fetchStats = async () => {
      if (!isAuthenticated || !accessToken) return;

      try {
        const sessions = await api.getSessions(100, 0);
        const activeSessions = sessions.items.filter(
          (s) => s.status === 'active'
        ).length;
        const totalCost = sessions.items.reduce(
          (sum, s) => sum + parseFloat(s.total_cost_usd || '0'),
          0
        );
        const totalInputTokens = sessions.items.reduce(
          (sum, s) => sum + (s.total_input_tokens || 0),
          0
        );
        const totalOutputTokens = sessions.items.reduce(
          (sum, s) => sum + (s.total_output_tokens || 0),
          0
        );

        // Calculate today's cost
        const today = new Date().toDateString();
        const todaySessions = sessions.items.filter(
          (s) => new Date(s.created_at).toDateString() === today
        );
        const dailyCost = todaySessions.reduce(
          (sum, s) => sum + parseFloat(s.total_cost_usd || '0'),
          0
        );

        setStats({
          totalCost,
          dailyCost,
          dailyLimit: 50,
          activeSessions,
          totalInputTokens,
          totalOutputTokens,
        });

        // Generate usage chart data from real sessions
        setUsageData(generateUsageData(sessions.items));
      } catch (err) {
        console.error('Failed to fetch stats:', err);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [isAuthenticated, accessToken]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Monitoring</h1>
        <p className="text-muted-foreground">
          System health and usage statistics
        </p>
      </div>

      <div className="grid gap-6">
        <SystemHealth />

        <CostTracker
          totalCost={stats.totalCost}
          dailyCost={stats.dailyCost}
          dailyLimit={stats.dailyLimit}
          sessions={stats.activeSessions}
        />

        <TokenUsageChart data={usageData} />
      </div>
    </div>
  );
}
