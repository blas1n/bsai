import { MemoryList } from '@/components/memories/MemoryList';

export default function MemoriesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Memories</h1>
        <p className="text-muted-foreground">
          Long-term memories learned from past tasks and interactions
        </p>
      </div>
      <MemoryList />
    </div>
  );
}
