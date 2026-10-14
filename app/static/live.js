/* 라이브 실험실: 서버에서 받은 단계(trace)를 하나씩 펼쳐 보여 준다. */
(function live() {
  const {$, $$, esc, el, svgEl, api, stream, drawGraph} = GR;

  const MODES = [
    {id: "ingest", label: "문서 처리", sub: "PDF · 청크 · 임베딩", visual: "chart", noQuestion: true},
    {id: "vector", label: "벡터 RAG", sub: "청크 · 임베딩 · 유사도", visual: "scatter"},
    {id: "graph", label: "그래프 Local", sub: "엔티티 · 경로 · PPR", visual: "kg"},
    {id: "global", label: "그래프 Global", sub: "커뮤니티 · Map-Reduce", visual: "kg"},
    {id: "compare", label: "나란히 비교", sub: "벡터 · 그래프 · 하이브리드", visual: "kg", noSteps: true},
    {id: "extract", label: "그래프 구축", sub: "LLM 추출 · 엔티티 해소", visual: "kg", noQuestion: true},
    {id: "agent", label: "에이전트", sub: "도구로 그래프 탐색", visual: "kg"},
    {id: "temporal", label: "시간 메모리", sub: "유효 기간 · 무효화", noSteps: true, noVisual: true, noQuestion: true},
  ];
  const TYPE_GROUPS = [
    ["주체(기업·사람)", "var(--t2)", ["FirmGroup", "Actor", "Organization", "Economy", "Person"]],
    ["지표·성과", "var(--t1)", ["Indicator", "Outcome"]],
    ["문제·위험", "var(--t4)", ["Problem", "Risk", "Trend", "Phenomenon", "Event"]],
    ["정책", "var(--t3)", ["Policy"]],
    ["자금·시장", "var(--t6)", ["Finance", "Market"]],
    ["연구·개념", "var(--t5)", ["ResearchType", "Concept", "Technology", "Product"]],
    ["데이터·방법", "var(--t7)", ["Dataset", "Method", "Location"]],
  ];
  const TYPE_COLOR = Object.fromEntries(TYPE_GROUPS.flatMap(([, c, ts]) => ts.map(t => [t, c])));
  /* 파이프라인 지도: 현재 단계가 전체 흐름의 어디인지 표시 */
  const STAGES = ["PDF", "정제", "섹션", "청크", "임베딩", "그래프·요약", "저장", "질문", "검색", "컨텍스트", "LLM 답변"];
  const STAGE_OF = {
    ingest: {load: "PDF", clean: "정제", sections: "섹션", chunk: "청크", embed: "임베딩", store: "저장"},
    vector: {chunk: "저장", embed: "질문", similarity: "검색", topk: "검색", prompt: "컨텍스트", answer: "LLM 답변"},
    graph: {kg: "그래프·요약", link: "질문", path: "검색", expand: "검색", ppr: "검색", rank: "검색", context: "컨텍스트", prompt: "컨텍스트", answer: "LLM 답변"},
    global: {community: "그래프·요약", reports: "그래프·요약", map: "검색", reduce: "컨텍스트", answer: "LLM 답변"},
    extract: {input: "섹션", prompt: "그래프·요약", extract: "그래프·요약", resolve: "그래프·요약"},
  };
  const DOC_COLORS = ["var(--t1)", "var(--t2)", "var(--t3)", "var(--t4)", "var(--t5)", "var(--t6)", "var(--t7)"];
  const docColor = id => DOC_COLORS[(parseInt(String(id).replace(/\D/g, ""), 10) || 0) % DOC_COLORS.length];
  const COMM = ["var(--t1)", "var(--t2)", "var(--t3)", "var(--t4)", "var(--t5)", "var(--t6)", "var(--t7)"];
  const S = {mode: "graph", trace: null, idx: 0, revealed: 0, events: [], kgView: null, busy: false};
  let CFG = null;

  /* ── 초기화 ─────────────────────────────────────────────── */
  async function init() {
    try { CFG = GR.config = await api("/api/config"); }
    catch (e) { $("#status").innerHTML = `<span class="off">서버 연결 실패</span>`; return; }
    renderStatus();
    $("#embSelect").innerHTML = CFG.embeddings.map(o => `<option value="${esc(o.id)}" ${o.id === CFG.embedding ? "selected" : ""}>${esc(o.label)}</option>`).join("");
    $("#modes").innerHTML = MODES.map(m => `<button type="button" role="tab" data-mode="${m.id}" aria-selected="false">${esc(m.label)}<small>${esc(m.sub)}</small></button>`).join("");
    setMode("ingest", false);
    $("#qinput").value = CFG.questions.find(q => q.id === "q3").question;
  }
  function renderStatus() {
    $("#status").innerHTML = `<span class="${CFG.llm ? "on" : "off"}">LLM: ${esc(CFG.llm || "없음 (검색만)")}</span><span>임베딩: ${esc(CFG.embedding)}</span>`;
  }

  /* ── 화면 전환 (강의 ↔ 실험실) ───────────────────────────── */
  function showView(lab) {
    GR.exitPresent?.();
    $("#lectureView").hidden = lab; $("#labView").hidden = !lab;
    document.body.classList.toggle("in-lab", lab);
    $("#tabLecture").setAttribute("aria-selected", !lab); $("#tabLab").setAttribute("aria-selected", lab);
    window.scrollTo(0, 0);
  }
  $("#tabLecture").addEventListener("click", () => showView(false));
  $("#tabLab").addEventListener("click", () => showView(true));
  document.addEventListener("click", e => {
    const b = e.target.closest(".live"); if (!b) return;
    e.preventDefault();
    showView(true); setMode(b.dataset.live, false);
    const q = CFG?.questions.find(x => x.id === b.dataset.q);
    if (q) $("#qinput").value = q.question;
    if (b.dataset.live !== "temporal") run();
  });

  /* ── 모드 ───────────────────────────────────────────────── */
  function setMode(id, autorun = false) {
    S.mode = id; S.trace = null; S.events = [];
    const m = MODES.find(x => x.id === id);
    $$("#modes button").forEach(b => b.setAttribute("aria-selected", b.dataset.mode === id));
    const main = $("#labMain");
    main.classList.toggle("no-steps", !!m.noSteps); main.classList.toggle("no-visual", !!m.noVisual);
    $("#qinput").parentElement.style.display = m.noQuestion ? "none" : "";
    $("#stepperTitle").textContent = id === "agent" ? "에이전트 행동" : "처리 단계";
    $("#steps").innerHTML = "";
    renderSamples();
    if (m.visual === "kg") drawKG(); else if (m.visual === "scatter") clearVisual("임베딩 공간", "질문을 실행하면 청크 벡터가 나타납니다");
    else if (m.visual === "chart") clearVisual("시각화", "실행하면 단계별 차트가 나타납니다");
    $("#nodeInfo").hidden = true;
    renderEmpty();
    if (id === "temporal") renderTemporal();
    if (autorun) run();
  }
  $("#modes").addEventListener("click", e => { const b = e.target.closest("[data-mode]"); if (b) setMode(b.dataset.mode); });

  function renderSamples() {
    if (S.mode === "ingest") {
      $("#samples").innerHTML = `<span style="font-size:.8rem;color:var(--muted);align-self:center">청크를 살펴볼 문서:</span>` +
        CFG.docs.map(d => `<button type="button" data-ingest="${d.id}"><b>${d.id}</b>${esc(d.title)}</button>`).join("");
      return;
    }
    if (S.mode === "extract") {
      $("#samples").innerHTML = `<span style="font-size:.8rem;color:var(--muted);align-self:center">문서 선택:</span>` +
        CFG.docs.map(d => `<button type="button" data-extract="${d.id}"><b>${d.id}</b>${esc(d.title)}</button>`).join("");
      return;
    }
    if (S.mode === "temporal") { $("#samples").innerHTML = ""; return; }
    const T = {"single-hop": "단일", "multi-hop": "멀티홉", "global": "전역"};
    const qs = CFG.questions.filter(q => S.mode === "global" ? true : q.type !== "global" || S.mode === "agent");
    $("#samples").innerHTML = qs.map(q => `<button type="button" data-sample="${q.id}"><b>${q.id}·${T[q.type]}</b>${esc(q.question)}</button>`).join("");
  }
  $("#samples").addEventListener("click", e => {
    const s = e.target.closest("[data-sample]"); if (s) { $("#qinput").value = CFG.questions.find(q => q.id === s.dataset.sample).question; run(); return; }
    const x = e.target.closest("[data-extract]"); if (x) runExtract(x.dataset.extract, null);
    const g = e.target.closest("[data-ingest]"); if (g) { S.ingest.doc_id = g.dataset.ingest; runIngest(3); }
  });
  $("#qform").addEventListener("submit", e => { e.preventDefault(); run(); });
  $("#embSelect").addEventListener("change", async e => {
    const v = e.target.value; e.target.disabled = true;
    $("#status").innerHTML += `<span>재인덱싱 중…</span>`;
    try { const r = await api("/api/config/embedding", {embedding: v}); CFG.embedding = r.embedding; renderStatus(); if (S.trace && S.mode === "vector") run(); }
    catch (err) { alert(err.message); }
    e.target.disabled = false;
  });

  function renderEmpty() {
    const hint = {
      ingest: "보고서 PDF가 검색 가능한 벡터 인덱스가 되기까지를 봅니다: <b>PDF 로드 → 정제 → 섹션 분할 → 청크 분할 → 임베딩 → 벡터 저장소</b>. 위에서 문서를 고르면 시작합니다.",
      vector: "질문을 실행하면 <b>청크 분할 → 임베딩 → 유사도 → Top-k → 프롬프트 → LLM</b> 순서로 단계가 펼쳐집니다.",
      graph: "질문을 실행하면 <b>엔티티 연결 → 경로 → 이웃 확장 → PPR → 문서 순위 → 컨텍스트 → LLM</b> 순서로 단계가 펼쳐집니다.",
      global: "전역 질문을 실행하면 <b>커뮤니티 → 리포트 → Map → Reduce → LLM</b> 순서로 단계가 펼쳐집니다.",
      compare: "같은 질문에 대해 세 검색기의 결과와 Recall을 비교하고, 두 방식의 LLM 답변을 동시에 생성합니다.",
      extract: "위에서 문서를 고르거나 아래에 글을 붙여 넣으면 LLM이 엔티티와 관계를 뽑고 기존 그래프와 병합하는 과정을 봅니다.",
      agent: "LLM 에이전트가 search_entities / get_neighbors / find_path / read_document 도구를 골라 쓰는 과정을 실시간으로 봅니다.",
    }[S.mode];
    if (!hint) return;
    let html = `<div class="empty"><b>${esc(MODES.find(m => m.id === S.mode).label)}</b><p>${hint}</p><p style="font-size:.84rem">발표 팁: <kbd>→</kbd> <kbd>←</kbd> 로 단계 이동, 상단 <b>가⁺</b>로 글자 크게</p></div>`;
    if (S.mode === "ingest") html += `<button class="btn primary" type="button" id="ingestRun" style="justify-self:center">문서 처리 시작 ▶</button>`;
    if (S.mode === "extract") html += `<label style="display:grid;gap:6px;font-size:.86rem">직접 입력 (선택)<textarea id="extractText" rows="5" style="font:inherit;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink)" placeholder="예) 정부는 벤처캐피탈 접근성을 높이기 위해 M&A 시장 규제를 완화하고, 민간 벤처캐피탈의 모태펀드 출자 비중을 늘리기로 했다."></textarea></label><button class="btn primary" type="button" id="extractRun" style="justify-self:start">입력한 글로 추출</button>`;
    if (S.mode === "agent" && !CFG.llm) html += `<p class="note warn">에이전트는 LLM이 필요합니다. <code>.env</code>에 <code>LLM_MODEL</code>과 API 키를 넣고 서버를 다시 시작하세요.</p>`;
    $("#stage").innerHTML = html;
    $("#extractRun")?.addEventListener("click", () => runExtract(null, $("#extractText").value));
    $("#ingestRun")?.addEventListener("click", () => runIngest(0));
  }

  /* ── 실행 ───────────────────────────────────────────────── */
  async function run() {
    const q = $("#qinput").value.trim();
    const k = +$("#kSelect").value;
    if (S.busy) return;
    if (S.mode === "extract") return runExtract("doc14", null);
    if (S.mode === "ingest") return runIngest(0);
    if (S.mode === "temporal") return;
    if (!q) { $("#qinput").focus(); return; }
    S.busy = true; $("#runBtn").disabled = true;
    $("#stage").innerHTML = `<div class="empty"><b>실행 중…</b><p>서버가 lab/ 의 실습 코드를 실행하고 있습니다.</p></div>`;
    try {
      if (S.mode === "compare") { renderCompare(await api("/api/compare", {mode: "compare", question: q, k})); }
      else if (S.mode === "agent") { await runAgent(q); }
      else { loadTrace(await api("/api/trace", {mode: S.mode, question: q, k})); }
    } catch (e) { $("#stage").innerHTML = `<div class="empty"><b>오류</b><p>${esc(e.message)}</p></div>`; }
    S.busy = false; $("#runBtn").disabled = false;
  }
  async function runExtract(docId, text) {
    if (S.busy) return;
    S.busy = true;
    $("#stage").innerHTML = `<div class="empty"><b>${CFG.llm ? "LLM이 추출하는 중…" : "실행 중…"}</b></div>`;
    try { loadTrace(await api("/api/extract", {doc_id: docId || "doc14", text})); }
    catch (e) { $("#stage").innerHTML = `<div class="empty"><b>오류</b><p>${esc(e.message)}</p></div>`; }
    S.busy = false;
  }

  S.ingest = {page: 3, doc_id: "doc09", chunk_size: 500, overlap: 50};
  async function runIngest(startStep = 0) {
    if (S.busy) return;
    S.busy = true;
    $("#stage").innerHTML = `<div class="empty"><b>PDF를 읽는 중…</b><p>PyPDFLoader → 정제 → 섹션 → 청크 → 임베딩</p></div>`;
    try {
      const tr = await api("/api/ingest", S.ingest);
      const keep = S.trace?.mode === "ingest" ? S.revealed : 0;
      loadTrace(tr, startStep);
      S.revealed = Math.max(S.revealed, keep, startStep); renderStepper();
    } catch (e) { $("#stage").innerHTML = `<div class="empty"><b>오류</b><p>${esc(e.message)}</p></div>`; }
    S.busy = false;
  }

  function loadTrace(tr, start = 0) {
    S.trace = tr; S.idx = start;
    S.revealed = $("#revealMode").checked ? 0 : tr.steps.length - 1;
    if (MODES.find(m => m.id === S.mode).visual === "kg") drawKG();
    renderStepper(); showStep(start);
  }

  /* ── 단계 목록 ───────────────────────────────────────────── */
  function renderStepper() {
    const steps = S.trace.steps;
    let html = "", lastPh = null;
    steps.forEach((s, i) => {
      if (s.phase !== lastPh) { html += `<li class="ph">${esc(s.phase)}</li>`; lastPh = s.phase; }
      const locked = i > S.revealed;
      html += `<li><button type="button" data-step="${i}" class="${locked ? "locked" : ""} ${i < S.idx ? "done" : ""}" ${i === S.idx ? 'aria-current="step"' : ""} ${locked ? "disabled" : ""}>
        <span class="no">${i + 1}</span><span>${esc(s.title)}</span><span class="ms">${locked ? "" : fmtMs(s.ms)}</span></button></li>`;
    });
    $("#steps").innerHTML = html;
    $("#stepPrev").disabled = S.idx === 0;
    $("#stepNext").disabled = S.idx >= steps.length - 1;
  }
  const fmtMs = ms => ms == null ? "" : ms < 1 ? "<1ms" : ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
  $("#steps").addEventListener("click", e => { const b = e.target.closest("[data-step]"); if (b && S.trace) showStep(+b.dataset.step); });
  const next = () => { if (S.trace && S.idx < S.trace.steps.length - 1) { S.revealed = Math.max(S.revealed, S.idx + 1); showStep(S.idx + 1); } };
  const prev = () => { if (S.trace && S.idx > 0) showStep(S.idx - 1); };
  $("#stepNext").addEventListener("click", next);
  $("#stepPrev").addEventListener("click", prev);
  $("#revealMode").addEventListener("change", e => { if (S.trace) { S.revealed = e.target.checked ? S.idx : S.trace.steps.length - 1; renderStepper(); } });
  document.addEventListener("keydown", e => {
    if (!document.body.classList.contains("in-lab") || !$("#drawer").hidden || e.repeat) return;
    if (/input|textarea|select/i.test(e.target.tagName)) return;
    if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); prev(); }
  });

  function showStep(i) {
    S.idx = i; S.revealed = Math.max(S.revealed, i);
    renderStepper();
    const s = S.trace.steps[i];
    const code = s.code ? `<div class="coderow"><span style="color:var(--muted)">이 단계의 코드</span><button type="button" class="btn" data-code="${esc(s.code.file)}#${esc(s.code.symbol)}">${esc(s.code.file)} · ${esc(s.code.symbol)}</button></div>` : "";
    const cur = STAGE_OF[S.mode]?.[s.id];
    const used = new Set(Object.values(STAGE_OF[S.mode] || {}));
    const map = cur ? `<div class="pipemap" aria-label="전체 흐름에서 현재 위치">${STAGES.map((st, j) => `${j === 7 ? '<span class="pm-sep">질문 시점 →</span>' : ""}<span class="pm ${st === cur ? "on" : used.has(st) ? "used" : ""}">${st}</span>`).join("")}</div>` : "";
    $("#stage").innerHTML = `${map}<div class="stage-head"><span class="ph">${esc(s.phase)} · 단계 ${i + 1}/${S.trace.steps.length} · ${fmtMs(s.ms)}</span><h2>${esc(s.title)}</h2></div>
      <p class="explain">${esc(s.explain)}</p>${code}<div id="view"></div>`;
    (VIEWS[s.view.type] || VIEWS.json)(s.view, $("#view"), s);
    updateVisual(s, i);
  }

  /* ── 단계별 화면 ─────────────────────────────────────────── */
  const docChip = (d, gold, sel) => `<button type="button" class="doc ${gold?.includes(d) ? "hit" : ""} ${sel === false ? "miss" : ""}" data-doc="${d}">${d}</button>`;
  /* 정답 근거는 '사실별 그룹'(그룹 안 문서 중 하나만 찾으면 인정)으로 표시 */
  const goldBox = (gold, got) => {
    if (!gold) return `<div class="gold"><span style="color:var(--muted)">직접 입력한 질문이라 정답 근거 정보가 없습니다.</span></div>`;
    const ok = gold.groups.map(g => g.some(d => got.includes(d)));
    const n = ok.filter(Boolean).length;
    return `<div class="gold"><b>필요한 근거</b> ${gold.groups.map((g, i) => `<span class="grp ${ok[i] ? "ok" : "no"}">사실 ${i + 1}: ${g.map(d => docChip(d, got, got.includes(d) ? undefined : false)).join('<span class="or">또는</span>')}</span>`).join("")}
      <span class="badge ${n === ok.length ? "ok" : "bad"}">${n}/${ok.length} 충족</span></div>`;
  };
  const bar = (v, max, color = "var(--vec)") => `<span class="sbar"><i style="width:${Math.max(2, 90 * v / (max || 1))}px;background:${color}"></i><span>${v.toFixed(3)}</span></span>`;

  const VIEWS = {
    chunks(v, box) {
      box.innerHTML = `<div class="chips"><span class="chip">임베딩 <b>${esc(v.embedding)}</b></span><span class="chip">벡터 차원 <b>${v.dim}</b></span><span class="chip">청크 크기 <b>${v.chunk_size}자</b></span><span class="chip">청크 수 <b>${v.chunks.length}</b></span></div>
      <div class="scroll" style="margin-top:10px"><table class="t"><thead><tr><th>#</th><th>문서</th><th class="num">글자 수</th><th>내용</th></tr></thead><tbody>
      ${v.chunks.map((c, i) => `<tr><td>${i + 1}</td><td>${docChip(c.doc_id)}</td><td class="num">${c.len}</td><td><span class="preview">${esc(c.text.replace(/\s+/g, " "))}</span></td></tr>`).join("")}</tbody></table></div>`;
    },
    vector(v, box) {
      const W = 640, H = 90, n = v.head.length, max = Math.max(...v.head.map(Math.abs)) || 1, bw = W / n;
      const bars = v.head.map((x, i) => { const h = Math.abs(x) / max * (H / 2 - 6); return `<rect x="${i * bw + 1}" y="${x >= 0 ? H / 2 - h : H / 2}" width="${bw - 2}" height="${Math.max(h, .5)}" fill="${x >= 0 ? "var(--vec)" : "var(--hyb)"}"/>`; }).join("");
      box.innerHTML = `<p class="qmark">"${esc($("#qinput").value)}"</p><p style="color:var(--muted)">↓ 임베딩 모델</p>
        <svg class="vecstrip" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="질문 벡터 앞부분"><line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" class="axis"/>${bars}</svg>
        <div class="chips" style="margin-top:8px"><span class="chip">차원 <b>${v.dim}</b></span><span class="chip">L2 노름 <b>${v.norm}</b></span><span class="chip">앞 ${n}개 값만 표시</span></div>
        <pre class="box" style="margin-top:8px">[${v.head.slice(0, 12).join(", ")}, … ]</pre>`;
    },
    scores(v, box) {
      const max = v.chunks[0]?.score || 1, seen = new Set(); let cut = -1;
      v.chunks.forEach((c, i) => { if (cut < 0) { seen.add(c.doc_id); if (seen.size === v.k) cut = i; } });
      box.innerHTML = `<p style="font-size:.88rem">청크 ${v.chunks.length}개 전체의 점수입니다. 점선 위가 선택된 범위(Top-${v.k} 문서)입니다.</p>
      <div class="scroll"><table class="t"><thead><tr><th>순위</th><th>문서</th><th>코사인 유사도</th><th>청크 내용</th></tr></thead><tbody>
      ${v.chunks.map((c, i) => `<tr class="${i <= cut ? "sel" : ""} ${i === cut ? "cut" : ""}"><td>${i + 1}</td><td>${docChip(c.doc_id)}</td><td>${bar(c.score, max)}</td><td><span class="preview">${esc(c.text.replace(/\s+/g, " "))}</span></td></tr>`).join("")}</tbody></table></div>`;
    },
    docs(v, box) {
      box.innerHTML = goldBox(v.gold, v.doc_ids) + `<p style="font-size:.86rem;color:var(--muted)">선택된 문서: ${v.doc_ids.map(d => docChip(d, v.gold?.docs)).join(" ")} · 컨텍스트로 들어갈 청크 ${v.chunks.length}개</p>
        <div class="doccards">${v.chunks.map((c, i) =>
        `<div class="doccard" style="border-left:4px solid ${docColor(c.doc_id)}"><span>청크 ${i + 1} ${docChip(c.doc_id, v.gold?.docs)} <span class="chip">유사도 ${c.score.toFixed(3)}</span> <span class="chip">${c.text.length}자</span></span><pre>${esc(c.text)}</pre></div>`).join("")}</div>`;
    },
    prompt(v, box) {
      if (v.segments) { promptView(v, box); return; }
      box.innerHTML = `<div class="chips"><span class="chip">길이 <b>${(v.chars ?? v.text.length).toLocaleString()}자</b></span></div><pre class="box" style="margin-top:8px">${esc(v.text)}</pre>` +
        (v.schema ? `<details class="more" style="margin-top:8px"><summary>LLM에 전달되는 출력 JSON 스키마 (Pydantic → JSON Schema)</summary><pre class="box">${esc(JSON.stringify(v.schema, null, 2))}</pre></details>` : "");
    },
    llm(v, box) { llmBox(box, v.messages, "answer"); },
    kgstats(v, box) {
      box.innerHTML = `<div class="cmp"><div class="col"><span style="color:var(--muted)">노드</span><span class="big">${v.nodes}</span></div><div class="col"><span style="color:var(--muted)">엣지(관계)</span><span class="big">${v.edges}</span></div></div>
      <div class="chips" style="margin-top:10px">${Object.entries(v.types).map(([t, n]) => `<span class="chip">${esc(t)} <b>${n}</b></span>`).join("")}</div>
      <p style="margin-top:10px"><button type="button" class="filelink" data-file="data/kg.json">data/kg.json 보기</button> · <button type="button" class="filelink live" data-live="extract">LLM 추출 과정 보기</button></p>`;
    },
    linking(v, box) {
      const q = v.question; let html = "", pos = 0;
      [...v.links].sort((a, b) => a.start - b.start).forEach(l => { if (l.start >= pos) { html += esc(q.slice(pos, l.start)) + `<mark>${esc(q.slice(l.start, l.end))}</mark>`; pos = l.end; } });
      html += esc(q.slice(pos));
      box.innerHTML = `<p class="qmark">${html}</p>` + (v.links.length
        ? `<table class="t" style="margin-top:8px"><thead><tr><th>그래프 노드</th><th>질문 속 표현</th><th>타입</th></tr></thead><tbody>${v.links.map(l => `<tr><td>${esc(l.node)}</td><td><code>${esc(l.matched)}</code></td><td>${esc(CFG.kg.nodes.find(n => n.id === l.node)?.type)}</td></tr>`).join("")}</tbody></table>`
        : `<p class="note warn">질문에서 그래프 엔티티를 하나도 찾지 못했습니다. 그래프 검색은 여기서 멈춥니다. Entity Linking이 GraphRAG의 첫 관문인 이유입니다.</p>`);
    },
    paths(v, box) {
      if (!v.paths.length) { box.innerHTML = `<p class="note warn">시드 엔티티가 ${v.seeds.length}개라 경로를 찾을 쌍이 없습니다.</p>`; return; }
      const rel = (a, b) => { const f = v.edges.find(e => e.s === a && e.t === b); if (f) return `—${f.type}→`; const r = v.edges.find(e => e.s === b && e.t === a); return r ? `←${r.type}—` : "—"; };
      box.innerHTML = `<div style="display:grid;gap:8px">${v.paths.map(p => `<div class="pathrow">${p.map((n, i) => (i ? `<span class="rl">${esc(rel(p[i - 1], n))}</span>` : "") + `<span class="nd ${v.seeds.includes(n) ? "seed" : ""}">${esc(n)}</span>`).join("")}<span class="badge">${p.length - 1}-hop</span></div>`).join("")}</div>
        <p style="margin-top:10px;font-size:.88rem">경로 위 관계의 출처 문서: ${[...new Set(v.edges.map(e => e.doc))].map(d => docChip(d)).join(" ")}</p>
        <p style="font-size:.84rem;color:var(--muted)">질문에 없던 중간 노드: ${[...new Set(v.paths.flat())].filter(n => !v.seeds.includes(n)).map(esc).join(", ") || "없음"}</p>`;
    },
    expand(v, box) {
      const hop0 = Object.keys(v.hops).filter(n => v.hops[n] === 0), hop1 = Object.keys(v.hops).filter(n => v.hops[n] === 1);
      const extra = v.sub.filter(n => !(n in v.hops));
      const col = (t, ns) => `<div><h4>${t} · ${ns.length}</h4>${ns.map(n => `<span>${esc(n)}</span>`).join("") || "<span style='color:var(--muted)'>없음</span>"}</div>`;
      box.innerHTML = `<div class="hopcols">${col("시드 (0-hop)", hop0)}${col("1-hop 이웃", hop1)}${col("경로로 추가", extra)}</div><p style="margin-top:10px;font-size:.88rem">서브그래프 노드 <b>${v.sub.length}</b>개 / 전체 ${CFG.kg.nodes.length}개</p>`;
    },
    ppr(v, box) {
      const max = v.top[0]?.score || 1, seeds = S.trace.steps.find(s => s.id === "link")?.graph?.seeds || [];
      box.innerHTML = `<table class="t"><thead><tr><th>노드</th><th>PPR 점수</th></tr></thead><tbody>${v.top.map(r => `<tr><td>${esc(r.node)} ${seeds.includes(r.node) ? '<span class="badge">시드</span>' : ""}</td><td>${bar(r.score, max, "var(--accent)")}</td></tr>`).join("")}</tbody></table>
      <p style="margin-top:8px;font-size:.84rem;color:var(--muted)">alpha=0.85: 85% 확률로 이웃으로 이동, 15% 확률로 시드로 순간이동하는 무작위 걷기.</p>`;
    },
    docscores(v, box) {
      const max = Math.max(...v.rows.map(r => r.score), 0.0001);
      box.innerHTML = goldBox(v.gold, v.selected) + `<table class="t" style="margin-top:10px"><thead><tr><th>순위</th><th>문서</th><th>근거</th><th>PPR 점수 합</th><th class="num">관계 수</th></tr></thead><tbody>
      ${v.rows.map((r, i) => `<tr class="${v.selected.includes(r.doc_id) ? "sel" : ""} ${i === v.selected.length - 1 ? "cut" : ""}"><td>${i + 1}</td><td>${docChip(r.doc_id, v.gold?.docs)}</td><td><span class="badge ${r.via === "path" ? "path" : ""}">${r.via === "path" ? "경로 위 관계" : "주변 서브그래프"}</span></td><td>${r.via === "path" ? '<span style="color:var(--muted)">경로 우선</span>' : bar(r.score, max, "var(--accent)")}</td><td class="num">${r.edges.length}</td></tr>`).join("")}</tbody></table>`;
    },
    context(v, box) {
      box.innerHTML = `<h3>관계 트리플 (${v.triples.length})</h3><pre class="box">${esc(v.triples.join("\n")) || "(없음)"}</pre>
        <h3 style="margin-top:10px">원문 (${Object.keys(v.docs).length})</h3><div class="doccards">${Object.entries(v.docs).map(([d, t]) => `<details class="doccard"><summary>${docChip(d)} ${esc(t.split("\n")[0].replace(/^#\s*/, ""))}</summary><pre>${esc(t)}</pre></details>`).join("")}</div>`;
    },
    communities(v, box) {
      box.innerHTML = `<div style="display:grid;gap:8px">${v.communities.map((c, i) => `<div class="doccard"><b><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${COMM[i % COMM.length]}"></i> 커뮤니티 C${i} · ${c.length}개 노드</b><div class="chips">${c.map(n => `<span class="chip">${esc(n)}</span>`).join("")}</div></div>`).join("")}</div>`;
    },
    reports(v, box) {
      box.innerHTML = `<div style="display:grid;gap:8px">${v.reports.map(r => `<div class="doccard"><b><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${COMM[r.id % COMM.length]}"></i> C${r.id} · ${esc(r.title)} <span class="badge">중요도 ${r.rating}</span></b><pre>${esc(r.summary)}</pre></div>`).join("")}</div>
        <details class="more" style="margin-top:10px"><summary>리포트를 만들 때 LLM에 넣는 입력 예시 (C0)</summary><pre class="box">${esc(v.input_example)}</pre></details>
        <p style="font-size:.84rem"><button type="button" class="filelink" data-file="data/community_summaries.json">community_summaries.json</button></p>`;
    },
    map(v, box) {
      box.innerHTML = `<table class="t"><thead><tr><th>커뮤니티</th><th>관련도</th><th>부분 답변</th></tr></thead><tbody>${v.rows.map(r => `<tr class="${r.score > 0 ? "sel" : ""}"><td>C${r.id} ${esc(r.title)}</td><td>${bar(r.score, 100, COMM[r.id % COMM.length])}</td><td style="font-size:.82rem">${esc(r.answer)}</td></tr>`).join("")}</tbody></table>
        <p style="font-size:.82rem;color:var(--muted);margin-top:6px">점수 계산: ${esc(v.rows[0]?.by || "")}</p>`;
    },
    text(v, box) { box.innerHTML = `<div class="chips"><span class="chip">${esc(v.label)}</span></div><pre class="box" style="margin-top:8px">${esc(v.text)}</pre>`; },
    extraction(v, box) {
      box.innerHTML = `<div class="chips"><span class="chip">출처 <b>${esc(v.by)}</b></span><span class="chip">엔티티 <b>${v.entities.length}</b></span><span class="chip">관계 <b>${v.relations.length}</b></span></div>
      <h3 style="margin-top:10px">엔티티</h3><table class="t"><thead><tr><th>이름</th><th>타입</th><th>설명</th></tr></thead><tbody>${v.entities.map(e => `<tr><td>${esc(e.name)}</td><td>${esc(e.type)}</td><td style="font-size:.84rem">${esc(e.description)}</td></tr>`).join("")}</tbody></table>
      <h3 style="margin-top:10px">관계 (트리플)</h3><table class="t"><thead><tr><th>주어</th><th>관계</th><th>목적어</th></tr></thead><tbody>${v.relations.map(r => `<tr><td>${esc(r.source)}</td><td><code>${esc(r.type)}</code></td><td>${esc(r.target)}</td></tr>`).join("")}</tbody></table>`;
    },
    resolution(v, box) {
      box.innerHTML = `<table class="t"><thead><tr><th>추출된 이름</th><th>정규화 키</th><th>결과</th></tr></thead><tbody>${v.rows.map(r => `<tr><td>${esc(r.name)}</td><td><code>${esc(r.key)}</code></td><td>${r.match ? `<span class="badge ok">기존 노드와 병합</span> ${esc(r.match)}` : `<span class="badge new">새 노드</span>`}</td></tr>`).join("")}</tbody></table>` +
        (v.dropped.length ? `<p class="note warn" style="margin-top:10px">엔티티 목록에 없는 이름을 가리켜 버린 관계: ${v.dropped.map(esc).join(", ")}</p>` : `<p style="margin-top:10px;font-size:.86rem;color:var(--muted)">버린 관계 없음</p>`) +
        `<p style="font-size:.84rem;color:var(--muted)">토론: "서해광물 제2정제공장"과 "서해광물"은 같은 노드여야 할까? 문자열 정규화만으로는 판단할 수 없습니다. 임베딩 유사도나 LLM 판정이 필요한 이유입니다.</p>`;
    },
    /* ── 문서 처리 모드 ── */
    pages(v, box) {
      const max = Math.max(...v.chars);
      box.innerHTML = `<div class="chips"><span class="chip">파일 <b>${esc(v.file)}</b></span><span class="chip">페이지 <b>${v.chars.length}</b></span><span class="chip">총 <b>${v.chars.reduce((a, b) => a + b, 0).toLocaleString()}자</b></span></div>
        <div class="pagebars" role="list" aria-label="페이지별 글자 수">${v.chars.map((c, i) => `<button type="button" role="listitem" data-page="${i}" class="${i === v.page ? "on" : ""}" title="보고서 ${v.offset + i}쪽 · ${c}자" style="height:${8 + 72 * c / max}px"></button>`).join("")}</div>
        <p style="font-size:.84rem;color:var(--muted)">막대 = 페이지별 추출 글자 수. 선택: 보고서 <b>${v.offset + v.page}쪽</b> (PDF ${v.page + 1}쪽)</p>
        <pre class="box">${esc(v.text)}</pre>`;
      box.querySelectorAll("[data-page]").forEach(b => b.addEventListener("click", () => { S.ingest.page = +b.dataset.page; runIngest(S.idx); }));
    },
    cleaning(v, box) {
      const kept = v.lines.filter(l => !l.reason).length;
      box.innerHTML = `<div class="chips">${Object.entries(v.totals).map(([r, n]) => `<span class="chip ${r === "남김" ? "keep" : ""}">${esc(r)} <b>${n}</b></span>`).join("")}</div>
        <p style="font-size:.84rem;color:var(--muted)">보고서 ${v.offset + v.page}쪽: ${v.lines.length}줄 중 <b>${kept}줄 남김</b>, ${v.lines.length - kept}줄 제거. (페이지는 ① 단계 막대에서 바꿀 수 있습니다)</p>
        <div class="cleanlines">${v.lines.map(l => l.reason ? `<div class="rm"><s>${esc(l.line) || "&nbsp;"}</s><span class="badge bad">${esc(l.reason)}</span></div>` : `<div>${esc(l.line)}</div>`).join("")}</div>`;
    },
    sections(v, box) {
      const max = Math.max(...v.docs.map(d => d.chars));
      box.innerHTML = `<table class="t"><thead><tr><th>문서</th><th>제목</th><th>출처</th><th>길이</th></tr></thead><tbody>${v.docs.map(d => `<tr class="${d.doc_id === v.selected ? "sel" : ""}"><td>${docChip(d.doc_id)}</td><td>${esc(d.title)}</td><td style="font-size:.8rem;color:var(--muted)">${esc(d.where)}</td><td><span class="sbar"><i style="width:${Math.max(2, 80 * d.chars / max)}px;background:${docColor(d.doc_id)}"></i><span>${d.chars.toLocaleString()}자</span></span></td></tr>`).join("")}</tbody></table>`;
    },
    chunking(v, box) { chunkView(v, box); },
    embedding(v, box) {
      const cols = v.rows[0]?.v.length || 0, cw = 12, rh = 18, lw = 150, W = lw + cols * cw, H = v.rows.length * rh;
      const max = Math.max(...v.rows.flatMap(r => r.v.map(Math.abs))) || 1;
      const labels = v.rows.map((r, i) => `<text class="lbl" x="0" y="${i * rh + 12}">청크 ${i + 1} · ${esc(r.text.replace(/\s+/g, " ").slice(0, 9))}…</text>`).join("");
      const cells = labels + v.rows.map((r, i) => r.v.map((x, j) => `<rect x="${lw + j * cw}" y="${i * rh}" width="${cw - 1}" height="${rh - 2}" fill="${x >= 0 ? "var(--vec)" : "var(--hyb)"}" opacity="${(0.12 + 0.88 * Math.abs(x) / max).toFixed(2)}"><title>청크 ${i + 1} · 차원 ${j} = ${x}</title></rect>`).join("")).join("");
      box.innerHTML = `<div class="chips"><span class="chip">모델 <b>${esc(v.model)}</b></span><span class="chip">차원 <b>${v.dim}</b></span><span class="chip">${esc(v.doc_id)}의 청크 <b>${v.rows.length}개</b></span><span class="chip">앞 ${cols}개 차원만 표시</span></div>
        <div class="svgbox"><svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:520px;height:auto;display:block" role="img" aria-label="청크 임베딩 히트맵">${cells}</svg></div>
        <p style="font-size:.82rem;color:var(--muted)">파랑 = 양수, 주황 = 음수, 진할수록 절댓값이 큼. 사람이 읽을 수 있는 의미는 없지만, 비슷한 문장은 비슷한 무늬를 갖습니다.</p>`;
    },
    store(v, box) {
      box.innerHTML = `<div class="cmp"><div class="col"><span style="color:var(--muted)">저장된 청크</span><span class="big">${v.count}</span></div><div class="col"><span style="color:var(--muted)">벡터 차원</span><span class="big">${v.dim}</span></div><div class="col"><span style="color:var(--muted)">벡터 메모리 (float64)</span><span class="big">${(v.bytes / 1024).toFixed(0)} KB</span></div></div>
        <h3>레코드 하나의 모양</h3><pre class="box">${esc(JSON.stringify(v.sample, null, 2))}</pre>
        <p style="font-size:.86rem"><button type="button" class="btn primary live" data-live="vector" data-q="q3">▶ 이 인덱스로 질문해 보기 (벡터 RAG)</button></p>`;
    },
    json(v, box) { box.innerHTML = `<pre class="box">${esc(JSON.stringify(v, null, 2))}</pre>`; },
  };


  /* ── 청크 분할: 슬라이더로 크기·겹침을 바꾸면 서버가 다시 자르고 경계를 색으로 표시 ── */
  function chunkView(v, box) {
    const text = v.text, spans = v.spans;
    const cuts = [...new Set([0, text.length, ...spans.flatMap(c => [c.start, c.end])])].sort((a, b) => a - b);
    let html = "";
    for (let i = 0; i < cuts.length - 1; i++) {
      const a = cuts[i], b = cuts[i + 1];
      const cover = spans.map((c, j) => c.start <= a && b <= c.end ? j : -1).filter(j => j >= 0);
      const starts = spans.map((c, j) => c.start === a ? j : -1).filter(j => j >= 0);
      const tag = starts.map(j => `<span class="cnum" style="background:${DOC_COLORS[j % DOC_COLORS.length]}">${j + 1}</span>`).join("");
      const cls = cover.length > 1 ? "ov" : cover.length ? "c" : "gap";
      const color = cover.length ? DOC_COLORS[cover[0] % DOC_COLORS.length] : "transparent";
      html += tag + `<span class="${cls}" style="--cc:${color}">${esc(text.slice(a, b))}</span>`;
    }
    const lens = spans.map(c => c.len);
    box.innerHTML = `<div class="chunkctl">
        <label>청크 크기 <b id="csV">${v.chunk_size}</b>자<input type="range" id="csR" min="100" max="1500" step="50" value="${v.chunk_size}"></label>
        <label>겹침 <b id="coV">${v.overlap}</b>자<input type="range" id="coR" min="0" max="300" step="10" value="${v.overlap}"></label>
        <button type="button" class="btn" id="reindex">이 설정으로 벡터 인덱스 다시 만들기</button>
      </div>
      <div class="chips"><span class="chip">${esc(v.doc_id)} 청크 <b>${spans.length}개</b></span><span class="chip">길이 <b>${Math.min(...lens)}~${Math.max(...lens)}자</b></span><span class="chip">전체 19개 문서 → 청크 <b>${v.total}개</b> (평균 ${v.avg}자)</span><span class="chip">현재 인덱스 설정 <b>${v.index_chunk_size}/${v.index_overlap}</b></span></div>
      <p style="font-size:.82rem;color:var(--muted)">색 = 청크, 진한 줄무늬 = 두 청크가 겹치는 부분, 숫자 = 청크 시작 위치</p>
      <div class="chunktext">${html}</div><div id="reidxMsg"></div>`;
    let timer;
    const upd = () => {
      $("#csV").textContent = $("#csR").value; $("#coV").textContent = $("#coR").value;
      clearTimeout(timer);
      timer = setTimeout(async () => {
        S.ingest.chunk_size = +$("#csR").value; S.ingest.overlap = Math.min(+$("#coR").value, S.ingest.chunk_size - 10);
        try {
          const nv = await api("/api/ingest/chunks", S.ingest);
          const st = S.trace.steps.find(x => x.id === "chunk"); st.view = nv;
          chunkView(nv, box); drawHistogram(nv);
        } catch (e) { $("#reidxMsg").innerHTML = `<p class="note warn">${esc(e.message)}</p>`; }
      }, 150);
    };
    $("#csR").addEventListener("input", upd); $("#coR").addEventListener("input", upd);
    $("#reindex").addEventListener("click", async () => {
      $("#reindex").disabled = true; $("#reidxMsg").innerHTML = `<p class="note">임베딩을 다시 계산하는 중…</p>`;
      try {
        const r = await api("/api/config/chunking", S.ingest);
        CFG.chunking = {chunk_size: r.chunk_size, overlap: r.overlap};
        $("#reidxMsg").innerHTML = `<p class="note">벡터 인덱스를 다시 만들었습니다: 청크 ${r.chunks}개, ${fmtMs(r.index_ms)}. 이후 벡터 RAG·비교 모드에 반영됩니다.</p>`;
      } catch (e) { $("#reidxMsg").innerHTML = `<p class="note warn">${esc(e.message)}</p>`; }
      $("#reindex").disabled = false;
    });
  }

  /* ── 프롬프트 구성: 출처별 비율 막대 + 색칠된 본문 ── */
  function promptView(v, box) {
    const segColor = sg => sg.kind === "template" ? "var(--line)" : sg.kind === "question" ? "var(--warn)" : sg.kind === "triples" ? "var(--accent)"
      : sg.community != null ? COMM[sg.community % COMM.length] : docColor(sg.doc_id);
    const total = v.segments.reduce((a, sg) => a + sg.text.length, 0);
    const agg = {};
    v.segments.forEach(sg => { const k = sg.kind === "template" ? "지시문·양식" : sg.label; agg[k] = agg[k] || {n: 0, color: segColor(sg)}; agg[k].n += sg.text.length; });
    box.innerHTML = `<div class="chips"><span class="chip">LLM 입력 길이 <b>${v.chars.toLocaleString()}자</b></span><span class="chip">한국어 기준 대략 <b>${Math.round(v.chars / 1.5).toLocaleString()} 토큰</b> 내외</span></div>
      <div class="compbar" role="img" aria-label="프롬프트 구성 비율">${v.segments.map(sg => `<i style="flex:${sg.text.length};background:${segColor(sg)}" title="${esc(sg.kind === "template" ? "지시문·양식" : sg.label)} · ${sg.text.length}자"></i>`).join("")}</div>
      <div class="legend">${Object.entries(agg).map(([k, a]) => `<span><i style="background:${a.color}"></i>${esc(k)} ${Math.round(100 * a.n / total)}%</span>`).join("")}</div>
      <pre class="box segtext">${v.segments.map(sg => sg.kind === "template" ? `<span class="tpl">${esc(sg.text)}</span>` : `<span class="seg" style="--sc:${segColor(sg)}" title="${esc(sg.label)}">${esc(sg.text)}</span>`).join("")}</pre>`;
  }

  /* ── 오른쪽 패널 차트 ── */
  function drawBarsV(values, {sel, label, color}) {
    const svg = $("#vis"), W = 640, H = 300, pad = 30, n = values.length, bw = (W - 2 * pad) / n, max = Math.max(...values) || 1;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.classList.remove("dim"); S.kgView = null;
    svg.innerHTML = values.map((x, i) => { const h = (H - 2 * pad) * x / max; return `<rect x="${pad + i * bw + 1}" y="${H - pad - h}" width="${Math.max(bw - 2, 1)}" height="${h}" fill="${i === sel ? "var(--warn)" : color(i)}"><title>${esc(label(i))}: ${x}</title></rect>`; }).join("")
      + `<line class="axis" x1="${pad}" x2="${W - pad}" y1="${H - pad}" y2="${H - pad}"/><text class="lbl" x="${pad}" y="${H - 8}">${esc(label(0))}</text><text class="lbl" x="${W - pad}" y="${H - 8}" text-anchor="end">${esc(label(n - 1))}</text><text class="lbl" x="${pad}" y="${pad - 10}">최대 ${max.toLocaleString()}</text>`;
  }
  function drawHistogram(v) {
    const bins = 12, lo = 0, hi = Math.max(v.chunk_size, ...v.lens), w = (hi - lo) / bins;
    const counts = Array(bins).fill(0); v.lens.forEach(x => counts[Math.min(bins - 1, Math.floor((x - lo) / w))]++);
    drawBarsV(counts, {sel: -1, label: i => `${Math.round(lo + i * w)}~${Math.round(lo + (i + 1) * w)}자`, color: () => "var(--vec)"});
    $("#visualTitle").textContent = "청크 길이 분포 (전체 문서)";
    $("#visualNote").textContent = `청크 ${v.total}개 · 크기 ${v.chunk_size} / 겹침 ${v.overlap}`;
    $("#visLegend").innerHTML = `<span>막대 = 해당 길이 구간의 청크 수. 대부분 설정 크기 근처에 모이고, 문단 끝에서 짧은 청크가 생깁니다.</span>`;
  }
  function drawDocScatter(sc) {
    const svg = $("#vis"); S.kgView = null;
    const W = 640, H = 460, pad = 30, xs = sc.points.map(p => p.x), ys = sc.points.map(p => p.y);
    const X = x => pad + (x - Math.min(...xs)) / ((Math.max(...xs) - Math.min(...xs)) || 1) * (W - 2 * pad);
    const Y = y => pad + (y - Math.min(...ys)) / ((Math.max(...ys) - Math.min(...ys)) || 1) * (H - 2 * pad);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.classList.remove("dim");
    svg.innerHTML = sc.points.map(p => `<circle class="pt" cx="${X(p.x)}" cy="${Y(p.y)}" r="${p.doc_id === sc.focus ? 8 : 5}" fill="${docColor(p.doc_id)}" opacity="${p.doc_id === sc.focus ? 1 : .45}"><title>${p.doc_id}</title></circle>`).join("")
      + sc.points.filter(p => p.doc_id === sc.focus).map(p => `<text class="lbl" x="${X(p.x) + 9}" y="${Y(p.y) + 4}">${p.doc_id}</text>`).join("");
    $("#visualTitle").textContent = "청크 임베딩 공간 (PCA 2차원)";
    $("#visualNote").textContent = `점 ${sc.points.length}개 = 청크, 색 = 문서, 큰 점 = ${sc.focus}`;
    $("#visLegend").innerHTML = `<span>같은 문서(같은 색)의 청크끼리 가까이 모이는지 보세요. 2차원 투영이라 거리는 근사치입니다.</span>`;
  }
  /* ── LLM 스트리밍 박스 ───────────────────────────────────── */
  function llmBox(box, messages, key) {
    const noLLM = !CFG.llm;
    box.innerHTML = `<div class="llmbox">
      ${noLLM ? `<p class="note warn">LLM이 설정되지 않아 이 단계는 실행할 수 없습니다. <code>.env</code>에 <code>LLM_MODEL</code>과 API 키를 넣고 서버를 다시 시작하세요. 앞 단계까지의 검색은 모두 실제로 실행된 결과입니다.</p>` : ""}
      <div class="controls"><button class="btn primary" type="button" data-go ${noLLM ? "disabled" : ""}>LLM 답변 생성 ▶</button><span class="chip">모델 <b>${esc(CFG.llm || "없음")}</b></span></div>
      <div class="llmout" data-out>${noLLM ? "" : '<span style="color:var(--muted)">버튼을 누르면 답변이 실시간으로 스트리밍됩니다.</span>'}</div>
      <div class="metrics" data-met></div></div>`;
    const out = box.querySelector("[data-out]"), met = box.querySelector("[data-met]"), go = box.querySelector("[data-go]");
    go?.addEventListener("click", async () => {
      go.disabled = true; out.classList.remove("err"); out.innerHTML = '<span class="cursor"></span>';
      let text = "";
      await stream("/api/answer", {messages}, ev => {
        if (ev.error) { out.classList.add("err"); out.textContent = ev.error; }
        else if (ev.t) { text += ev.t; out.innerHTML = esc(text) + '<span class="cursor"></span>'; }
        else if (ev.done) {
          out.innerHTML = esc(text).replace(/\[?(doc\d{2})\]?/g, (m, d) => `<button type="button" class="doc" data-doc="${d}" style="border-color:${docColor(d)}">${d}</button>`);
          met.innerHTML = `<span class="chip">첫 토큰 <b>${fmtMs(ev.ttft_ms)}</b></span><span class="chip">전체 <b>${fmtMs(ev.total_ms)}</b></span>` +
            (ev.input_tokens != null ? `<span class="chip">입력 토큰 <b>${ev.input_tokens}</b></span><span class="chip">출력 토큰 <b>${ev.output_tokens}</b></span>` : "");
        }
      }).catch(e => { out.classList.add("err"); out.textContent = e.message; });
      go.disabled = false; go.textContent = "다시 생성 ▶";
    });
    return go;
  }

  /* ── 비교 ───────────────────────────────────────────────── */
  function renderCompare(r) {
    const L = {vector: "벡터 RAG", graph: "그래프 Local", hybrid: "하이브리드"};
    const gold = r.gold?.docs;
    $("#stage").innerHTML = `<div class="stage-head"><span class="ph">나란히 비교 · k=${$("#kSelect").value}</span><h2>${esc(r.question)}</h2></div>
      <div class="cmp">${r.rows.map(x => `<div class="col ${x.method}"><h3>${L[x.method]}</h3>
        <span class="big">${x.recall == null ? "–" : Math.round(x.recall * 100) + "%"}</span><span style="font-size:.78rem;color:var(--muted)">${x.recall == null ? "정답 정보 없음" : "Recall (정답 근거 중 찾은 비율)"}</span>
        <div class="docs">${x.docs.map(d => docChip(d, gold)).join("")}</div></div>`).join("")}</div>
      ${r.gold ? `<div class="gold"><b>정답 근거</b> ${r.gold.docs.map(d => docChip(d)).join("")}<span style="font-size:.84rem;color:var(--muted)">${esc(r.gold.answer)}</span></div>` : `<div class="gold"><span style="color:var(--muted)">직접 입력한 질문이라 정답 근거 정보가 없습니다.</span></div>`}
      <p style="font-size:.88rem">그래프가 찾은 엔티티: ${r.seeds.map(esc).join(", ") || "없음"}</p>
      <div class="grid2"><div class="card"><h3 style="color:var(--vec)">벡터 RAG 답변</h3><div data-a="0"></div></div><div class="card"><h3 style="color:var(--accent)">그래프 RAG 답변</h3><div data-a="1"></div></div></div>
      ${CFG.llm ? `<button class="btn primary" type="button" id="bothGo" style="justify-self:start">두 답변 동시 생성 ▶</button>` : ""}`;
    const gos = r.rows.slice(0, 2).map((x, i) => llmBox($(`[data-a="${i}"]`), x.messages));
    $("#bothGo")?.addEventListener("click", () => gos.forEach(g => g?.click()));
    kgHighlight(r.graph);
    $("#visualNote").textContent = "그래프 검색이 본 영역 · 초록 선 = 경로";
  }

  /* ── 에이전트 ───────────────────────────────────────────── */
  async function runAgent(q) {
    S.events = []; S.trace = null;
    $("#steps").innerHTML = "";
    $("#stage").innerHTML = `<div class="stage-head"><span class="ph">에이전트 · 실시간</span><h2>${esc(q)}</h2></div>
      <p class="explain">고정된 파이프라인 대신 LLM이 매 턴 어떤 도구를 쓸지 결정합니다. 도구 호출과 결과가 도착하는 대로 표시됩니다.</p><div class="events" id="events"></div>`;
    drawKG();
    const visited = new Set();
    const names = CFG.kg.nodes.map(n => n.id).sort((a, b) => b.length - a.length);
    const LBL = {tool_call: "도구 호출", tool_result: "도구 결과", thought: "생각", final: "최종 답변", error: "오류", done: "완료"};
    await stream("/api/agent", {question: q}, ev => {
      if (ev.error) { $("#events").innerHTML = `<p class="note warn">${esc(ev.error)}</p>`; return; }
      S.events.push(ev);
      const i = S.events.length;
      let body = "";
      if (ev.type === "tool_call") body = `<b>${esc(ev.name)}</b><pre>${esc(JSON.stringify(ev.args, null, 1))}</pre>`;
      else if (ev.type === "tool_result") body = `<details><summary>${esc(ev.name)} 결과 (${ev.content.length}자)</summary><pre>${esc(ev.content)}</pre></details>`;
      else if (ev.type === "done") body = `<span>총 ${fmtMs(ev.ms)}, 도구 호출 ${S.events.filter(e => e.type === "tool_call").length}회</span>`;
      else body = `<div style="white-space:pre-wrap">${esc(ev.text)}</div>`;
      $("#events").insertAdjacentHTML("beforeend", `<div class="ev ${ev.type}" id="ev${i}"><div class="meta"><span>#${i}</span><span>${LBL[ev.type] || ev.type}</span><span>${fmtMs(ev.ms)}</span></div>${body}</div>`);
      $("#steps").insertAdjacentHTML("beforeend", `<li><button type="button" onclick="document.getElementById('ev${i}').scrollIntoView({block:'center'})"><span class="no">${i}</span><span>${LBL[ev.type] || ev.type}${ev.name ? " · " + esc(ev.name) : ""}</span><span class="ms">${fmtMs(ev.ms)}</span></button></li>`);
      const txt = ev.type === "tool_call" ? JSON.stringify(ev.args) : ev.content || "";
      const now = names.filter(n => txt.includes(n));
      now.forEach(n => visited.add(n));
      kgHighlight({seeds: ev.type === "tool_call" ? now : [], focus: [...visited], near: false});
      $("#visualNote").textContent = `에이전트가 살펴본 노드 ${visited.size}개`;
    }).catch(e => $("#events").insertAdjacentHTML("beforeend", `<p class="note warn">${esc(e.message)}</p>`));
  }

  /* ── 시간 메모리 ─────────────────────────────────────────── */
  async function renderTemporal() {
    $("#stage").innerHTML = `<div class="stage-head"><span class="ph">트렌드 · 에이전트 메모리</span><h2>시간 인식 지식그래프</h2></div>
      <p class="explain">보고서의 시점별 수치를 기억으로 쌓습니다. 사실마다 유효 기간을 두고, 같은 지표의 새 값이 들어오면 옛 값을 지우지 않고 '무효화'합니다. 벡터 검색은 2.3%·3.6%·5.2%를 모두 돌려주지만, 시간 인식 그래프는 질의 시점에 유효한 값 하나를 고릅니다. 슬라이더로 시점을 바꿔 보세요.</p>
      <div class="coderow"><button type="button" class="btn" data-code="lab/temporal_kg.py#TemporalKG">lab/temporal_kg.py · TemporalKG</button><button type="button" class="btn" data-file="lab/09_temporal_memory.py">09_temporal_memory.py</button></div>
      <svg class="tl-chart" id="tlChart" role="img" aria-label="사실별 유효 기간"></svg>
      <label style="display:grid;gap:4px;font-size:.86rem">질의 시점 <input type="range" id="asOf" min="0" max="323" value="186"></label>
      <div class="gold" id="tAnswer"></div>
      <h3>새 에피소드(사실) 추가</h3>
      <div class="tform">
        <label>지표(주어)<input id="tS" value="한국 R&D 지출(GDP 대비)"></label><label>관계<input id="tR" value="VALUE"></label><label>값<input id="tT" value="5.2%"></label>
        <label>시작일<input id="tD" type="date" value="2022-01-01"></label><label>출처<input id="tE" value="doc03 (2022년 통계)"></label>
        <span class="controls"><button type="button" class="btn primary" id="tAdd">추가</button><button type="button" class="btn" id="tReset">초기화</button></span>
      </div><div id="tMsg"></div>`;
    const load = async () => draw((await api("/api/temporal")).facts);
    const Y0 = 2000;
    const monthToDate = m => { const y = Y0 + Math.floor(m / 12), mo = m % 12 + 1; return `${y}-${String(mo).padStart(2, "0")}-01`; };
    const dateToMonth = d => { const [y, m] = d.split("-").map(Number); return (y - Y0) * 12 + (m - 1); };
    let facts = [];
    function draw(f) {
      facts = f;
      const W = 760, rowH = 34, top = 30, H = top + rowH * facts.length + 16, x0 = 250, x1 = W - 16, span = 324;
      const X = m => x0 + (x1 - x0) * Math.min(m, span) / span;
      let s = "";
      for (let y = Y0; y <= 2027; y += 3) { const x = X((y - Y0) * 12); s += `<line x1="${x}" x2="${x}" y1="${top - 6}" y2="${H - 10}" class="axis"/><text x="${x}" y="${top - 12}" class="tick" text-anchor="middle">${y}</text>`; }
      facts.forEach((f, i) => {
        const y = top + i * rowH, a = X(dateToMonth(f.valid_from)), b = f.valid_to ? X(dateToMonth(f.valid_to)) : x1;
        s += `<text x="8" y="${y + 20}">${esc(f.source)} = ${esc(f.target)}</text><rect class="bar ${f.valid_to ? "dead" : ""}" x="${a}" y="${y + 8}" width="${Math.max(b - a, 3)}" height="16" rx="4"><title>${esc(f.valid_from)} ~ ${esc(f.valid_to || "현재")} · ${esc(f.episode)}</title></rect>`;
      });
      const m = +$("#asOf").value;
      s += `<line class="now" x1="${X(m)}" x2="${X(m)}" y1="${top - 6}" y2="${H - 10}"/>`;
      $("#tlChart").setAttribute("viewBox", `0 0 ${W} ${H}`); $("#tlChart").innerHTML = s;
      query();
    }
    async function query() {
      const d = monthToDate(+$("#asOf").value);
      const rels = [...new Set(facts.map(f => `${f.source}|${f.relation}`))];
      const ans = await Promise.all(rels.map(async r => { const [s, rel] = r.split("|"); return [s, rel, (await api(`/api/temporal/query?source=${encodeURIComponent(s)}&relation=${encodeURIComponent(rel)}&as_of=${d}`)).answer]; }));
      $("#tAnswer").innerHTML = `<b>${d} 기준</b> ` + ans.map(([s, r, a]) => `<span class="chip">${esc(s)} · ${esc(r)} → <b>${esc(a.join(", ") || "없음")}</b></span>`).join(" ");
    }
    $("#asOf").addEventListener("input", () => draw(facts));
    $("#tAdd").addEventListener("click", async () => {
      const r = await api("/api/temporal/add", {source: $("#tS").value, relation: $("#tR").value, target: $("#tT").value, valid_from: $("#tD").value, episode: $("#tE").value});
      $("#tMsg").innerHTML = r.invalidated.length ? `<p class="note warn">무효화됨: ${r.invalidated.map(esc).join(", ")} (삭제하지 않고 유효 기간만 닫음)</p>` : `<p class="note">추가됨. 모순되는 기존 사실 없음.</p>`;
      draw(r.facts);
    });
    $("#tReset").addEventListener("click", async () => { $("#tMsg").innerHTML = ""; draw((await api("/api/temporal/reset", {})).facts); });
    load();
  }

  /* ── 시각화 패널 ─────────────────────────────────────────── */
  function clearVisual(title, note) { $("#visualTitle").textContent = title; $("#visualNote").textContent = note || ""; $("#vis").innerHTML = ""; $("#visLegend").innerHTML = ""; S.kgView = null; }
  const deg = () => { const d = {}; CFG.kg.edges.forEach(e => { d[e.s] = (d[e.s] || 0) + 1; d[e.t] = (d[e.t] || 0) + 1; }); return d; };
  function drawKG(colorBy = "type") {
    const D = deg(), svg = $("#vis");
    svg.classList.remove("dim");
    S.kgView = drawGraph(svg, CFG.kg, {w: 960, h: 620, directed: true, r: n => 6 + Math.min(D[n.id] || 0, 10) * .9,
      color: n => colorBy === "community" ? COMM[n.c % COMM.length] : TYPE_COLOR[n.type] || "var(--t5)"});
    S.kgView.color = colorBy;
    $("#visualTitle").textContent = "지식그래프 (kg.json · 노드 " + CFG.kg.nodes.length + " · 관계 " + CFG.kg.edges.length + ")";
    $("#visualNote").textContent = "노드를 누르면 상세 정보";
    $("#visLegend").innerHTML = colorBy === "community"
      ? CFG.communities.map(c => `<span><i style="background:${COMM[c.id % COMM.length]}"></i>C${c.id} ${esc(c.title)}</span>`).join("")
      : TYPE_GROUPS.map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("") + `<span>굵은 테두리 = 시드 · 초록 선 = 경로</span>`;
    S.kgView.nodes.forEach((g, id) => g.addEventListener("click", () => nodeInfo(id)));
  }
  function nodeInfo(id) {
    const n = CFG.kg.nodes.find(x => x.id === id);
    const rel = CFG.kg.edges.filter(e => e.s === id || e.t === id).map(e => `${e.s} —${e.type}→ ${e.t} [${e.doc}]`);
    const box = $("#nodeInfo"); box.hidden = false;
    box.innerHTML = `<b>${esc(n.id)} <span style="font-family:var(--f-mono);font-size:.74rem;color:var(--muted)">${n.type} · C${n.c}</span></b><span>${esc(n.description)}</span><span class="docs">${n.docs.map(d => `<button type="button" class="doc" data-doc="${d}">${d}</button>`).join("")}</span><span style="font-family:var(--f-mono);font-size:.74rem;color:var(--muted);white-space:pre-wrap">${rel.map(esc).join("\n")}</span>`;
  }
  function kgHighlight(g) {
    if (!S.kgView) drawKG();
    const want = g.color === "community" ? "community" : "type";
    if (S.kgView.color !== want) drawKG(want);
    const V = S.kgView, svg = $("#vis"), D = deg();
    V.nodes.forEach((n, id) => { n.classList.remove("keep", "seed", "path"); n.style.opacity = ""; n.querySelector("circle").setAttribute("r", 6 + Math.min(D[id] || 0, 10) * .9); });
    V.edges.forEach(e => e.classList.remove("on", "near"));
    const focus = g.focus || [];
    svg.classList.toggle("dim", focus.length > 0);
    focus.forEach(id => V.nodes.get(id)?.classList.add("keep"));
    (g.seeds || []).forEach(id => V.nodes.get(id)?.classList.add("seed", "keep"));
    (g.edges || []).forEach(k => { V.edges.get(k)?.classList.add("on"); k.split("|").slice(0, 2).forEach(id => V.nodes.get(id)?.classList.add("path", "keep")); });
    if (g.near) V.edges.forEach((e, k) => { const [a, b] = k.split("|"); if (focus.includes(a) && focus.includes(b) && !e.classList.contains("on")) e.classList.add("near"); });
    if (g.weights) {
      const max = Math.max(...Object.values(g.weights)) || 1;
      V.nodes.forEach((n, id) => n.querySelector("circle").setAttribute("r", 4 + 20 * Math.sqrt((g.weights[id] || 0) / max)));
    }
    if (g.communityScores) {
      svg.classList.remove("dim");
      V.nodes.forEach((n, id) => { const c = CFG.kg.nodes.find(x => x.id === id).c; n.style.opacity = .25 + .75 * ((g.communityScores[String(c)] || 0) / 100); });
    }
  }
  function drawMini(mini) {
    const svg = $("#vis"); S.kgView = null;
    const n = mini.nodes.length, W = 640, H = 460, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 70;
    const nodes = mini.nodes.map((id, i) => ({id, x: cx + R * Math.cos(2 * Math.PI * i / n - Math.PI / 2), y: cy + R * Math.sin(2 * Math.PI * i / n - Math.PI / 2)}));
    drawGraph(svg, {nodes, edges: mini.edges}, {w: W, h: H, directed: true, r: () => 11, color: () => "var(--t3)"});
    svg.classList.remove("dim");
    $("#visualTitle").textContent = "이 문서에서 추출된 그래프";
    $("#visualNote").textContent = `엔티티 ${n} · 관계 ${mini.edges.length}`;
    $("#visLegend").innerHTML = `<span>선에 마우스를 올리면 관계 이름</span>`;
  }
  function drawScatter(sc, level) {
    const svg = $("#vis"); S.kgView = null;
    const W = 640, H = 460, pad = 36, all = [...sc.points, sc.query];
    const xs = all.map(p => p.x), ys = all.map(p => p.y);
    const X = x => pad + (x - Math.min(...xs)) / ((Math.max(...xs) - Math.min(...xs)) || 1) * (W - 2 * pad);
    const Y = y => pad + (y - Math.min(...ys)) / ((Math.max(...ys) - Math.min(...ys)) || 1) * (H - 2 * pad);
    const max = Math.max(...sc.points.map(p => p.score)), min = Math.min(...sc.points.map(p => p.score));
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.classList.remove("dim");
    let s = "";
    if (level >= 3) sc.points.filter(p => sc.selected.includes(p.doc_id)).forEach(p => { s += `<line class="ray" x1="${X(sc.query.x)}" y1="${Y(sc.query.y)}" x2="${X(p.x)}" y2="${Y(p.y)}"/>`; });
    sc.points.forEach(p => {
      const t = level >= 2 ? (p.score - min) / ((max - min) || 1) : .5;
      const sel = level >= 3 && sc.selected.includes(p.doc_id);
      s += `<g><circle class="pt" cx="${X(p.x)}" cy="${Y(p.y)}" r="${level >= 2 ? 5 + 9 * t : 7}" fill="${sel ? "var(--accent)" : "var(--vec)"}" opacity="${level >= 2 ? .25 + .75 * t : .8}"><title>${p.doc_id} · 유사도 ${p.score.toFixed(3)}</title></circle>${level >= 3 && sc.selected.includes(p.doc_id) ? `<text class="lbl" x="${X(p.x) + 9}" y="${Y(p.y) + 4}">${p.doc_id}</text>` : ""}</g>`;
    });
    if (level >= 1) s += `<path class="qpt" d="M${X(sc.query.x)} ${Y(sc.query.y) - 11}l3.2 7 7.6.8-5.7 5.1 1.6 7.5-6.7-3.9-6.7 3.9 1.6-7.5-5.7-5.1 7.6-.8z"/><text class="lbl" x="${X(sc.query.x) + 12}" y="${Y(sc.query.y) - 8}" style="fill:var(--warn)">질문</text>`;
    svg.innerHTML = s;
    $("#visualTitle").textContent = "임베딩 공간 (PCA 2차원 투영)";
    $("#visualNote").textContent = ["청크 벡터들", "질문 벡터 추가", "원 크기·진하기 = 유사도", "초록 = 선택된 문서의 청크"][Math.min(level, 3)];
    $("#visLegend").innerHTML = `<span><i style="background:var(--vec)"></i>청크</span><span><i style="background:var(--warn)"></i>질문</span>${level >= 3 ? '<span><i style="background:var(--accent)"></i>Top-k 문서</span>' : ""}<span>2차원 투영이라 거리는 근사치</span>`;
  }
  function updateVisual(step, i) {
    if (S.mode === "ingest") {
      const v = step.view;
      if (step.id === "load") drawBarsV(v.chars, {sel: v.page, label: j => `${v.offset + j}쪽`, color: () => "var(--vec)"}), $("#visualTitle").textContent = "페이지별 추출 글자 수", $("#visualNote").textContent = "주황 = 선택 페이지", $("#visLegend").innerHTML = "<span>표·차트가 많은 페이지는 숫자가 많아 글자 수가 들쭉날쭉합니다.</span>";
      else if (step.id === "clean") { const e = Object.entries(v.totals); drawBarsV(e.map(x => x[1]), {sel: -1, label: j => e[j][0], color: j => e[j][0] === "남김" ? "var(--ok)" : "var(--warn)"}); $("#visualTitle").textContent = "전체 49쪽 정제 결과 (줄 수)"; $("#visualNote").textContent = e.map(x => `${x[0]} ${x[1]}`).join(" · "); $("#visLegend").innerHTML = "<span>초록 = 남긴 줄, 빨강 = 이유별 지운 줄</span>"; }
      else if (step.id === "sections") { drawBarsV(v.docs.map(d => d.chars), {sel: v.docs.findIndex(d => d.doc_id === v.selected), label: j => v.docs[j].doc_id, color: j => docColor(v.docs[j].doc_id)}); $("#visualTitle").textContent = "문서별 길이 (글자)"; $("#visualNote").textContent = "주황 = 선택 문서"; $("#visLegend").innerHTML = ""; }
      else if (step.id === "chunk") drawHistogram(v);
      else { const sc = S.trace.steps.find(x => x.scatter)?.scatter; if (sc) drawDocScatter(sc); }
      return;
    }
    if (S.mode === "vector") {
      const sc = S.trace.steps.find(s => s.scatter)?.scatter;
      if (sc) drawScatter(sc, {chunk: 0, embed: 1, similarity: 2}[step.id] ?? 3);
      return;
    }
    // 그래프 상태가 없는 단계(프롬프트, 답변 등)는 직전 단계의 하이라이트를 유지
    let g = null;
    for (let j = i; j >= 0 && !g; j--) g = S.trace.steps[j].graph;
    if (g?.mini) { drawMini(g.mini); return; }
    if (!S.kgView || (g?.color === "community") !== (S.kgView.color === "community")) drawKG(g?.color === "community" ? "community" : "type");
    kgHighlight(g || {});
    step = {graph: g};
    if (step.graph?.weights) $("#visualNote").textContent = "노드 크기 = PPR 점수";
    else if (step.graph?.communityScores) $("#visualNote").textContent = "진하기 = Map 관련도";
  }

  init();
})();
