import { Component, type ErrorInfo, type ReactNode } from "react";

import { AlertTriangle, RotateCcw, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/Button";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  private handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="flex flex-col items-center justify-center gap-4 p-8 text-center min-h-[200px]">
        <AlertTriangle className="h-10 w-10 text-warning" />
        <h2 className="text-lg font-semibold text-text-primary">
          Something went wrong
        </h2>
        {import.meta.env.DEV && this.state.error && (
          <pre className="max-w-xl overflow-auto rounded-lg bg-surface-2 p-3 text-left text-xs text-text-secondary">
            {this.state.error.message}
          </pre>
        )}
        <div className="flex gap-3">
          <Button variant="secondary" size="sm" onClick={this.handleRetry}>
            <RotateCcw className="h-4 w-4" />
            Try Again
          </Button>
          <Button variant="ghost" size="sm" onClick={this.handleReload}>
            <RefreshCw className="h-4 w-4" />
            Reload App
          </Button>
        </div>
      </div>
    );
  }
}
