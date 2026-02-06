'use client';

import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface LintResult {
  success: boolean;
  errors: number;
  warnings: number;
}

interface TypecheckResult {
  success: boolean;
  errors: number;
}

interface TestResult {
  success: boolean;
  passed: number;
  failed: number;
  coverage?: number;
}

interface BuildResult {
  success: boolean;
}

export interface QAResult {
  decision: 'PASS' | 'RETRY';
  confidence: number;
  summary: string;
  lint?: LintResult;
  typecheck?: TypecheckResult;
  test?: TestResult;
  build?: BuildResult;
}

interface QAResultCardProps {
  result: QAResult;
}

function ResultIcon({ success }: { success: boolean }) {
  return success ? (
    <CheckCircle className="h-4 w-4 text-green-500" />
  ) : (
    <XCircle className="h-4 w-4 text-red-500" />
  );
}

function ValidationItem({
  label,
  success,
  children,
}: {
  label: string;
  success: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b last:border-b-0">
      <div className="flex items-center gap-2">
        <ResultIcon success={success} />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="text-sm text-muted-foreground">{children}</div>
    </div>
  );
}

export function QAResultCard({ result }: QAResultCardProps) {
  const { decision, confidence, summary, lint, typecheck, test, build } = result;

  const isPass = decision === 'PASS';
  const confidencePercent = Math.round(confidence * 100);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            {isPass ? (
              <CheckCircle className="h-5 w-5 text-green-500" />
            ) : (
              <XCircle className="h-5 w-5 text-red-500" />
            )}
            QA Result
          </CardTitle>
          <Badge
            variant={isPass ? 'default' : 'destructive'}
            className={cn(
              isPass && 'bg-green-500 hover:bg-green-600'
            )}
          >
            {decision}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Confidence */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Confidence</span>
            <span className="font-medium">{confidencePercent}%</span>
          </div>
          <Progress value={confidencePercent} className="h-2" />
        </div>

        {/* Validation Results */}
        <div className="rounded-md border">
          {lint && (
            <ValidationItem label="Lint" success={lint.success}>
              <div className="flex items-center gap-3">
                {lint.errors > 0 && (
                  <span className="flex items-center gap-1 text-red-500">
                    <XCircle className="h-3 w-3" />
                    {lint.errors} error{lint.errors !== 1 && 's'}
                  </span>
                )}
                {lint.warnings > 0 && (
                  <span className="flex items-center gap-1 text-amber-500">
                    <AlertTriangle className="h-3 w-3" />
                    {lint.warnings} warning{lint.warnings !== 1 && 's'}
                  </span>
                )}
                {lint.errors === 0 && lint.warnings === 0 && (
                  <span className="text-green-500">No issues</span>
                )}
              </div>
            </ValidationItem>
          )}

          {typecheck && (
            <ValidationItem label="Type Check" success={typecheck.success}>
              {typecheck.errors > 0 ? (
                <span className="text-red-500">
                  {typecheck.errors} error{typecheck.errors !== 1 && 's'}
                </span>
              ) : (
                <span className="text-green-500">No errors</span>
              )}
            </ValidationItem>
          )}

          {test && (
            <ValidationItem label="Tests" success={test.success}>
              <div className="flex items-center gap-3">
                <span className="text-green-500">
                  {test.passed} passed
                </span>
                {test.failed > 0 && (
                  <span className="text-red-500">
                    {test.failed} failed
                  </span>
                )}
                {test.coverage !== undefined && (
                  <span className="text-muted-foreground">
                    {test.coverage}% coverage
                  </span>
                )}
              </div>
            </ValidationItem>
          )}

          {build && (
            <ValidationItem label="Build" success={build.success}>
              {build.success ? (
                <span className="text-green-500">Success</span>
              ) : (
                <span className="text-red-500">Failed</span>
              )}
            </ValidationItem>
          )}
        </div>

        {/* Summary */}
        <div className="space-y-2">
          <span className="text-sm font-medium">Summary</span>
          <p className="text-sm text-muted-foreground rounded-md bg-muted p-3">
            {summary}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
