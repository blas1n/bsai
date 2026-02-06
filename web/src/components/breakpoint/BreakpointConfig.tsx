'use client';

import { useState, useCallback } from 'react';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { X } from 'lucide-react';

type PauseLevel = 'none' | 'task' | 'feature' | 'epic';

export interface BreakpointConfig {
  pauseLevel: PauseLevel;
  pauseOnFailure: boolean;
  pauseOnPlanReview: boolean;
  pauseOnTaskIds: string[];
}

interface BreakpointConfigProps {
  initialConfig?: BreakpointConfig;
  onSave: (config: BreakpointConfig) => void;
}

const pauseLevelOptions: { value: PauseLevel; label: string; description: string }[] = [
  { value: 'none', label: 'None', description: 'No automatic pauses' },
  { value: 'task', label: 'Task', description: 'Pause after each task completes' },
  { value: 'feature', label: 'Feature', description: 'Pause after each feature milestone' },
  { value: 'epic', label: 'Epic', description: 'Pause after each epic completes' },
];

const defaultConfig: BreakpointConfig = {
  pauseLevel: 'none',
  pauseOnFailure: true,
  pauseOnPlanReview: false,
  pauseOnTaskIds: [],
};

export function BreakpointConfig({ initialConfig, onSave }: BreakpointConfigProps) {
  const [pauseLevel, setPauseLevel] = useState<PauseLevel>(
    initialConfig?.pauseLevel ?? defaultConfig.pauseLevel
  );
  const [pauseOnFailure, setPauseOnFailure] = useState(
    initialConfig?.pauseOnFailure ?? defaultConfig.pauseOnFailure
  );
  const [pauseOnPlanReview, setPauseOnPlanReview] = useState(
    initialConfig?.pauseOnPlanReview ?? defaultConfig.pauseOnPlanReview
  );
  const [pauseOnTaskIds, setPauseOnTaskIds] = useState<string[]>(
    initialConfig?.pauseOnTaskIds ?? defaultConfig.pauseOnTaskIds
  );
  const [taskIdInput, setTaskIdInput] = useState('');

  const handleAddTaskId = useCallback(() => {
    const trimmedId = taskIdInput.trim();
    if (trimmedId && !pauseOnTaskIds.includes(trimmedId)) {
      setPauseOnTaskIds((prev) => [...prev, trimmedId]);
      setTaskIdInput('');
    }
  }, [taskIdInput, pauseOnTaskIds]);

  const handleRemoveTaskId = useCallback((idToRemove: string) => {
    setPauseOnTaskIds((prev) => prev.filter((id) => id !== idToRemove));
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAddTaskId();
      }
    },
    [handleAddTaskId]
  );

  const handleSave = useCallback(() => {
    onSave({
      pauseLevel,
      pauseOnFailure,
      pauseOnPlanReview,
      pauseOnTaskIds,
    });
  }, [pauseLevel, pauseOnFailure, pauseOnPlanReview, pauseOnTaskIds, onSave]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Breakpoint Configuration</CardTitle>
        <CardDescription>
          Configure when the workflow should pause for review
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Pause Level */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Pause Level</Label>
          <RadioGroup
            value={pauseLevel}
            onValueChange={(value) => setPauseLevel(value as PauseLevel)}
            className="space-y-2"
          >
            {pauseLevelOptions.map((option) => (
              <div
                key={option.value}
                className="flex items-start space-x-3 rounded-md border p-3 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => setPauseLevel(option.value)}
              >
                <RadioGroupItem value={option.value} id={`pause-${option.value}`} />
                <div className="space-y-1">
                  <Label
                    htmlFor={`pause-${option.value}`}
                    className="text-sm font-medium cursor-pointer"
                  >
                    {option.label}
                  </Label>
                  <p className="text-xs text-muted-foreground">{option.description}</p>
                </div>
              </div>
            ))}
          </RadioGroup>
        </div>

        {/* Additional Options */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Additional Options</Label>
          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="pauseOnFailure"
                checked={pauseOnFailure}
                onCheckedChange={(checked) => setPauseOnFailure(checked === true)}
              />
              <Label htmlFor="pauseOnFailure" className="text-sm cursor-pointer">
                Pause on failure
              </Label>
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="pauseOnPlanReview"
                checked={pauseOnPlanReview}
                onCheckedChange={(checked) => setPauseOnPlanReview(checked === true)}
              />
              <Label htmlFor="pauseOnPlanReview" className="text-sm cursor-pointer">
                Pause on plan review (before execution starts)
              </Label>
            </div>
          </div>
        </div>

        {/* Pause on Specific Task IDs */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Pause on Specific Tasks</Label>
          <div className="flex space-x-2">
            <Input
              placeholder="Enter task ID"
              value={taskIdInput}
              onChange={(e) => setTaskIdInput(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1"
            />
            <Button type="button" variant="outline" onClick={handleAddTaskId}>
              Add
            </Button>
          </div>
          {pauseOnTaskIds.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {pauseOnTaskIds.map((id) => (
                <div
                  key={id}
                  className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md bg-muted"
                >
                  <span className="font-mono">{id}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveTaskId(id)}
                    className="text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Add specific task IDs to pause before their execution
          </p>
        </div>

        {/* Save Button */}
        <div className="pt-4">
          <Button onClick={handleSave} className="w-full">
            Save Configuration
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
