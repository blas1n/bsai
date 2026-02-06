'use client';

import { useState, useCallback } from 'react';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

type ValidationTypeKey = 'static' | 'lint' | 'typecheck' | 'test' | 'build';

export interface QAConfig {
  validations: ValidationTypeKey[];
  testCommand?: string;
  lintCommand?: string;
  allowLintWarnings: boolean;
  requireAllTestsPass: boolean;
}

interface QAConfigFormProps {
  initialConfig?: QAConfig;
  onSave: (config: QAConfig) => void;
}

const validationOptions: { key: ValidationTypeKey; label: string; description: string }[] = [
  { key: 'static', label: 'Static Analysis', description: 'Run static code analysis' },
  { key: 'lint', label: 'Linting', description: 'Check code style and formatting' },
  { key: 'typecheck', label: 'Type Check', description: 'Verify TypeScript types' },
  { key: 'test', label: 'Tests', description: 'Run unit and integration tests' },
  { key: 'build', label: 'Build', description: 'Verify the project builds successfully' },
];

const defaultConfig: QAConfig = {
  validations: ['lint', 'typecheck'],
  testCommand: undefined,
  lintCommand: undefined,
  allowLintWarnings: true,
  requireAllTestsPass: true,
};

export function QAConfigForm({ initialConfig, onSave }: QAConfigFormProps) {
  const [validations, setValidations] = useState<ValidationTypeKey[]>(
    initialConfig?.validations ?? defaultConfig.validations
  );
  const [testCommand, setTestCommand] = useState(
    initialConfig?.testCommand ?? ''
  );
  const [lintCommand, setLintCommand] = useState(
    initialConfig?.lintCommand ?? ''
  );
  const [allowLintWarnings, setAllowLintWarnings] = useState(
    initialConfig?.allowLintWarnings ?? defaultConfig.allowLintWarnings
  );
  const [requireAllTestsPass, setRequireAllTestsPass] = useState(
    initialConfig?.requireAllTestsPass ?? defaultConfig.requireAllTestsPass
  );

  const handleValidationToggle = useCallback((key: ValidationTypeKey) => {
    setValidations((prev) => {
      if (prev.includes(key)) {
        return prev.filter((v) => v !== key);
      }
      return [...prev, key];
    });
  }, []);

  const handleSave = useCallback(() => {
    onSave({
      validations,
      testCommand: testCommand.trim() || undefined,
      lintCommand: lintCommand.trim() || undefined,
      allowLintWarnings,
      requireAllTestsPass,
    });
  }, [validations, testCommand, lintCommand, allowLintWarnings, requireAllTestsPass, onSave]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">QA Configuration</CardTitle>
        <CardDescription>
          Configure quality assurance validations for task outputs
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Validation Types */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Validation Types</Label>
          <div className="space-y-2">
            {validationOptions.map((option) => (
              <div
                key={option.key}
                className="flex items-start space-x-3 rounded-md border p-3 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => handleValidationToggle(option.key)}
              >
                <Checkbox
                  id={`validation-${option.key}`}
                  checked={validations.includes(option.key)}
                  onCheckedChange={() => handleValidationToggle(option.key)}
                />
                <div className="space-y-1">
                  <Label
                    htmlFor={`validation-${option.key}`}
                    className="text-sm font-medium cursor-pointer"
                  >
                    {option.label}
                  </Label>
                  <p className="text-xs text-muted-foreground">{option.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Custom Commands */}
        <div className="space-y-4">
          <Label className="text-sm font-medium">Custom Commands</Label>

          {validations.includes('lint') && (
            <div className="space-y-2">
              <Label htmlFor="lintCommand" className="text-xs text-muted-foreground">
                Lint Command (optional)
              </Label>
              <Input
                id="lintCommand"
                placeholder="e.g., npm run lint"
                value={lintCommand}
                onChange={(e) => setLintCommand(e.target.value)}
              />
            </div>
          )}

          {validations.includes('test') && (
            <div className="space-y-2">
              <Label htmlFor="testCommand" className="text-xs text-muted-foreground">
                Test Command (optional)
              </Label>
              <Input
                id="testCommand"
                placeholder="e.g., npm test"
                value={testCommand}
                onChange={(e) => setTestCommand(e.target.value)}
              />
            </div>
          )}
        </div>

        {/* Additional Options */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Options</Label>
          <div className="space-y-3">
            {validations.includes('lint') && (
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="allowLintWarnings"
                  checked={allowLintWarnings}
                  onCheckedChange={(checked) => setAllowLintWarnings(checked === true)}
                />
                <Label htmlFor="allowLintWarnings" className="text-sm cursor-pointer">
                  Allow lint warnings (only fail on errors)
                </Label>
              </div>
            )}
            {validations.includes('test') && (
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="requireAllTestsPass"
                  checked={requireAllTestsPass}
                  onCheckedChange={(checked) => setRequireAllTestsPass(checked === true)}
                />
                <Label htmlFor="requireAllTestsPass" className="text-sm cursor-pointer">
                  Require all tests to pass
                </Label>
              </div>
            )}
          </div>
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
