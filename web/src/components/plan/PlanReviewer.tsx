// web/src/components/plan/PlanReviewer.tsx
"use client";

import { useState, useCallback } from "react";
import { CheckCircle, XCircle, Edit3, FileText, Layers, ListChecks } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PlanTree, Epic, Feature, Task } from "./PlanTree";
import { cn } from "@/lib/utils";

export interface Plan {
  id: string;
  title: string;
  overview: string;
  techStack: string[];
  structureType: "flat" | "grouped" | "hierarchical";
  epics?: Epic[];
  features?: Feature[];
  tasks: Task[];
  totalTasks: number;
}

interface PlanReviewerProps {
  plan: Plan;
  onApprove: () => void;
  onRevise: (feedback: string) => void;
  onReject: () => void;
  isLoading?: boolean;
}

const STRUCTURE_ICONS = {
  flat: <ListChecks className="h-4 w-4" />,
  grouped: <Layers className="h-4 w-4" />,
  hierarchical: <FileText className="h-4 w-4" />,
};

const STRUCTURE_LABELS = {
  flat: "Flat List",
  grouped: "Grouped by Feature",
  hierarchical: "Epic/Feature/Task",
};

export function PlanReviewer({
  plan,
  onApprove,
  onRevise,
  onReject,
  isLoading = false,
}: PlanReviewerProps) {
  const [feedback, setFeedback] = useState("");
  const [showReviseForm, setShowReviseForm] = useState(false);

  const handleReviseClick = useCallback(() => {
    setShowReviseForm(true);
  }, []);

  const handleCancelRevise = useCallback(() => {
    setShowReviseForm(false);
    setFeedback("");
  }, []);

  const handleSubmitRevision = useCallback(() => {
    if (feedback.trim()) {
      onRevise(feedback.trim());
      setShowReviseForm(false);
      setFeedback("");
    }
  }, [feedback, onRevise]);

  // Calculate stats
  const completedTasks = plan.tasks.filter((t) => t.status === "completed").length;
  const pendingTasks = plan.tasks.filter((t) => t.status === "pending").length;
  const failedTasks = plan.tasks.filter((t) => t.status === "failed").length;

  const complexityCounts = plan.tasks.reduce(
    (acc, task) => {
      const complexity = task.complexity.toLowerCase();
      acc[complexity] = (acc[complexity] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-xl truncate">{plan.title}</CardTitle>
            <CardDescription className="mt-2 line-clamp-3">
              {plan.overview}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {STRUCTURE_ICONS[plan.structureType]}
            <span className="text-xs text-muted-foreground">
              {STRUCTURE_LABELS[plan.structureType]}
            </span>
          </div>
        </div>

        {/* Tech Stack */}
        {plan.techStack.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-4">
            {plan.techStack.map((tech) => (
              <Badge key={tech} variant="secondary" className="text-xs">
                {tech}
              </Badge>
            ))}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Stats Section */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard
            label="Total Tasks"
            value={plan.totalTasks}
            className="bg-muted/50"
          />
          <StatCard
            label="Completed"
            value={completedTasks}
            className="bg-green-50 dark:bg-green-900/20"
          />
          <StatCard
            label="Pending"
            value={pendingTasks}
            className="bg-yellow-50 dark:bg-yellow-900/20"
          />
          <StatCard
            label="Failed"
            value={failedTasks}
            className="bg-red-50 dark:bg-red-900/20"
          />
        </div>

        {/* Complexity Distribution */}
        {Object.keys(complexityCounts).length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">
              Complexity Distribution
            </h4>
            <div className="flex flex-wrap gap-2">
              {Object.entries(complexityCounts).map(([complexity, count]) => (
                <Badge key={complexity} variant="outline" className="capitalize">
                  {complexity}: {count}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Plan Tree */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-muted-foreground">
            Task Breakdown
          </h4>
          <div className="max-h-[400px] overflow-y-auto rounded-lg border p-3">
            <PlanTree
              structureType={plan.structureType}
              epics={plan.epics}
              features={plan.features}
              tasks={plan.tasks}
            />
          </div>
        </div>

        {/* Revision Feedback Form */}
        {showReviseForm && (
          <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
            <label className="text-sm font-medium">
              Revision Feedback
              <span className="text-muted-foreground ml-1">
                (Describe what changes you would like)
              </span>
            </label>
            <Textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Please describe the changes you'd like to see in this plan..."
              rows={4}
              className="resize-none"
            />
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCancelRevise}
                disabled={isLoading}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSubmitRevision}
                disabled={isLoading || !feedback.trim()}
              >
                Submit Revision Request
              </Button>
            </div>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex justify-end gap-3 pt-4 border-t">
        <Button
          variant="destructive"
          onClick={onReject}
          disabled={isLoading || showReviseForm}
          className="gap-2"
        >
          <XCircle className="h-4 w-4" />
          Reject
        </Button>
        <Button
          variant="outline"
          onClick={handleReviseClick}
          disabled={isLoading || showReviseForm}
          className="gap-2"
        >
          <Edit3 className="h-4 w-4" />
          Request Revision
        </Button>
        <Button
          onClick={onApprove}
          disabled={isLoading || showReviseForm}
          className="gap-2"
        >
          <CheckCircle className="h-4 w-4" />
          Approve Plan
        </Button>
      </CardFooter>
    </Card>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  className?: string;
}

function StatCard({ label, value, className }: StatCardProps) {
  return (
    <div className={cn("rounded-lg p-3 text-center", className)}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
