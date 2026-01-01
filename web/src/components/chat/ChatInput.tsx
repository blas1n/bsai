'use client';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Loader2, Send, StopCircle } from 'lucide-react';
import { KeyboardEvent, useEffect, useRef, useState } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  onCancel?: () => void;
  isLoading?: boolean;
  isStreaming?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  onCancel,
  isLoading = false,
  isStreaming = false,
  disabled = false,
  placeholder = 'Type your message...',
}: ChatInputProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [value]);

  const handleSubmit = () => {
    if (value.trim() && !isLoading && !disabled) {
      onSend(value.trim());
      setValue('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t bg-background p-4">
      <div className="mx-auto max-w-3xl">
        <div className="relative flex items-end gap-2 rounded-lg border bg-background p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isLoading || disabled}
            rows={1}
            className={cn(
              'flex-1 resize-none bg-transparent px-2 py-1.5 text-sm',
              'placeholder:text-muted-foreground',
              'focus:outline-none',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'max-h-[200px] min-h-[36px]'
            )}
          />
          {isStreaming ? (
            <Button
              onClick={onCancel}
              variant="destructive"
              size="icon"
              className="h-8 w-8 shrink-0"
              title="Stop generation"
            >
              <StopCircle className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              onClick={handleSubmit}
              disabled={!value.trim() || isLoading || disabled}
              size="icon"
              className="h-8 w-8 shrink-0"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Press Enter to send, Shift + Enter for new line
        </p>
      </div>
    </div>
  );
}
