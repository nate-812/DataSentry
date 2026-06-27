import { Send } from "lucide-react";
import { FormEvent, useState } from "react";

import { api } from "../api/client";
import type { ChatRunResponse, ChatSession } from "../api/types";

export function ChatPage() {
  const [session, setSession] = useState<ChatSession | null>(null);
  const [question, setQuestion] = useState("为什么K线不更新");
  const [result, setResult] = useState<ChatRunResponse | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      const activeSession = session ?? (await api.createSession("Kline 诊断"));
      setSession(activeSession);
      const response = await api.runQuestion(activeSession.id, trimmed);
      setResult(response);
      const eventText = await api.runEvents(response.run.id);
      setEvents(parseSseEvents(eventText));
    } catch {
      setError("诊断请求失败，请检查 API 服务");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-grid">
      <section className="panel span-2">
        <div className="panel-heading">
          <h2>对话诊断</h2>
          <span>{session ? session.title : "新会话"}</span>
        </div>
        <form className="question-form" onSubmit={submit}>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={6} />
          <button type="submit" title="提交诊断问题" disabled={busy || !question.trim()}>
            <Send size={16} aria-hidden="true" />
            {busy ? "诊断中" : "提交"}
          </button>
        </form>
        {error ? <p className="error-text">{error}</p> : null}
        {result ? (
          <article className="answer">
            <div className="answer-meta">
              <span>{result.run.status}</span>
              <span>{result.assistant_message.llm_status ?? "unknown"}</span>
            </div>
            <p>{result.assistant_message.content}</p>
          </article>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>事件</h2>
          <span>{events.length}</span>
        </div>
        <ul className="event-list">
          {events.map((item, index) => (
            <li key={`${item}-${index}`}>{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function parseSseEvents(text: string): string[] {
  return text
    .split("\n")
    .filter((line) => line.startsWith("event: "))
    .map((line) => line.replace("event: ", ""));
}
