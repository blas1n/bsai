/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';

// Mock UI components that may not exist
jest.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span data-testid="tooltip-content">{children}</span>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) => <>{children}</>,
}));

jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, className, onClick, variant }: { children: React.ReactNode; className?: string; onClick?: () => void; variant?: string }) => (
    <span className={className} onClick={onClick} data-testid="badge" data-variant={variant}>
      {children}
    </span>
  ),
}));

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, className, onClick, variant, size }: { children: React.ReactNode; className?: string; onClick?: () => void; variant?: string; size?: string }) => (
    <button className={className} onClick={onClick} data-testid="button" data-variant={variant} data-size={size}>
      {children}
    </button>
  ),
}));

import { LangfuseTraceLink } from '@/components/debug/LangfuseTraceLink';

// Mock window.open
const mockOpen = jest.fn();
Object.defineProperty(window, 'open', {
  value: mockOpen,
  writable: true,
});

describe('LangfuseTraceLink', () => {
  beforeEach(() => {
    mockOpen.mockClear();
  });

  describe('when traceUrl is null or undefined', () => {
    it('returns null when traceUrl is null', () => {
      const { container } = render(<LangfuseTraceLink traceUrl={null} />);
      expect(container.firstChild).toBeNull();
    });

    it('returns null when traceUrl is undefined', () => {
      const { container } = render(<LangfuseTraceLink traceUrl={undefined} />);
      expect(container.firstChild).toBeNull();
    });

    it('returns null when traceUrl is empty string', () => {
      const { container } = render(<LangfuseTraceLink traceUrl="" />);
      expect(container.firstChild).toBeNull();
    });
  });

  describe('badge variant (default)', () => {
    it('renders badge with trace text by default', () => {
      render(<LangfuseTraceLink traceUrl="http://localhost:13001/trace/123" />);
      expect(screen.getByText('Trace')).toBeInTheDocument();
    });

    it('opens trace URL in new tab when clicked', () => {
      render(<LangfuseTraceLink traceUrl="http://localhost:13001/trace/123" />);

      // Find the badge element by its text content
      const badge = screen.getByText('Trace').closest('div, span, button');
      if (badge) {
        fireEvent.click(badge);
        expect(mockOpen).toHaveBeenCalledWith(
          'http://localhost:13001/trace/123',
          '_blank',
          'noopener,noreferrer'
        );
      }
    });

    it('hides label when showLabel is false', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          showLabel={false}
        />
      );
      expect(screen.queryByText('Trace')).not.toBeInTheDocument();
    });

    it('applies custom className', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          className="custom-class"
        />
      );
      // The badge should have the custom class
      const badge = screen.getByText('Trace').closest('[class*="custom-class"]');
      expect(badge).toBeInTheDocument();
    });
  });

  describe('button variant', () => {
    it('renders button with "View Trace" text', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          variant="button"
        />
      );
      expect(screen.getByText('View Trace')).toBeInTheDocument();
    });

    it('opens trace URL in new tab when clicked', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          variant="button"
        />
      );

      const button = screen.getByRole('button');
      fireEvent.click(button);

      expect(mockOpen).toHaveBeenCalledWith(
        'http://localhost:13001/trace/123',
        '_blank',
        'noopener,noreferrer'
      );
    });

    it('hides label when showLabel is false', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          variant="button"
          showLabel={false}
        />
      );
      expect(screen.queryByText('View Trace')).not.toBeInTheDocument();
    });
  });

  describe('icon variant', () => {
    it('renders icon button with aria-label', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          variant="icon"
        />
      );
      const button = screen.getByRole('button', { name: 'View trace in Langfuse' });
      expect(button).toBeInTheDocument();
    });

    it('opens trace URL in new tab when clicked', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          variant="icon"
        />
      );

      const button = screen.getByRole('button', { name: 'View trace in Langfuse' });
      fireEvent.click(button);

      expect(mockOpen).toHaveBeenCalledWith(
        'http://localhost:13001/trace/123',
        '_blank',
        'noopener,noreferrer'
      );
    });
  });

  describe('security', () => {
    it('opens with noopener and noreferrer', () => {
      render(
        <LangfuseTraceLink
          traceUrl="http://localhost:13001/trace/123"
          variant="button"
        />
      );

      const button = screen.getByRole('button');
      fireEvent.click(button);

      expect(mockOpen).toHaveBeenCalledWith(
        expect.any(String),
        '_blank',
        'noopener,noreferrer'
      );
    });
  });
});
