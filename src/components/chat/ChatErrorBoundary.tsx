import { Component, type ReactNode } from "react";

type Props = { children: ReactNode; onReset: () => void };

/** Keeps a rendering bug in one chat message from blanking the whole help page: shows a way back instead. */
export class ChatErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("chat widget crashed", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="store-chat-panel store-chat-crashed" role="alert">
        <p>Something went wrong in the chat. Your question was not lost on our side.</p>
        <button
          className="store-chat-help-button dark"
          onClick={() => {
            this.setState({ failed: false });
            this.props.onReset();
          }}
          type="button"
        >
          Start a new chat
        </button>
      </section>
    );
  }
}
