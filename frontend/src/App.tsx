import DocumentPanel from "./components/DocumentPanel";
import ChatPanel from "./components/ChatPanel";

export default function App() {
  return (
    <div className="app">
      <header>
        <h1>DocAgent</h1>
      </header>
      <main>
        <aside>
          <DocumentPanel />
        </aside>
        <ChatPanel />
      </main>
    </div>
  );
}
