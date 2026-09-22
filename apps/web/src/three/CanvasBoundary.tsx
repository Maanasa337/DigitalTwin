import { Component, type ReactNode } from 'react';

interface CanvasBoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
}

/**
 * A browser without WebGL (or with it disabled) makes the R3F canvas throw on mount; this keeps the
 * rest of the page alive and shows `fallback` instead.
 */
export class CanvasBoundary extends Component<CanvasBoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
