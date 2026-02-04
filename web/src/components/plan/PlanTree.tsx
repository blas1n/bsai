// web/src/components/plan/PlanTree.tsx
"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  CheckCircle,
  Circle,
  AlertCircle,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export interface Task {
  id: string;
  description: string;
  complexity: string;
  status: string;
  dependencies: string[];
}

export interface Feature {
  id: string;
  title: string;
  tasks: Task[];
}

export interface Epic {
  id: string;
  title: string;
  features: Feature[];
}

interface PlanTreeProps {
  structureType: "flat" | "grouped" | "hierarchical";
  epics?: Epic[];
  features?: Feature[];
  tasks: Task[];
}

const COMPLEXITY_STYLES: Record<string, string> = {
  trivial: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  simple: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  moderate: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  complex: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  expert: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export function PlanTree({ structureType, epics, features, tasks }: PlanTreeProps) {
  if (structureType === "flat") {
    return <TaskList tasks={tasks} />;
  }

  if (structureType === "grouped") {
    return (
      <div className="space-y-4">
        {features?.map((feature) => (
          <FeatureItem key={feature.id} feature={feature} />
        ))}
      </div>
    );
  }

  // hierarchical
  return (
    <div className="space-y-4">
      {epics?.map((epic) => (
        <EpicItem key={epic.id} epic={epic} />
      ))}
    </div>
  );
}

function TaskList({ tasks }: { tasks: Task[] }) {
  return (
    <ul className="space-y-2">
      {tasks.map((task) => (
        <TaskItem key={task.id} task={task} />
      ))}
    </ul>
  );
}

function TaskItem({ task }: { task: Task }) {
  const statusIcon = {
    pending: <Circle className="h-4 w-4 text-gray-400 flex-shrink-0" />,
    in_progress: <Clock className="h-4 w-4 text-blue-500 flex-shrink-0" />,
    completed: <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />,
    failed: <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />,
  }[task.status] || <Circle className="h-4 w-4 flex-shrink-0" />;

  const complexityStyle = COMPLEXITY_STYLES[task.complexity.toLowerCase()] || COMPLEXITY_STYLES.moderate;

  return (
    <li className="flex items-start gap-3 p-3 rounded-lg border bg-card hover:bg-accent/50 transition-colors">
      {statusIcon}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs text-muted-foreground">{task.id}</span>
          <Badge variant="outline" className={cn("text-xs", complexityStyle)}>
            {task.complexity}
          </Badge>
        </div>
        <p className="text-sm mt-1">{task.description}</p>
        {task.dependencies.length > 0 && (
          <p className="text-xs text-muted-foreground mt-1">
            <span className="font-medium">Depends on:</span>{" "}
            {task.dependencies.join(", ")}
          </p>
        )}
      </div>
    </li>
  );
}

function FeatureItem({ feature }: { feature: Feature }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const completedTasks = feature.tasks.filter((t) => t.status === "completed").length;
  const totalTasks = feature.tasks.length;

  return (
    <div className="border rounded-lg bg-card overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 p-3 text-left hover:bg-accent/50 transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        )}
        <span className="font-mono text-xs text-muted-foreground">{feature.id}</span>
        <span className="flex-1 font-medium text-sm truncate">{feature.title}</span>
        <span className="text-xs text-muted-foreground">
          {completedTasks}/{totalTasks} tasks
        </span>
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 pt-0 border-t">
          <ul className="space-y-2 mt-3 pl-4">
            {feature.tasks.map((task) => (
              <TaskItem key={task.id} task={task} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function EpicItem({ epic }: { epic: Epic }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const totalFeatures = epic.features.length;
  const totalTasks = epic.features.reduce((sum, f) => sum + f.tasks.length, 0);
  const completedTasks = epic.features.reduce(
    (sum, f) => sum + f.tasks.filter((t) => t.status === "completed").length,
    0
  );

  return (
    <div className="border-2 rounded-lg bg-card overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 p-4 text-left hover:bg-accent/50 transition-colors bg-muted/30"
      >
        {isExpanded ? (
          <ChevronDown className="h-5 w-5 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="h-5 w-5 text-muted-foreground flex-shrink-0" />
        )}
        <span className="font-mono text-xs text-muted-foreground">{epic.id}</span>
        <span className="flex-1 font-semibold truncate">{epic.title}</span>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{totalFeatures} features</span>
          <span>{completedTasks}/{totalTasks} tasks</span>
        </div>
      </button>

      {isExpanded && (
        <div className="p-3 pt-0 border-t space-y-3">
          {epic.features.map((feature) => (
            <div key={feature.id} className="mt-3">
              <FeatureItem feature={feature} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
