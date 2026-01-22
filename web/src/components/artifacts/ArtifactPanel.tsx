'use client';

import { useState } from 'react';
import {
  FileCode,
  FolderTree,
  Copy,
  Download,
  ChevronDown,
  ChevronRight,
  File,
  Folder,
  Check,
  X,
  Maximize2,
  Minimize2,
  Archive,
  History,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';

// Artifact types
export interface CodeArtifact {
  id: string;
  type: 'code';
  filename: string;
  language: string;
  content: string;
  path?: string;
}

export interface ProjectArtifact {
  id: string;
  type: 'project';
  name: string;
  files: FileNode[];
}

export interface FileNode {
  name: string;
  type: 'file' | 'folder';
  path: string;
  content?: string;
  language?: string;
  children?: FileNode[];
}

export type Artifact = CodeArtifact | ProjectArtifact;

export interface TaskVersion {
  id: string;
  sequence_number: number;
  original_request: string;
  created_at: string;
}

interface ArtifactPanelProps {
  artifacts: Artifact[];
  onClose?: () => void;
  sessionId?: string;
  tasks?: TaskVersion[];
  selectedTaskId?: string | null;
  onVersionChange?: (taskId: string | null) => void;
}

// Language to syntax highlighting mapping
const LANGUAGE_DISPLAY: Record<string, { label: string; color: string }> = {
  typescript: { label: 'TypeScript', color: 'text-blue-500' },
  javascript: { label: 'JavaScript', color: 'text-yellow-500' },
  python: { label: 'Python', color: 'text-green-500' },
  rust: { label: 'Rust', color: 'text-orange-500' },
  go: { label: 'Go', color: 'text-cyan-500' },
  java: { label: 'Java', color: 'text-red-500' },
  css: { label: 'CSS', color: 'text-pink-500' },
  html: { label: 'HTML', color: 'text-orange-400' },
  json: { label: 'JSON', color: 'text-gray-500' },
  yaml: { label: 'YAML', color: 'text-purple-500' },
  markdown: { label: 'Markdown', color: 'text-gray-400' },
  sql: { label: 'SQL', color: 'text-blue-400' },
  shell: { label: 'Shell', color: 'text-green-400' },
  dockerfile: { label: 'Dockerfile', color: 'text-blue-300' },
};

function CodeBlock({ content, language, filename }: { content: string; language: string; filename: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const langDisplay = LANGUAGE_DISPLAY[language] || { label: language, color: 'text-gray-500' };

  return (
    <div className="rounded-lg border bg-muted/30 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-muted/50 border-b">
        <div className="flex items-center gap-2">
          <FileCode className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">{filename}</span>
          <span className={cn('text-xs', langDisplay.color)}>{langDisplay.label}</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleCopy}>
            {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleDownload}>
            <Download className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Code content */}
      <div className="overflow-x-auto">
        <pre className="p-4 text-sm font-mono leading-relaxed">
          <code>{content}</code>
        </pre>
      </div>
    </div>
  );
}

