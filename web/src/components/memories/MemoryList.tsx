'use client';

import { useEffect, useState, useRef } from 'react';
import { Combine, RefreshCw, Search, Timer, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MemoryCard } from './MemoryCard';
import { MemoryDetailDialog } from './MemoryDetailDialog';
import { useMemoryStore } from '@/stores/memoryStore';
import { useAuth } from '@/hooks/useAuth';
import type { Memory } from '@/types/memory';

const MEMORY_TYPES = [
  { value: '', label: 'All Types' },
  { value: 'task_result', label: 'Task Results' },
  { value: 'learning', label: 'Learnings' },
  { value: 'error', label: 'Errors' },
  { value: 'user_preference', label: 'Preferences' },
];

export function MemoryList() {
  const {
    memories,
    searchResults,
    stats,
    total,
    isLoading,
    isSearching,
    error,
    fetchMemories,
    searchMemories,
    fetchStats,
    deleteMemory,
    consolidate,
    decay,
    clearSearchResults,
    setError,
  } = useMemoryStore();
  const { accessToken, isLoading: isAuthLoading } = useAuth();

  const [filterType, setFilterType] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [isConsolidating, setIsConsolidating] = useState(false);
  const [isDecaying, setIsDecaying] = useState(false);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const hasFetchedRef = useRef(false);

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      clearSearchResults();
      return;
    }
    await searchMemories(searchQuery);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    clearSearchResults();
  };

  const handleFilterChange = (type: string) => {
    setFilterType(type);
    fetchMemories(20, 0, type || undefined);
  };

  const handleDelete = async (memoryId: string) => {
    if (!confirm('Are you sure you want to delete this memory?')) return;
    try {
      await deleteMemory(memoryId);
      fetchStats();
    } catch {
      // Error handled in store
    }
  };

  const handleConsolidate = async () => {
    setIsConsolidating(true);
    try {
      const result = await consolidate();
      alert(`Consolidated ${result.consolidated_count} memories. ${result.remaining_count} remaining.`);
    } catch {
      // Error handled in store
    } finally {
      setIsConsolidating(false);
    }
  };

  const handleDecay = async () => {
    setIsDecaying(true);
    try {
      const result = await decay();
      alert(`Applied decay to ${result.decayed_count} memories.`);
    } catch {
      // Error handled in store
    } finally {
      setIsDecaying(false);
    }
  };

  useEffect(() => {
    if (isAuthLoading) return;

    if (accessToken && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchMemories();
      fetchStats();
    }
  }, [accessToken, isAuthLoading, fetchMemories, fetchStats]);

  useEffect(() => {
    if (!accessToken) {
      hasFetchedRef.current = false;
    }
  }, [accessToken]);

  const displayMemories = searchResults.length > 0
    ? searchResults.map((r) => ({ memory: r.memory, similarity: r.similarity }))
    : memories.map((m) => ({ memory: m, similarity: undefined }));

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Memories
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_memories}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Avg Importance
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {(stats.average_importance * 100).toFixed(0)}%
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                By Type
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1">
                {Object.entries(stats.by_type).map(([type, count]) => (
                  <Badge key={type} variant="secondary" className="text-xs">
                    {type}: {count}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Maintenance
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleConsolidate}
                  disabled={isConsolidating}
                  title="Merge similar memories"
                >
                  <Combine className={`h-4 w-4 ${isConsolidating ? 'animate-spin' : ''}`} />
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleDecay}
                  disabled={isDecaying}
                  title="Apply importance decay"
                >
                  <Timer className={`h-4 w-4 ${isDecaying ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Search and Filter */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex flex-1 gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Search memories semantically..."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm pr-20"
            />
            {searchQuery && (
              <Button
                size="icon"
                variant="ghost"
                className="absolute right-10 top-1/2 -translate-y-1/2 h-6 w-6"
                onClick={handleClearSearch}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
            <Button
              size="icon"
              variant="ghost"
              className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6"
              onClick={handleSearch}
              disabled={isSearching}
            >
              <Search className={`h-4 w-4 ${isSearching ? 'animate-pulse' : ''}`} />
            </Button>
          </div>
        </div>
        <div className="flex gap-2 items-center">
          <select
            value={filterType}
            onChange={(e) => handleFilterChange(e.target.value)}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            {MEMORY_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            size="icon"
            onClick={() => {
              fetchMemories(20, 0, filterType || undefined);
              fetchStats();
            }}
            disabled={isLoading}
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Search results indicator */}
      {searchResults.length > 0 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Found {searchResults.length} similar memories</span>
          <Button variant="link" size="sm" onClick={handleClearSearch}>
            Clear search
          </Button>
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="rounded-md bg-destructive/15 p-4 text-destructive flex justify-between items-center">
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={() => setError(null)}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* Memory list */}
      {(isLoading || isAuthLoading) && memories.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : displayMemories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-muted-foreground">
            {searchQuery ? 'No matching memories found' : 'No memories yet'}
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            Memories are automatically created as you complete tasks
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {displayMemories.map(({ memory, similarity }) => (
              <MemoryCard
                key={memory.id}
                memory={memory}
                onSelect={setSelectedMemory}
                onDelete={handleDelete}
                showSimilarity={similarity}
              />
            ))}
          </div>
          {!searchResults.length && total > memories.length && (
            <div className="text-center text-sm text-muted-foreground">
              Showing {memories.length} of {total} memories
            </div>
          )}
        </>
      )}

      {/* Detail Dialog */}
      <MemoryDetailDialog
        memory={selectedMemory}
        onClose={() => setSelectedMemory(null)}
        onDelete={handleDelete}
      />
    </div>
  );
}
