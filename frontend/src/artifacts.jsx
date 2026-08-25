import React, { useState } from "react";
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

function ArtifactUpload({ authenticated }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [artifactType, setArtifactType] = useState("other");
  const [visibility, setVisibility] = useState("members");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  if (!authenticated) {
    return <p className="meta">Log in to upload scores, tracks, images, and other shared files.</p>;
  }

  const submit = async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!file) {
      setStatus("Choose a file before uploading.");
      return;
    }

    const form = new FormData();
    form.append("title", title || file.name);
    form.append("description", description);
    form.append("artifact_type", artifactType);
    form.append("visibility", visibility);
    form.append("tags", tags);
    form.append("file", file);

    try {
      setSaving(true);
      setStatus("");
      await api("/api/artifacts/upload/", { method: "POST", body: form });
      setTitle("");
      setDescription("");
      setArtifactType("other");
      setVisibility("members");
      setTags("");
      setFile(null);
      formElement.reset();
      setStatus("Upload complete. Refreshing list...");
      window.location.assign("/artifacts/");
    } catch (error) {
      setStatus(error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="upload-form artifact-page-upload-form" onSubmit={submit}>
      <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Title defaults to filename" />
      <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows="2" placeholder="Short description" />
      <div className="split-fields">
        <select value={artifactType} onChange={(event) => setArtifactType(event.target.value)}>
          <option value="pdf">PDF</option>
          <option value="audio">Audio</option>
          <option value="image">Image</option>
          <option value="artwork">Artwork</option>
          <option value="other">Other</option>
        </select>
        <select value={visibility} onChange={(event) => setVisibility(event.target.value)}>
          <option value="members">Members</option>
          <option value="public">Public</option>
          <option value="private">Private</option>
        </select>
      </div>
      <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Tags, comma-separated" />
      <input type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} />
      <div className="composer-actions">
        <button className="primary-button" type="submit" disabled={saving}>{saving ? "Uploading..." : "Upload"}</button>
      </div>
      {status && <p className="meta">{status}</p>}
    </form>
  );
}

const root = document.getElementById("artifact-upload-app");
const authenticated = root?.dataset.authenticated === "true";

if (root) {
  createRoot(root).render(<ArtifactUpload authenticated={authenticated} />);
}