function FileTreeNode({
  node,
  depth = 0,
  selectedPath,
  onSelect,
}: {
  node: FileNode;
  depth?: number;
  selectedPath: string | null;
  onSelect: (node: FileNode) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(depth < 2);
  const isSelected = selectedPath === node.path;

  if (node.type === 'folder') {
    return (
      <div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={cn(
            'w-full flex items-center gap-1 px-2 py-1 text-sm hover:bg-accent rounded transition-colors',
            'text-left'
          )}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          {isExpanded ? (
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 text-muted-foreground" />
          )}
          <Folder className="h-4 w-4 text-blue-500" />
          <span>{node.name}</span>
        </button>
        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={() => onSelect(node)}
      className={cn(
        'w-full flex items-center gap-1 px-2 py-1 text-sm hover:bg-accent rounded transition-colors',
        'text-left',
        isSelected && 'bg-accent'
      )}
      style={{ paddingLeft: `${depth * 12 + 20}px` }}
    >
      <File className="h-4 w-4 text-muted-foreground" />
      <span className="truncate">{node.name}</span>
    </button>
  );
}

function ProjectViewer({ project }: { project: ProjectArtifact }) {
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);

  return (
    <div className="flex h-full">
      {/* File tree */}
      <div className="w-64 border-r overflow-y-auto">
        <div className="p-2 border-b bg-muted/30">
          <div className="flex items-center gap-2">
            <FolderTree className="h-4 w-4" />
            <span className="text-sm font-medium">{project.name}</span>
          </div>
        </div>
        <div className="py-1">
          {project.files.map((node) => (
            <FileTreeNode
              key={node.path}
              node={node}
              selectedPath={selectedFile?.path || null}
              onSelect={setSelectedFile}
            />
          ))}
        </div>
      </div>

      {/* File content */}
      <div className="flex-1 overflow-auto">
        {selectedFile && selectedFile.content ? (
          <CodeBlock
            content={selectedFile.content}
            language={selectedFile.language || 'text'}
            filename={selectedFile.name}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <FileCode className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Select a file to view</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatVersionLabel(task: TaskVersion): string {
  const date = new Date(task.created_at);
  const timeStr = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  const preview = task.original_request.slice(0, 20) + (task.original_request.length > 20 ? '...' : '');
  return `#${task.sequence_number} - ${timeStr} - ${preview}`;
}

export function ArtifactPanel({
  artifacts,
  onClose,
  sessionId,
  tasks,
  selectedTaskId,
  onVersionChange,
}: ArtifactPanelProps) {
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(
    artifacts.length > 0 ? artifacts[0].id : null
  );
  const [isExpanded, setIsExpanded] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const selectedArtifact = artifacts.find((a) => a.id === selectedArtifactId);
  const hasVersions = tasks && tasks.length > 1;

  const handleVersionChange = (value: string) => {
    if (onVersionChange) {
      onVersionChange(value === 'latest' ? null : value);
    }
  };

  const handleDownloadZip = async () => {
    if (!sessionId) return;

    setIsDownloading(true);
    try {
      const blob = await api.downloadArtifactsZip(sessionId, selectedTaskId || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const versionSuffix = selectedTaskId ? `_${selectedTaskId.slice(0, 8)}` : '';
      a.download = `artifacts_${sessionId.slice(0, 8)}${versionSuffix}.zip`;
      a.href = url;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to download ZIP:', error);
    } finally {
      setIsDownloading(false);
    }
  };

  if (artifacts.length === 0) {
    return (
      <div className="h-full flex flex-col bg-background border-l">
        <div className="p-4 border-b flex items-center justify-between">
          <h2 className="font-semibold text-sm">Artifacts</h2>
          {onClose && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
        <div className="flex-1 flex items-center justify-center text-muted-foreground">
          <div className="text-center">
            <FileCode className="h-12 w-12 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No artifacts yet</p>
            <p className="text-xs mt-1">Generated code will appear here</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn(
      'flex flex-col bg-background border-l transition-all',
      isExpanded ? 'fixed inset-0 z-50' : 'h-full'
    )}>
      {/* Header */}
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-sm">Artifacts</h2>
          <span className="text-xs text-muted-foreground">({artifacts.length})</span>
          {hasVersions && (
            <div className="flex items-center gap-1">
              <History className="h-3 w-3 text-muted-foreground" />
              <select
                value={selectedTaskId || 'latest'}
                onChange={(e) => handleVersionChange(e.target.value)}
                className="h-7 text-xs bg-background border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="latest">Latest</option>
                {tasks.map((task) => (
                  <option key={task.id} value={task.id}>
                    {formatVersionLabel(task)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <div className="flex items-center gap-1">
          {sessionId && artifacts.length > 0 && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={handleDownloadZip}
              disabled={isDownloading}
              title="Download all as ZIP"
            >
              <Archive className={cn("h-4 w-4", isDownloading && "animate-pulse")} />
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
          {onClose && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Artifact tabs */}
      {artifacts.length > 1 && (
        <div className="flex border-b overflow-x-auto">
          {artifacts.map((artifact) => (
            <button
              key={artifact.id}
              onClick={() => setSelectedArtifactId(artifact.id)}
              className={cn(
                'px-3 py-2 text-sm whitespace-nowrap border-b-2 transition-colors',
                selectedArtifactId === artifact.id
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              {artifact.type === 'code' ? artifact.filename : artifact.name}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {selectedArtifact && selectedArtifact.type === 'code' && (
          <CodeBlock
            content={selectedArtifact.content}
            language={selectedArtifact.language}
            filename={selectedArtifact.filename}
          />
        )}
        {selectedArtifact && selectedArtifact.type === 'project' && (
          <ProjectViewer project={selectedArtifact} />
        )}
      </div>
    </div>
  );
}
