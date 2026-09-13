import { Component, type ErrorInfo, type ReactNode } from 'react'
import { appLog } from './logging'

type Props = { children: ReactNode }
type State = { hasError: boolean; message: string }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || 'Something went wrong' }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    appLog.error('react_error_boundary', { componentStack: info.componentStack }, error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-banner" role="alert" style={{ margin: 24 }}>
          <strong>UI error</strong>
          <span>{this.state.message}</span>
          <button type="button" onClick={() => this.setState({ hasError: false, message: '' })}>
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
