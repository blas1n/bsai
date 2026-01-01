import { SessionList } from '@/components/sessions/SessionList';

export default function SessionsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Sessions</h1>
        <p className="text-muted-foreground">
          Manage and monitor your AI agent sessions
        </p>
      </div>
      <SessionList />
    </div>
  );
}
