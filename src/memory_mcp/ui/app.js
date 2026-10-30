// Memory registry console. All memory text is untrusted: every node is built with
// createElement + textContent. The access token lives in sessionStorage, so an HTML
// injection here would leak it; never assign markup strings to the DOM.
(() => {
  "use strict";

  const TOKEN_KEY = "memory-mcp-token";
  const PAGE = 50;
  const KIND = { duplicate: "重复", internal_contradiction: "内部矛盾", multiple_current: "多条当前版本", contradiction: "矛盾" };
  const MUTATION = { initial: "初始", update: "更新", evolution: "演化", correction: "改正", reversal: "反转", refinement: "补充" };

  const $ = (id) => document.getElementById(id);
  const state = { view: "docket", findings: [], records: [], offset: 0, order: "created_at", type: "", query: "", selected: null, done: false };
  // Every list load and every case-file load takes a ticket; a response whose ticket is no
  // longer the latest belongs to a view, query or selection the person has already left.
  const tickets = { list: 0, file: 0 };
  const take = (kind) => ++tickets[kind];
  const stale = (kind, ticket) => ticket !== tickets[kind];

  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const stamp = (text, cls) => el("span", { class: "stamp " + (cls || ""), text });
  const when = (iso) => (iso ? iso.replace("T", " ").slice(0, 16) : "");

  let toastTimer;
  function toast(message, bad) {
    const t = $("toast");
    t.textContent = message;
    t.classList.toggle("bad", !!bad);
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, bad ? 6000 : 2500);
  }

  // ---- API ---------------------------------------------------------------
  class AuthError extends Error {}

  async function api(path, options = {}) {
    const token = sessionStorage.getItem(TOKEN_KEY);
    if (!token) throw new AuthError("no token");
    const res = await fetch("/api/v1" + path, {
      ...options,
      headers: { Authorization: "Bearer " + token, ...(options.body ? { "Content-Type": "application/json" } : {}) },
    });
    if (res.status === 401 || res.status === 403) {
      sessionStorage.removeItem(TOKEN_KEY);
      showLogin("令牌无效，请重新输入。");
      throw new AuthError("unauthorized");
    }
    let body = null;
    try { body = await res.json(); } catch { /* non-JSON error body */ }
    if (!res.ok || !body || body.ok === false) {
      throw new Error((body && body.error) || "请求失败（HTTP " + res.status + "）");
    }
    return body.data;
  }

  function failed(err) {
    if (!(err instanceof AuthError)) toast(err.message, true);
  }

  // ---- Login -------------------------------------------------------------
  function showLogin(message) {
    for (const node of [$("workspace"), $("logout"), document.querySelector(".tabs")]) node.hidden = true;
    $("rows").replaceChildren();
    $("file").replaceChildren();
    $("docket-count").textContent = "";
    $("login").hidden = false;
    $("login-error").textContent = message || "";
    $("token").focus();
  }

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = $("token").value.trim();
    if (!token) return;
    sessionStorage.setItem(TOKEN_KEY, token);
    $("token").value = "";
    try {
      await api("/findings?status=open");
      $("login").hidden = true;
      start();
    } catch (err) {
      if (!(err instanceof AuthError)) $("login-error").textContent = err.message;
    }
  });

  $("logout").addEventListener("click", () => {
    sessionStorage.removeItem(TOKEN_KEY);
    showLogin("");
  });

  // ---- Views -------------------------------------------------------------
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => switchView(tab.dataset.view));
  }

  function switchView(view) {
    state.view = view;
    state.selected = null;
    take("list");
    take("file");
    for (const tab of document.querySelectorAll(".tab")) {
      if (tab.dataset.view === view) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    }
    $("workspace").classList.remove("reading");
    $("file").replaceChildren();
    if (view === "docket") loadDocket();
    else loadRecords(true);
  }

  function start() {
    $("workspace").hidden = false;
    $("logout").hidden = false;
    document.querySelector(".tabs").hidden = false;
    switchView(state.view);
  }

  function skeletonRows() {
    $("rows").replaceChildren(...Array.from({ length: 6 }, () =>
      el("li", { class: "row", role: "option", "aria-busy": "true", "aria-selected": "false" }, el("span", { class: "no" }), el("div", {}, el("div", { class: "skeleton" }), el("div", { class: "skeleton", style: "width:70%" })))));
  }

  // Rows form a listbox: Enter or Space opens a row, Up and Down move between rows.
  function row(i, open, ...children) {
    return el("li", {
      class: "row", role: "option", "data-index": i, "aria-selected": String(state.selected === i), tabindex: "0",
      onclick: () => open(i),
      onkeydown: (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(i); }
        else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          const next = e.key === "ArrowDown" ? e.currentTarget.nextElementSibling : e.currentTarget.previousElementSibling;
          next?.focus();
        }
      },
    }, ...children);
  }

  function selectRow(index) {
    for (const row of $("rows").children) row.setAttribute("aria-selected", String(row.dataset.index === String(index)));
    $("workspace").classList.add("reading");
  }

  function backButton() {
    return el("button", { type: "button", class: "quiet back", text: "返回列表", onclick: () => $("workspace").classList.remove("reading") });
  }

  // ---- Docket (findings) ---------------------------------------------------
  async function loadDocket() {
    $("ledger-head").replaceChildren(el("div", { class: "meta", text: "待审的发现，按发现时间排列。逐条裁定：改正、归档或判为误报。" }));
    $("ledger-foot").replaceChildren();
    skeletonRows();
    const ticket = take("list");
    try {
      const data = await api("/findings?status=open");
      if (stale("list", ticket)) return;
      state.findings = data.items;
      $("docket-count").textContent = String(data.total);
      renderDocket();
    } catch (err) { failed(err); $("rows").replaceChildren(); }
  }

  function renderDocket() {
    const items = state.findings;
    $("ledger-foot").replaceChildren(el("span", { text: items.length + " 件待审" }));
    if (!items.length) {
      $("rows").replaceChildren(el("li", { class: "empty", role: "option", "aria-disabled": "true", "aria-selected": "false" }, el("strong", { text: "没有待审的发现" }), "维护检查每天运行一次，新的发现会出现在这里。"));
      $("file").replaceChildren(el("div", { class: "empty" }, el("strong", { text: "卷宗已清空" }), "可以到「档案」里按最久未更新排序，检查陈旧记忆。"));
      $("workspace").classList.remove("reading");
      return;
    }
    $("rows").replaceChildren(...items.map((f, i) => row(i, openFinding,
      el("span", { class: "no", text: String(i + 1).padStart(2, "0") }),
      el("span", { class: "key" }, KIND[f.kind] || f.kind),
      el("span", { class: "gist", text: f.detail || f.entity_key || "" }),
    )));
    if (window.matchMedia("(min-width: 761px)").matches) openFinding(0);
  }

  async function openFinding(index) {
    const f = state.findings[index];
    if (!f) return;
    state.selected = index;
    selectRow(index);
    $("file").replaceChildren(el("div", { class: "skeleton" }), el("div", { class: "skeleton", style: "width:60%" }));
    const ticket = take("file");
    try {
      const ids = [f.memory_id, f.other_memory_id].filter(Boolean);
      const records = await Promise.all(ids.map((id) => api("/memories/" + encodeURIComponent(id))));
      if (stale("file", ticket)) return;
      const pair = records.length > 1;
      // A correction replaces the card in place with the new version, so the person sees the
      // result they wrote; an archive re-renders the card as archived with its reason.
      const slot = (r) => {
        const holder = el("div", { class: "slot" });
        const show = (rec) => holder.replaceChildren(recordCard(rec, {
          onChanged: async (next) => {
            try { show(await api("/memories/" + encodeURIComponent(next ? next.memory_id : rec.memory_id))); }
            catch (err) { failed(err); }
          },
        }));
        show(r);
        return holder;
      };
      $("file").replaceChildren(
        backButton(),
        el("div", { class: "file-head" }, stamp(KIND[f.kind] || f.kind, "kind"), el("h2", { text: "卷宗 " + String(index + 1).padStart(2, "0") })),
        el("p", { class: "detail" }, f.detail ? [el("b", { text: "检查意见：" }), f.detail] : "同一主题下有不止一条当前版本，保留正确的一条，归档其余。"),
        el("div", { class: "records" + (pair ? " pair" : "") }, records.map(slot)),
        el("div", { class: "ruling" },
          el("span", { class: "note", text: "改正或归档任一条后，这件发现会在下一次维护时自动关闭。" }),
          el("button", { type: "button", class: "secondary", text: "判为误报", onclick: (e) => dismiss(f, e.currentTarget) }),
        ),
      );
    } catch (err) { failed(err); }
  }

  async function dismiss(finding, button) {
    button.disabled = true;
    try {
      await api("/findings/" + encodeURIComponent(finding.id) + "/dismiss", { method: "POST" });
      toast("已判为误报");
      afterRuling(finding);
    } catch (err) { failed(err); button.disabled = false; }
  }

  function afterRuling(finding) {
    const index = state.findings.indexOf(finding);
    if (state.view !== "docket" || index < 0) return;
    state.findings.splice(index, 1);
    $("docket-count").textContent = String(state.findings.length);
    renderDocket();
    if (state.findings.length) openFinding(Math.min(index, state.findings.length - 1));
  }

  // ---- Records (browse + search) -------------------------------------------
  function recordsHead() {
    const search = el("input", { type: "search", placeholder: "检索记忆（含型号、版本号）", value: state.query, "aria-label": "检索" });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { state.query = search.value.trim(); loadRecords(true); }
      if (e.key === "Escape" && search.value) { search.value = ""; state.query = ""; loadRecords(true); }
    });
    const order = el("select", { "aria-label": "排序" },
      el("option", { value: "created_at", text: "最新写入在前" }),
      el("option", { value: "valid_from", text: "最久未更新在前" }));
    order.value = state.order;
    order.addEventListener("change", () => { state.order = order.value; loadRecords(true); });
    const type = el("input", { type: "text", placeholder: "类型，如 fact", value: state.type, "aria-label": "按类型过滤", spellcheck: "false" });
    type.addEventListener("change", () => { state.type = type.value.trim(); loadRecords(true); });
    order.hidden = !!state.query;
    return [search, el("div", { class: "line" }, order, type)];
  }

  async function loadRecords(reset) {
    if (reset) { state.offset = 0; state.records = []; state.done = false; state.selected = null; skeletonRows(); }
    $("ledger-head").replaceChildren(...recordsHead());
    const ticket = take("list");
    try {
      let items;
      if (state.query) {
        const q = new URLSearchParams({ query: state.query, limit: "30" });
        if (state.type) q.set("entity_type", state.type);
        items = (await api("/memories/search?" + q)).results;
        if (stale("list", ticket)) return;
        state.done = true;
      } else {
        const q = new URLSearchParams({ limit: String(PAGE), offset: String(state.offset), order: state.order });
        if (state.type) q.set("entity_type", state.type);
        items = (await api("/memories?" + q)).results;
        if (stale("list", ticket)) return;
        state.done = items.length < PAGE;
        state.offset += items.length;
      }
      state.records = reset ? items : state.records.concat(items);
      renderRecords();
    } catch (err) { failed(err); }
  }

  function renderRecords() {
    const items = state.records;
    if (!items.length) {
      $("rows").replaceChildren(el("li", { class: "empty", role: "option", "aria-disabled": "true", "aria-selected": "false" }, el("strong", { text: state.query ? "没有匹配的记忆" : "没有当前记忆" }), state.query ? "换个说法，或直接用型号、版本号检索。" : ""));
    } else {
      $("rows").replaceChildren(...items.map((m, i) => row(i, openRecord,
        el("span", { class: "no", text: String(i + 1) }),
        el("span", { class: "key ident", text: m.entity_key }),
        el("span", { class: "gist", text: m.content }),
      )));
    }
    const label = state.query ? "最相关的 " + items.length + " 条" : "已载入 " + items.length + " 条";
    const more = !state.done && el("button", { type: "button", class: "quiet", text: "载入更多", onclick: () => loadRecords(false) });
    $("ledger-foot").replaceChildren(el("span", { text: label }), more || "");
    if (!$("file").childElementCount) {
      $("file").replaceChildren(el("div", { class: "empty" }, el("strong", { text: "选一条记忆" }), "查看全文和版本历史，必要时改正或归档。"));
    }
  }

  async function openRecord(index) {
    const m = state.records[index];
    if (!m) return;
    state.selected = index;
    selectRow(index);
    await showRecordFile(m.memory_id, index);
  }

  async function showRecordFile(memoryId, index) {
    $("file").replaceChildren(el("div", { class: "skeleton" }), el("div", { class: "skeleton", style: "width:60%" }));
    const ticket = take("file");
    try {
      const r = await api("/memories/" + encodeURIComponent(memoryId));
      if (stale("file", ticket)) return;
      $("file").replaceChildren(
        backButton(),
        el("div", { class: "records" }, recordCard(r, {
          onChanged: (next) => {
            if (next) { state.records[index] = { ...state.records[index], memory_id: next.memory_id, content: next.content }; renderRecords(); showRecordFile(next.memory_id, index); }
            else { state.records.splice(index, 1); state.selected = null; $("file").replaceChildren(); renderRecords(); $("workspace").classList.remove("reading"); }
          },
        })),
        historyList(r),
      );
    } catch (err) { failed(err); }
  }

  function historyList(r) {
    return el("section", { class: "history" },
      el("h3", { text: "版本历史（" + r.versions.length + "）" }),
      el("ol", { class: "versions" }, r.versions.map((v) => el("li", { class: "version" + (v.is_current ? " is-current" : "") },
        el("div", { class: "when" },
          el("span", { text: when(v.created_at) }),
          el("span", {}, v.is_current ? stamp("当前", "current") : stamp("已失效", "archived"), " ", stamp(MUTATION[v.mutation_type] || v.mutation_type, v.mutation_type === "correction" ? "correction" : ""), v.conflict ? [" ", stamp("冲突合并", "conflict")] : null),
        ),
        el("div", {},
          el("div", { class: "text", text: v.content }),
          v.archived_reason ? el("div", { class: "why", text: "归档原因：" + v.archived_reason }) : null,
        ),
      ))),
    );
  }

  // ---- One record: full text, stamps, correct / archive ---------------------
  function recordCard(r, { onChanged }) {
    const card = el("section", { class: "record" });
    const actions = el("div", { class: "record-actions" });
    const head = el("div", { class: "record-head" },
      el("span", { class: "key", text: r.entity_key }),
      r.is_current ? stamp("当前", "current") : stamp("已失效", "archived"),
      r.mutation_type === "correction" ? stamp("改正", "correction") : null,
      r.conflict ? stamp("冲突合并", "conflict") : null,
    );
    const meta = el("div", { class: "record-meta" },
      el("span", { text: "写入 " + when(r.created_at) }),
      el("span", { text: "生效 " + when(r.valid_from) }),
      el("span", { text: "版本 " + r.versions.length }),
    );
    const body = el("div", { class: "record-body", text: r.content });
    card.append(head, meta, body);
    if (r.archived_reason) card.append(el("div", { class: "reason", text: "归档原因：" + r.archived_reason }));
    if (!r.is_current) return card;

    const reset = () => { card.querySelector(".editor")?.remove(); actions.hidden = false; };

    actions.append(
      el("button", {
        type: "button", class: "secondary", text: "改正", onclick: () => {
          actions.hidden = true;
          const area = el("textarea", { "aria-label": "改正后的完整内容" });
          area.value = r.content;
          const save = el("button", { type: "submit", class: "primary", text: "保存为新版本" });
          const form = el("form", { class: "editor" },
            el("p", { class: "hint", text: "保存后原文变为历史版本。这里写的内容原样替换，不经过自动合并。" }),
            area,
            el("div", { class: "actions" }, el("button", { type: "button", class: "quiet", text: "取消", onclick: reset }), save),
          );
          form.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (!area.value.trim()) { toast("内容不能为空", true); return; }
            save.disabled = true;
            try {
              const next = await api("/memories/" + encodeURIComponent(r.memory_id) + "/correct", { method: "POST", body: JSON.stringify({ content: area.value }) });
              toast("已保存改正版本");
              onChanged(next);
            } catch (err) { failed(err); save.disabled = false; }
          });
          card.append(form);
          area.focus();
        },
      }),
      el("button", {
        type: "button", class: "quiet danger-text", text: "归档", onclick: () => {
          actions.hidden = true;
          const reason = el("input", { type: "text", placeholder: "归档原因，例如：内容已过时", "aria-label": "归档原因", required: true });
          const confirm = el("button", { type: "submit", class: "primary", text: "确认归档" });
          const form = el("form", { class: "editor" },
            el("p", { class: "hint", text: "归档后这条记忆不再被检索到，版本历史保留。" }),
            reason,
            el("div", { class: "actions" }, el("button", { type: "button", class: "quiet", text: "取消", onclick: reset }), confirm),
          );
          form.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (!reason.value.trim()) { toast("请填写归档原因", true); reason.focus(); return; }
            confirm.disabled = true;
            try {
              await api("/memories/" + encodeURIComponent(r.memory_id) + "/archive", { method: "POST", body: JSON.stringify({ reason: reason.value.trim() }) });
              toast("已归档");
              onChanged(null);
            } catch (err) { failed(err); confirm.disabled = false; }
          });
          card.append(form);
          reason.focus();
        },
      }),
    );
    card.append(actions);
    return card;
  }

  // ---- Boot ------------------------------------------------------------------
  if (sessionStorage.getItem(TOKEN_KEY)) start();
  else showLogin("");
})();
