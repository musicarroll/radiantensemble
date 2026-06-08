import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

const api = async (url, options = {}) => {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCookie("csrftoken"),
      ...(options.headers || {})
    },
    ...options
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
};

function getCookie(name) {
  return document.cookie
    .split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.split("=")[1] || "";
}

function ThreadApp() {
  const root = document.getElementById("radiant-thread");
  const threadId = root.dataset.threadId;
  const [detail, setDetail] = useState(null);
  const [me, setMe] = useState(null);
  const [replyBody, setReplyBody] = useState("");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const messageListRef = useRef(null);

  const load = async () => {
    const [meData, threadData] = await Promise.all([
      api("/api/me/"),
      api(`/api/threads/${threadId}/`)
    ]);
    setMe(meData);
    setDetail(threadData);
  };

  useEffect(() => {
    load().catch((error) => setStatus(error.message));
  }, [threadId]);

  useEffect(() => {
    const messageList = messageListRef.current;
    if (messageList) {
      messageList.scrollTop = messageList.scrollHeight;
    }
  }, [detail?.messages.length]);

  const sendReply = async (event) => {
    event.preventDefault();
    if (!replyBody.trim()) return;
    const form = new FormData();
    form.append("body", replyBody);
    try {
      setSaving(true);
      setStatus("");
      await api(`/api/threads/${threadId}/messages/`, { method: "POST", body: form });
      setReplyBody("");
      await load();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  if (!detail || !me) {
    return (
      <section className="loading-shell">
        <h1>Messages</h1>
        <p>{status || "Loading conversation..."}</p>
      </section>
    );
  }

  return (
    <section className="thread-page">
      <div className="thread-page-header">
        <div>
          <p className="eyebrow">Messages</p>
          <h1>{detail.thread.title}</h1>
          <p className="meta">{detail.thread.participants.map((participant) => participant.displayName).join(", ")}</p>
        </div>
        <a className="primary-button" href="/">Home</a>
      </div>

      <div className="message-list message-list-full" ref={messageListRef}>
        {detail.messages.map((message) => (
          <article className={`message ${message.sender.id === me.user.id ? "own-message" : ""}`} key={message.id}>
            <div className="message-heading">
              <strong>{message.sender.displayName}</strong>
              <span>{new Date(message.createdAt).toLocaleString()}</span>
            </div>
            {message.body && <p>{message.body}</p>}
            {message.attachmentUrl && <a href={message.attachmentUrl}>Attachment</a>}
          </article>
        ))}
        {!detail.messages.length && <p className="meta">No messages yet.</p>}
      </div>

      <form className="thread-reply-form" onSubmit={sendReply}>
        <textarea value={replyBody} onChange={(event) => setReplyBody(event.target.value)} rows="3" placeholder="Reply" />
        <div className="composer-actions">
          <button className="primary-button" type="submit" disabled={saving || !replyBody.trim()}>{saving ? "Sending..." : "Send"}</button>
        </div>
        {status && <p className="meta">{status}</p>}
      </form>
    </section>
  );
}

createRoot(document.getElementById("radiant-thread")).render(<ThreadApp />);
