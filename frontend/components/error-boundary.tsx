"use client";

import React from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  children: React.ReactNode;
  /** 每次导航（路由变化）时由父组件传入递增 key，触发重置 */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  /** resetKey 变化时清除错误，恢复子树渲染 */
  componentDidUpdate(prevProps: Props) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  private handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
          <AlertTriangle className="size-10 text-destructive" />
          <h2 className="text-lg font-semibold">页面出了点问题</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            {this.state.error.message || "渲染过程中发生了意外错误"}
          </p>
          <Button onClick={this.handleReset} variant="outline" size="sm">
            <RotateCcw className="size-4" />
            重试
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
