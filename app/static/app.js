const $ = (sel) => document.querySelector(sel);
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const els = {
  form: $("#analyze-form"),
  url: $("#url"),
  formError: $("#form-error"),
  loading: $("#loading"),
  status: $("#status-text"),
  results: $("#results"),
  empty: $("#empty"),
  error: $("#error"),
  errorTitle: $("#error-title"),
  errorBody: $("#error-body"),
  errorNext: $("#error-next"),
  title: $("#video-title"),
  kicker: $("#meta-kicker"),
  watch: $("#watch-link"),
  standfirst: $("#standfirst"),
  ledger: $("#ledger"),
  ledgerNote: $("#ledger-note"),
  slate: $("#slate"),
  templateNote: $("#template-note"),
  downloadMd: $("#download-md"),
  downloadJson: $("#download-json"),
  colophon: $("#colophon-text"),
};

let payload = null;
let stepTimer = null;

const STEPS = [
  "Fetching comments…",
  "Finding questions…",
  "Grouping what repeats…",
  "Drafting ideas…",
];

const ERRORS = {
  invalid_url: {
    title: "That URL does not look right",
    next: "Use a link like https://www.youtube.com/watch?v=… or a bare 11-character video ID.",
  },
  video_unavailable: {
    title: "This video is not reachable",
    next: "It may be private, deleted or age-restricted. Try another public video.",
  },
  comments_disabled: {
    title: "Comments are turned off",
    next: "There is nothing to mine here. Try a video with an active comment section.",
  },
  rate_limited: {
    title: "YouTube is pushing back",
    next: "Wait a minute, then try again. Smaller comment caps are less likely to trip the limit.",
  },
  too_many_requests: {
    title: "Slow down a moment",
    next: "This tool accepts a handful of analyses per minute. Try again shortly.",
  },
  fetch_failed: {
    title: "We could not read the comments",
    next: "YouTube may be blocking the request. Retry once, or try a smaller cap.",
  },
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function show(el) {
  el.hidden = false;
}
function hide(...nodes) {
  nodes.forEach((n) => (n.hidden = true));
}

function setStatus(text) {
  els.status.textContent = text;
}

function startLoading() {
  hide(els.results, els.empty, els.error);
  show(els.loading);
  let i = 0;
  setStatus(STEPS[0]);
  clearInterval(stepTimer);
  stepTimer = setInterval(() => {
    i = Math.min(i + 1, STEPS.length - 1);
    setStatus(STEPS[i]);
  }, 2600);
}

function stopLoading() {
  clearInterval(stepTimer);
  hide(els.loading);
}

function formError(message) {
  els.formError.textContent = message;
  show(els.formError);
}

function clearFormError() {
  els.formError.textContent = "";
  hide(els.formError);
}

function showError(error) {
  const known = ERRORS[error?.code] || {
    title: "Something went wrong",
    next: "Try again. If it keeps failing, try another video.",
  };
  els.errorTitle.textContent = known.title;
  els.errorBody.textContent = error?.message || "The analysis could not finish.";
  els.errorNext.textContent = known.next;
  hide(els.results, els.empty);
  show(els.error);
}

function countUp(el, target) {
  if (reduceMotion || target < 10) {
    el.textContent = String(target);
    return;
  }
  const duration = 700;
  const start = performance.now();
  const tick = (now) => {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = String(Math.round(target * eased));
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function plural(n, word) {
  return Number(n) === 1 ? word : `${word}s`;
}

function quote(comment) {
  const likes = comment.likes ? ` · ${comment.likes} ${comment.likes === 1 ? "like" : "likes"}` : "";
  return `<figure class="example">
      <p>${esc(comment.text)}</p>
      <cite>— ${esc(comment.author || "a viewer")}${likes}</cite>
    </figure>`;
}

function ideaRow(idea) {
  return `<div class="idea">
      <span class="idea-title">${esc(idea.title)}</span>
      ${idea.angle ? `<span class="idea-angle">${esc(idea.angle)}</span>` : ""}
    </div>`;
}

function renderLedger(clusters) {
  els.ledger.innerHTML = clusters
    .map((cluster, index) => {
      const id = `detail-${cluster.rank}`;
      const examples = cluster.examples || [];
      const preview = examples[0];
      const rest = examples.slice(1);
      const ideas = cluster.ideas || [];
      const meta = `<p class="row-meta">
          <span class="row-count" data-count="${cluster.count}">0</span>
          <span>asked</span>
          <span>${cluster.likes} ${cluster.likes === 1 ? "like" : "likes"}</span>
        </p>`;

      return `<li class="row" data-open="false" style="--i:${index}">
        <div class="row-main">
          <span class="rank" aria-hidden="true">${String(cluster.rank).padStart(2, "0")}</span>
          <div class="row-body">
            <button class="row-toggle" type="button" aria-expanded="false" aria-controls="${id}">
              ${esc(cluster.canonical)}
            </button>
            ${meta}
            ${preview ? `<div class="preview">${quote(preview)}</div>` : ""}
            <div class="detail" id="${id}" hidden>
              ${rest.length ? `<div class="examples">${rest.map(quote).join("")}</div>` : ""}
              ${ideas.length ? `<div class="idea-list">${ideas.map(ideaRow).join("")}</div>` : ""}
              ${
                ideas.length
                  ? `<div class="chips">${ideas
                      .map(
                        (idea) =>
                          `<button class="chip" type="button" data-copy="${esc(idea.title)}">${esc(
                            idea.title,
                          )} <span>copy</span></button>`,
                      )
                      .join("")}</div>`
                  : ""
              }
            </div>
          </div>
          <div class="tally">
            <span class="tally-num" data-count="${cluster.count}">0</span>
            <span class="tally-label">asked</span>
            <span class="tally-likes">${cluster.likes} ${cluster.likes === 1 ? "like" : "likes"}</span>
          </div>
        </div>
      </li>`;
    })
    .join("");

  els.ledger.querySelectorAll(".row-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest(".row");
      const open = row.dataset.open !== "true";
      row.dataset.open = String(open);
      button.setAttribute("aria-expanded", String(open));
      const detail = document.getElementById(button.getAttribute("aria-controls"));
      detail.hidden = !open;
      const preview = row.querySelector(".preview");
      if (preview) preview.hidden = open;
    });
  });

  els.ledger.querySelectorAll("[data-count]").forEach((el) => {
    countUp(el, Number(el.dataset.count));
  });
}

