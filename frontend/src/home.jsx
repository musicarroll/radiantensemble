import React, { useEffect, useState } from "react";
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
    let message = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      message = data.error || message;
    } catch (_error) {
      // Keep the HTTP status fallback when the response body is not JSON.
    }
    throw new Error(message);
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

function LinkifiedText({ text }) {
  const urlPattern = /(https?:\/\/[^\s<]+|www\.[^\s<]+)/gi;
  const parts = [];
  let lastIndex = 0;

  for (const match of text.matchAll(urlPattern)) {
    const rawUrl = match[0];
    const start = match.index;
    const trailingPunctuation = rawUrl.match(/[),.;:!?]+$/)?.[0] || "";
    const url = trailingPunctuation ? rawUrl.slice(0, -trailingPunctuation.length) : rawUrl;
    const href = url.startsWith("www.") ? `https://${url}` : url;

    if (start > lastIndex) {
      parts.push(text.slice(lastIndex, start));
    }
    parts.push(
      <a href={href} target="_blank" rel="noopener noreferrer" key={`${start}-${url}`}>
        {url}
      </a>
    );
    if (trailingPunctuation) {
      parts.push(trailingPunctuation);
    }
    lastIndex = start + rawUrl.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.map((part, index) => {
    if (typeof part !== "string") return part;
    return part.split("\n").map((line, lineIndex, lines) => (
      <React.Fragment key={`${index}-${lineIndex}`}>
        {line}
        {lineIndex < lines.length - 1 && <br />}
      </React.Fragment>
    ));
  });
}