function renderSlate(clusters) {
  const rows = [];
  clusters.forEach((cluster) => {
    (cluster.ideas || []).forEach((idea) => {
      rows.push({ idea, question: cluster.canonical });
    });
  });

  els.slate.innerHTML = rows
    .map(
      ({ idea, question }) => `<li>
        <div>
          <span class="slate-title">${esc(idea.title)}</span>
          ${idea.angle ? `<span class="slate-angle">${esc(idea.angle)}</span>` : ""}
          <span class="slate-from">from: ${esc(question)}</span>
        </div>
        <button class="copy" type="button" data-copy="${esc(idea.title)}">Copy</button>
      </li>`,
    )
    .join("");
}

function render(data) {
  payload = data;
  const stats = data.stats || {};
  const video = data.video || {};
  const clusters = data.clusters || [];

  els.kicker.textContent = video.author ? video.author : "Brief";
  els.title.textContent = video.title || "Untitled video";
  if (els.watch) {
    els.watch.href = video.url || "#";
    els.watch.hidden = !video.url;
  }
  els.standfirst.innerHTML = [
    `<b data-count="${stats.comments_analyzed || 0}">0</b> ${plural(stats.comments_analyzed, "comment")} analyzed`,
    `<b data-count="${stats.questions || 0}">0</b> ${plural(stats.questions, "question")}`,
    `<b data-count="${stats.groups || 0}">0</b> ${plural(stats.groups, "group")}`,
    new Date(data.generated_at || Date.now()).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    }),
  ].join(" · ");

  els.ledgerNote.textContent = `${stats.comments_analyzed || 0} analyzed${
    stats.capped ? " (capped)" : ""
  } · ranked by how often each question repeats`;

  hide(els.error);
  if (!clusters.length) {
    hide(els.results);
    show(els.empty);
    return;
  }

  renderLedger(clusters);
  renderSlate(clusters);
  els.templateNote.hidden = Boolean(stats.llm);
  els.colophon.innerHTML = `Set in Instrument Serif &amp; Space Mono · analyzed ${stats.comments_analyzed} ${plural(
    stats.comments_analyzed,
    "comment",
  )} · built from ${stats.questions} ${plural(stats.questions, "question")} · ${stats.groups} ${plural(
    stats.groups,
    "group",
  )}`;
  show(els.results);
  hide(els.empty);
  els.standfirst.querySelectorAll("[data-count]").forEach((el) => {
    countUp(el, Number(el.dataset.count));
  });
}

function download(name, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

els.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = els.url.value.trim();
  if (!url) {
    formError("Paste a video URL first.");
    els.url.focus();
    return;
  }
  clearFormError();

  const cap = Number(new FormData(els.form).get("cap") || 500);
  const order = new FormData(els.form).get("order") || "relevance";
  const submit = els.form.querySelector("button[type=submit]");
  submit.disabled = true;
  startLoading();

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, max_comments: cap, order }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      showError(data.error || { code: "server_error", message: "The analysis could not finish." });
      return;
    }
    render(data);
  } catch (err) {
    showError({ code: "network", message: "Could not reach the server. Check the connection and retry." });
  } finally {
    stopLoading();
    submit.disabled = false;
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  try {
    await navigator.clipboard.writeText(button.dataset.copy);
    button.dataset.done = "true";
    const original = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => {
      button.dataset.done = "false";
      button.textContent = original;
    }, 1400);
  } catch {
    /* clipboard unavailable: leave the label alone */
  }
});

els.downloadMd.addEventListener("click", () => {
  if (!payload) return;
  download(`brief-${payload.video.video_id}.md`, payload.markdown, "text/markdown");
});

els.downloadJson.addEventListener("click", () => {
  if (!payload) return;
  const { markdown, ...rest } = payload;
  download(
    `brief-${payload.video.video_id}.json`,
    JSON.stringify(rest, null, 2),
    "application/json",
  );
});

async function checkEngine() {
  const statusEl = document.getElementById("engine-status");
  const dotEl = document.getElementById("engine-dot");
  if (!statusEl || !dotEl) return;
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (data.llm) {
      statusEl.textContent = "Gemini LLM Active";
      dotEl.style.background = "#16a34a";
      dotEl.style.boxShadow = "0 0 8px rgba(22, 163, 74, 0.4)";
    } else {
      statusEl.textContent = "Template Engine";
      dotEl.style.background = "#eab308";
    }
  } catch {
    statusEl.textContent = "Engine Offline";
    dotEl.style.background = "#dc2626";
  }
}
checkEngine();