function useDashboardData() {
  const [state, setState] = useState({
    me: null,
    feed: { posts: [], members: [] },
    threads: [],
    loading: true,
    error: ""
  });

  const refresh = async () => {
    try {
      const [me, feed] = await Promise.all([
        api("/api/me/"),
        api("/api/home-feed/")
      ]);
      let threads = { threads: [] };
      if (me.authenticated) {
        threads = await api("/api/threads/");
      }
      setState({
        me,
        feed,
        threads: threads.threads,
        loading: false,
        error: ""
      });
    } catch (error) {
      setState((current) => ({ ...current, loading: false, error: error.message }));
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  return { state, refresh };
}

function Composer({ me, onPostCreated }) {
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState("members");
  const [pinned, setPinned] = useState(false);
  const [saving, setSaving] = useState(false);
  const authenticated = me?.authenticated;
  const canPin = me?.user?.isStaff;

  if (!authenticated) {
    return (
      <section className="composer">
        <h2>Member Space</h2>
        <p className="meta">Log in to post updates, message ensemble members, and share musical artifacts.</p>
        <a className="primary-button" href="/accounts/login/">Log in</a>
      </section>
    );
  }

  const submit = async (event) => {
    event.preventDefault();
    if (!body.trim()) return;
    const form = new FormData();
    form.append("title", title);
    form.append("body", body);
    form.append("visibility", visibility);
    if (canPin) {
      form.append("pinned", pinned ? "true" : "false");
    }
    setSaving(true);
    await api("/api/posts/", { method: "POST", body: form });
    setTitle("");
    setBody("");
    setPinned(false);
    setSaving(false);
    onPostCreated();
  };

  return (
    <form className="composer" onSubmit={submit}>
      <h2>Share an Update</h2>
      <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Optional title" />
      <textarea value={body} onChange={(event) => setBody(event.target.value)} rows="4" placeholder="Post rehearsal notes, questions, announcements, or ideas." />
      <select value={visibility} onChange={(event) => setVisibility(event.target.value)}>
        <option value="members">Members only</option>
        <option value="public">Public</option>
        <option value="private">Private draft</option>
      </select>
      {canPin && (
        <label className="checkbox-row">
          <input type="checkbox" checked={pinned} onChange={(event) => setPinned(event.target.checked)} />
          <span>Keep this post on top</span>
        </label>
      )}
      <div className="composer-actions">
        <button className="primary-button" type="submit" disabled={saving}>{saving ? "Posting..." : "Post"}</button>
      </div>
    </form>
  );
}

function LeftRail({ members, me }) {
  return (
    <aside className="rail feed-stack">
      <section className="panel">
        <h2>Members</h2>
        <div className="member-list">
          {members.map((member) => (
            <a className="member-link" href={member.profileUrl || "#"} key={member.id}>
              <span className="avatar" style={{ background: member.accentColor }}>{member.displayName.slice(0, 1)}</span>
              {member.displayName}
            </a>
          ))}
          {!members.length && <p className="meta">Member profiles will appear here.</p>}
        </div>
      </section>
      <section className="panel">
        <h2>Account</h2>
        {me?.authenticated ? (
          <>
            <p className="meta">Signed in as {me.user.displayName}</p>
            <nav className="account-links" aria-label="Account navigation">
              <a href="/members/me/edit/">My Profile</a>
              <a href="/bugs/">Bug Reports</a>
              <a href="/features/">Feature Requests</a>
              {me.user.isStaff && <a href="/admin/">Admin</a>}
            </nav>
          </>
        ) : <p className="meta">Public visitor view</p>}
      </section>
    </aside>
  );
}

function PostCard({ post, me, onUpdated }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(post.title);
  const [body, setBody] = useState(post.body);
  const [visibility, setVisibility] = useState(post.visibility);
  const [pinned, setPinned] = useState(post.pinned);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const canEdit = me?.authenticated && me.user.id === post.owner.id;
  const canPinOwnPost = canEdit && me?.user?.isStaff;
  const canModeratePin = me?.authenticated && me.user.isStaff;

  const cancelEdit = () => {
    setTitle(post.title);
    setBody(post.body);
    setVisibility(post.visibility);
    setPinned(post.pinned);
    setStatus("");
    setEditing(false);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!body.trim()) {
      setStatus("Post body is required.");
      return;
    }
    const form = new FormData();
    form.append("title", title);
    form.append("body", body);
    form.append("visibility", visibility);
    if (canPinOwnPost) {
      form.append("pinned", pinned ? "true" : "false");
    }
    try {
      setSaving(true);
      setStatus("");
      await api(`/api/posts/${post.id}/`, { method: "POST", body: form });
      setEditing(false);
      onUpdated();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  const togglePinned = async () => {
    const form = new FormData();
    form.append("pinned", post.pinned ? "false" : "true");
    try {
      setSaving(true);
      setStatus("");
      await api(`/api/posts/${post.id}/pin/`, { method: "POST", body: form });
      onUpdated();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  const deletePost = async () => {
    if (!window.confirm("Delete this post? This cannot be undone.")) return;
    try {
      setSaving(true);
      setStatus("");
      await api(`/api/posts/${post.id}/delete/`, { method: "POST" });
      onUpdated();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <article className="post">
        <form className="edit-post-form" onSubmit={submit}>
          <h2>Edit Post</h2>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Optional title" />
          <textarea value={body} onChange={(event) => setBody(event.target.value)} rows="5" />
          <select value={visibility} onChange={(event) => setVisibility(event.target.value)}>
            <option value="members">Members only</option>
            <option value="public">Public</option>
            <option value="private">Private draft</option>
          </select>
          {canPinOwnPost && (
            <label className="checkbox-row">
              <input type="checkbox" checked={pinned} onChange={(event) => setPinned(event.target.checked)} />
              <span>Keep this post on top</span>
            </label>
          )}
          <div className="post-actions">
            <button className="danger-button" type="button" onClick={deletePost} disabled={saving}>Delete</button>
            <button className="secondary-button" type="button" onClick={cancelEdit}>Cancel</button>
            <button className="primary-button" type="submit" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
          </div>
          {status && <p className="meta">{status}</p>}
        </form>
      </article>
    );
  }

  return (
    <article className="post">
      <div className="post-header">
        <p className="meta">{post.owner.displayName} · {new Date(post.createdAt).toLocaleString()} · {post.visibility}{post.pinned ? " · pinned" : ""}</p>
        <div className="post-header-actions">
          {canModeratePin && <button className="text-button" type="button" onClick={togglePinned} disabled={saving}>{post.pinned ? "Unpin" : "Pin"}</button>}
          {canEdit && <button className="text-button" type="button" onClick={() => setEditing(true)}>Edit</button>}
        </div>
      </div>
      {post.pinned && <span className="pin-badge">Pinned</span>}
      {post.title && <h2>{post.title}</h2>}
      <p><LinkifiedText text={post.body} /></p>
    </article>
  );
}

function Feed({ posts, me, onPostUpdated }) {
  return (
    <section className="feed feed-stack">
      <div className="hero-band home-graphic">
        <img src="/static/community/images/radiant_graphic.png" alt="Radiant Ensemble" />
      </div>
      {posts.map((post) => (
        <PostCard post={post} me={me} onUpdated={onPostUpdated} key={post.id} />
      ))}
      {!posts.length && <article className="post"><p className="meta">No visible posts yet.</p></article>}
    </section>
  );
}

function MessagingWidget({ authenticated, members, me, threads, onChanged }) {
  const [recipientId, setRecipientId] = useState("");
  const [newThreadBody, setNewThreadBody] = useState("");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  const messageableMembers = members.filter((member) => member.id !== me?.user?.id);

  if (!authenticated) {
    return <p className="meta">Member login is required for direct and group messaging.</p>;
  }

  const startThread = async (event) => {
    event.preventDefault();
    if (!recipientId) {
      setStatus("Choose a member to message.");
      return;
    }
    const form = new FormData();
    form.append("recipient_id", recipientId);
    form.append("body", newThreadBody);
    try {
      setSaving(true);
      setStatus("");
      const data = await api("/api/threads/create-direct/", { method: "POST", body: form });
      setRecipientId("");
      setNewThreadBody("");
      await onChanged();
      window.location.assign(`/messages/${data.thread.id}/`);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="message-widget">
      <form className="message-form" onSubmit={startThread}>
        <select value={recipientId} onChange={(event) => setRecipientId(event.target.value)}>
          <option value="">New direct message...</option>
          {messageableMembers.map((member) => (
            <option value={member.id} key={member.id}>{member.displayName}</option>
          ))}
        </select>
        <textarea value={newThreadBody} onChange={(event) => setNewThreadBody(event.target.value)} rows="2" placeholder="Optional first message" />
        <div className="composer-actions">
          <button className="primary-button" type="submit" disabled={saving}>Start</button>
        </div>
      </form>

      <div className="thread-list thread-list-scroll">
        {threads.map((thread) => (
          <a className="thread" href={`/messages/${thread.id}/`} key={thread.id}>
            <strong>{thread.title}</strong>
            <span>{thread.lastMessage || "No messages yet."}</span>
          </a>
        ))}
        {!threads.length && <p className="meta">No message threads yet.</p>}
      </div>
      {status && <p className="meta">{status}</p>}
    </div>
  );
}

function RightPanel({ threads, authenticated, members, me, onMessagesChanged }) {
  return (
    <aside className="side-panel feed-stack">
      <section className="panel">
        <h2>Messages</h2>
        <MessagingWidget authenticated={authenticated} members={members} me={me} threads={threads} onChanged={onMessagesChanged} />
      </section>
    </aside>
  );
}

function App() {
  const { state, refresh } = useDashboardData();
  if (state.loading) return <section className="loading-shell"><h1>Radiant Ensemble</h1><p>Loading member space...</p></section>;
  if (state.error) return <section className="loading-shell"><h1>Radiant Ensemble</h1><p>{state.error}</p></section>;

  return (
    <div className="app-shell">
      <LeftRail members={state.feed.members} me={state.me} />
      <main className="feed-stack">
        <Composer me={state.me} onPostCreated={refresh} />
        <Feed posts={state.feed.posts} me={state.me} onPostUpdated={refresh} />
      </main>
      <RightPanel
        threads={state.threads}
        authenticated={state.me.authenticated}
        members={state.feed.members}
        me={state.me}
        onMessagesChanged={refresh}
      />
    </div>
  );
}

createRoot(document.getElementById("radiant-home")).render(<App />);
