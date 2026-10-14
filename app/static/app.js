/* 공통 유틸 + 강의 화면 + 코드 뷰어 + 발표 모드. 라이브 실험실은 live.js */
const GR = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const NS = "http://www.w3.org/2000/svg";
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const el = (tag, attrs = {}, html) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (html != null) e.innerHTML = html; return e; };
  const svgEl = (tag, attrs = {}) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
  async function api(path, body) {
    const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
    return r.json();
  }
  /* SSE(POST) 읽기: 서버가 보내는 data: {...} 줄을 하나씩 콜백으로 */
  async function stream(path, body, onEvent) {
    const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 2);
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
      }
    }
  }
  /* 범용 그래프 렌더러 */
  function drawGraph(svg, g, {w, h, directed = false, r = () => 9, color = () => "var(--t1)", label = n => n.id}) {
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.innerHTML = "";
    const mid = "arr-" + svg.id;
    if (directed) svg.innerHTML = `<defs><marker id="${mid}" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker></defs>`;
    const pos = Object.fromEntries(g.nodes.map(n => [n.id, n]));
    const eg = svgEl("g"), ng = svgEl("g");
    const edges = new Map(), nodes = new Map();
    for (const e of g.edges) {
      const a = pos[e.s], b = pos[e.t]; if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, rb = r(b) + 3;
      const line = svgEl("line", {x1: a.x, y1: a.y, x2: b.x - dx / d * rb, y2: b.y - dy / d * rb, class: "e"});
      if (directed) line.setAttribute("marker-end", `url(#${mid})`);
      if (e.type) { const t = svgEl("title"); t.textContent = `${e.s} —${e.type}→ ${e.t}${e.desc ? "\n" + e.desc : ""}${e.doc ? ` [${e.doc}]` : ""}`; line.append(t); }
      eg.append(line); edges.set(e.type ? `${e.s}|${e.t}|${e.type}` : `${e.s}|${e.t}`, line);
    }
    for (const n of g.nodes) {
      const gg = svgEl("g", {class: "n", tabindex: "0"}); gg.dataset.id = n.id;
      const c = svgEl("circle", {cx: n.x, cy: n.y, r: r(n), fill: color(n)});
      const t = svgEl("text", {x: n.x, y: n.y - r(n) - 5, "text-anchor": "middle"}); t.textContent = label(n);
      gg.append(c, t); ng.append(gg); nodes.set(n.id, gg);
    }
    svg.append(eg, ng);
    return {edges, nodes};
  }
  return {$, $$, esc, el, svgEl, api, stream, drawGraph, config: null};
})();

(function lecture() {
  const {$, $$, esc, el, api} = GR;

  /* 목차 */
  const sections = $$("#main > section");
  sections.forEach((s, i) => {
    $("#toc").append(el("li", {}, `<a href="#${s.id}"><span>${String(i).padStart(2, "0")}</span>${esc(s.dataset.title)}</a>`));
    $("#mobileToc").append(el("a", {href: "#" + s.id}, esc(s.dataset.title)));
    if (i > 0) $("#agenda")?.append(el("a", {href: "#" + s.id}, esc(s.dataset.title)));
  });
  const tocLinks = $$("#toc a");
  const spy = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) tocLinks.forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#" + e.target.id));
  }), {rootMargin: "-30% 0px -60% 0px"});
  sections.forEach(s => spy.observe(s));

  /* Part 1: 친구 그래프 BFS */
  (function friends() {
    const P = {"민수": [60, 70], "지영": [190, 46], "현우": [320, 70], "소라": [372, 196], "하늘": [240, 214], "태호": [104, 196]};
    const E = [["민수", "지영"], ["지영", "현우"], ["현우", "소라"], ["민수", "태호"], ["태호", "하늘"], ["하늘", "소라"], ["지영", "태호"]];
    const g = {nodes: Object.entries(P).map(([id, [x, y]]) => ({id, x, y})), edges: E.map(([s, t]) => ({s, t}))};
    const adj = {}; g.nodes.forEach(n => adj[n.id] = []); E.forEach(([a, b]) => { adj[a].push(b); adj[b].push(a); });
    const svg = $("#friendSvg");
    const view = GR.drawGraph(svg, g, {w: 420, h: 250, r: () => 14, color: () => "var(--t2)"});
    let pick = [];
    const edgeOf = (a, b) => view.edges.get(`${a}|${b}`) || view.edges.get(`${b}|${a}`);
    const bfs = (s, t) => {
      const prev = {[s]: null}, q = [s];
      while (q.length) { const u = q.shift(); if (u === t) break; for (const v of adj[u]) if (!(v in prev)) { prev[v] = u; q.push(v); } }
      const path = []; for (let u = t; u != null; u = prev[u]) path.unshift(u); return path;
    };
    const reset = () => {
      pick = []; svg.classList.remove("dim");
      view.nodes.forEach(n => n.classList.remove("keep", "sel", "path")); view.edges.forEach(e => e.classList.remove("on", "near"));
      $("#friendInfo").innerHTML = "<b>출발 노드를 클릭하세요</b><span>노드 위에 마우스를 올리면 이웃(1-hop)이 강조됩니다.</span>";
    };
    const click = id => {
      if (pick.length === 2) reset();
      pick.push(id); view.nodes.get(id).classList.add("sel");
      if (pick.length === 1) { $("#friendInfo").innerHTML = `<b>출발: ${esc(id)}</b><span>이웃(1-hop): ${adj[id].map(esc).join(", ")}</span><span>이제 도착 노드를 클릭하세요.</span>`; return; }
      const path = bfs(pick[0], pick[1]);
      svg.classList.add("dim");
      path.forEach(p => view.nodes.get(p).classList.add("keep", "path"));
      path.slice(1).forEach((p, i) => edgeOf(path[i], p).classList.add("on"));
      $("#friendInfo").innerHTML = `<b>${esc(path.join(" → "))}</b><span>${path.length - 1}-hop 경로입니다. BFS(너비 우선 탐색)는 가까운 노드부터 차례로 넓혀 가며 찾습니다.</span><span style="color:var(--muted)">GraphRAG에서 "A와 B는 어떻게 연결되나?"를 푸는 연산이 바로 이것입니다.</span>`;
    };
    view.nodes.forEach((n, id) => {
      n.addEventListener("click", () => click(id));
      n.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); click(id); } });
      n.addEventListener("mouseenter", () => { if (pick.length < 2) view.edges.forEach((e, k) => e.classList.toggle("near", k.split("|").includes(id))); });
      n.addEventListener("mouseleave", () => { if (pick.length < 2) view.edges.forEach(e => e.classList.remove("near")); });
    });
    $("#friendReset").addEventListener("click", reset);
  })();

  /* 실시간 벤치마크 (강의 화면) */
  (function bench() {
    let k = 5;
    $("#benchK").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; k = +b.dataset.k; $$("#benchK button").forEach(x => x.setAttribute("aria-pressed", x === b)); });
    $("#benchRun").addEventListener("click", async () => {
      const out = $("#benchOut"); out.innerHTML = `<p style="padding:14px;color:var(--muted)">실행 중…</p>`;
      try {
        const t0 = performance.now();
        const r = await api(`/api/benchmark?k=${k}`);
        const cell = (x, best) => `<td class="num" style="${x.recall === best ? "font-weight:700" : ""}">${x.recall.toFixed(2)}</td>`;
        out.innerHTML = `<table><thead><tr><th>질문</th><th>유형</th><th class="num v">vector</th><th class="num g">graph</th><th class="num">hybrid</th></tr></thead><tbody>` +
          r.rows.map(x => { const best = Math.max(x.vector.recall, x.graph.recall, x.hybrid.recall); return `<tr><td>${x.id} <span style="font-weight:400;color:var(--muted)">${esc(x.question)}</span></td><td>${x.type}</td>${cell(x.vector, best)}${cell(x.graph, best)}${cell(x.hybrid, best)}</tr>`; }).join("") +
          `<tr><td><b>평균</b></td><td></td>${["vector", "graph", "hybrid"].map(m => `<td class="num"><b>${r.avg[m].toFixed(2)}</b></td>`).join("")}</tr></tbody></table>` +
          `<p style="padding:8px 14px;font-size:.8rem;color:var(--muted)">임베딩: ${esc(GR.config?.embedding)} · k=${r.k} · ${Math.round(performance.now() - t0)}ms</p>`;
      } catch (e) { out.innerHTML = `<p style="padding:14px;color:var(--warn)">${esc(e.message)}</p>`; }
    });
  })();

  /* 개념 사전 */
  (function concepts() {
    const C = [
      ["기초", "노드 · 엣지 · 트리플", "그래프의 점과 선. 지식그래프에서는 (주어, 관계, 목적어) 트리플 하나가 엣지 하나입니다.", "lab/01_graph_basics.py"],
      ["기초", "속성 그래프 vs RDF", "속성 그래프는 노드·엣지에 속성을 붙이고(Neo4j), RDF는 모든 것을 트리플로 표현합니다(SPARQL).", null],
      ["기초", "스키마 · 온톨로지", "허용되는 노드·관계 타입의 정의. 추출을 일관되게 만들지만 설계 비용이 듭니다.", "lab/extraction.py"],
      ["기초", "경로 · BFS · hop", "엣지를 따라 이동하는 길. 멀티홉 질문은 곧 경로 탐색 문제입니다.", "lab/01_graph_basics.py"],
      ["인덱싱", "엔티티·관계 추출", "LLM이 청크에서 트리플을 뽑습니다. LangChain에서는 with_structured_output + Pydantic 스키마로 구현합니다.", "lab/extraction.py", "extract"],
      ["인덱싱", "엔티티 해소 (Entity Resolution)", "표기가 다른 같은 개체를 하나로 합칩니다. 문자열 정규화 → 임베딩 유사도 → LLM 판정 순으로 정교해집니다.", "lab/extraction.py", "extract"],
      ["인덱싱", "커뮤니티 탐지 (Louvain · Leiden)", "서로 촘촘히 연결된 노드 묶음을 찾습니다. MS GraphRAG는 계층적 Leiden을 씁니다.", "lab/global_search.py", "global"],
      ["인덱싱", "커뮤니티 리포트", "커뮤니티마다 LLM이 미리 쓴 요약. Global Search의 재료이자 인덱싱 비용의 큰 몫입니다.", "data/community_summaries.json", "global"],
      ["검색", "Entity Linking", "질문 속 표현을 그래프 노드에 연결하는 첫 단계. 실습에서는 이름·별칭 문자열 매칭을 씁니다.", "lab/retrievers.py", "graph"],
      ["검색", "Local Search", "시드 엔티티의 이웃·경로·원문을 모아 컨텍스트를 만듭니다.", "lab/04_local_graph_rag.py", "graph"],
      ["검색", "Global Search (Map-Reduce)", "모든 커뮤니티 요약에 질문해 부분 답을 얻고 종합합니다. 전역 질문용입니다.", "lab/05_global_graph_rag.py", "global"],
      ["검색", "DRIFT Search", "Global로 방향을 잡고 후속 질문으로 Local 탐색을 확장하는 MS GraphRAG의 하이브리드 검색입니다.", null],
      ["검색", "Personalized PageRank", "시드 노드에서 출발해 중요도를 퍼뜨리는 알고리즘. HippoRAG의 핵심이며 실습의 문서 순위에 쓰입니다.", "lab/retrievers.py", "graph"],
      ["검색", "경로 기반 검색 (PathRAG)", "시드 엔티티들을 잇는 경로 위 관계를 우선 모읍니다. 인과 연쇄 질문에 강합니다.", "lab/retrievers.py", "graph"],
      ["검색", "Text2Cypher", "LLM이 자연어를 Cypher 쿼리로 바꿔 그래프 DB에서 실행합니다. 집계·필터에 강하지만 보안에 주의해야 합니다.", "lab/07_neo4j_text2cypher.py"],
      ["검색", "하이브리드 검색", "벡터·키워드·그래프 결과를 합칩니다. 실습에서 평균 Recall이 가장 높았습니다.", "lab/06_compare_eval.py", "compare"],
      ["트렌드", "Agentic GraphRAG", "LLM 에이전트가 그래프 탐색 도구를 골라 반복 호출합니다. Think-on-Graph의 실용판입니다.", "lab/graph_tools.py", "agent"],
      ["트렌드", "Temporal KG (Bi-temporal)", "사실마다 유효 기간을 두고, 모순되는 새 사실이 오면 옛 사실을 무효화합니다(Graphiti).", "lab/temporal_kg.py", "temporal"],
      ["트렌드", "LazyGraphRAG", "요약을 미리 만들지 않고 질의 시점에 필요한 만큼만 LLM으로 처리해 인덱싱 비용을 줄입니다.", null],
      ["트렌드", "하이퍼그래프", "셋 이상의 개체를 한 번에 잇는 하이퍼엣지로 n-ary 관계를 표현합니다(HyperGraphRAG).", null],
      ["트렌드", "MCP (Model Context Protocol)", "LLM에 도구와 데이터 소스를 연결하는 표준 프로토콜. 그래프 DB를 에이전트 도구로 노출할 때 씁니다.", null],
      ["트렌드", "Context Engineering", "LLM 컨텍스트에 무엇을 어떤 구조로 넣을지 설계하는 일. GraphRAG를 이 관점의 도구 중 하나로 봅니다.", null],
    ];
    const cats = ["전체", ...new Set(C.map(c => c[0]))];
    let cur = "전체";
    const draw = () => {
      $("#conceptGrid").innerHTML = C.filter(c => cur === "전체" || c[0] === cur).map(([cat, t, d, f, live]) =>
        `<div class="concept"><span class="cat">${cat}</span><h3>${esc(t)}</h3><p>${esc(d)}</p>${f ? `<span class="where">코드: <button type="button" class="filelink" data-file="${f}">${f}</button>${live ? ` · <button type="button" class="filelink live" data-live="${live}">▶ 실험실</button>` : ""}</span>` : ""}</div>`).join("");
      $$("#conceptFilter button").forEach(b => b.setAttribute("aria-pressed", b.dataset.c === cur));
    };
    cats.forEach(c => $("#conceptFilter").append(el("button", {type: "button", "data-c": c, "aria-pressed": "false"}, c)));
    $("#conceptFilter").addEventListener("click", e => { const b = e.target.closest("button"); if (b) { cur = b.dataset.c; draw(); } });
    draw();
  })();

  /* 환경 셋팅 탭 */
  (function setup() {
    const T = [
      ["라이브 실험실 (이 시스템)", `이 발표 시스템 자체입니다. 서버가 lab/ 의 실습 코드를 import 해서 실행하고, 브라우저에서 단계별 중간 결과를 봅니다. API 키가 없어도 검색 단계까지 모두 동작합니다.`,
`<span class="c"># Python 3.10 이상</span>
python -m venv .venv && source .venv/bin/activate     <span class="c"># Windows: .venv\\Scripts\\activate</span>
pip install -r requirements.txt
cp .env.example .env               <span class="c"># LLM_MODEL, API 키 (선택)</span>
python app/server.py               <span class="c"># → http://localhost:8000</span>

<span class="c"># 선택: 무료 로컬 한국어 임베딩 (실험실 상단에서 전환 가능)</span>
pip install langchain-huggingface sentence-transformers`, ["README.md", ".env.example", "requirements.txt", "app/server.py", "app/pipelines.py"]],
      ["실습 스크립트", `같은 코드를 터미널에서 한 단계씩 실행합니다. VS Code/Jupyter에서는 # %% 셀 단위로 실행할 수 있습니다.`,
`cd lab
python 01_graph_basics.py
python 02_vector_rag.py
python 04_local_graph_rag.py
python 06_compare_eval.py

<span class="c"># 선택: 실습 07 Neo4j</span>
docker compose up -d               <span class="c"># http://localhost:7474</span>
python 07_neo4j_text2cypher.py`, ["lab/common.py", "lab/retrievers.py", "docker-compose.yml"]],
      ["Microsoft GraphRAG", `CLI로 인덱싱과 질의를 합니다. 기본 설정은 OpenAI(gpt-4.1, text-embedding-3-large)이며 settings.yaml에서 다른 제공자로 바꿀 수 있습니다. 인덱싱 비용이 크니 작은 문서로 먼저 시험하세요.`,
`pip install graphrag
graphrag init --root ./ragtest                    <span class="c"># settings.yaml, .env, prompts/, input/ 생성</span>
<span class="c">#   (모델을 묻는 질문에 답하거나 -m gpt-4.1 -e text-embedding-3-large 로 지정)</span>
<span class="c"># ./ragtest/.env 에 GRAPHRAG_API_KEY=... 입력, ./ragtest/input/ 에 .txt 문서 복사</span>

graphrag prompt-tune --root ./ragtest             <span class="c"># (선택) 내 데이터·언어에 맞춘 추출 프롬프트 생성</span>
graphrag index --root ./ragtest                   <span class="c"># 추출 → 커뮤니티 → 요약 (시간·비용 소모)</span>

graphrag query --root ./ragtest --method global --query "이 문서들의 핵심 주제는?"
graphrag query --root ./ragtest --method local  --query "벤처캐피탈 접근성이 낮은 이유는?"
<span class="c"># --method: local | global | drift | basic(벡터 RAG)</span>
graphrag update --root ./ragtest                  <span class="c"># 문서 추가 후 증분 갱신</span>`, []],
      ["LightRAG", `가벼운 라이브러리입니다. 비동기 API로 문서를 넣고 5가지 모드로 질의합니다. 웹 UI가 있는 서버 모드도 제공합니다.`,
`pip install lightrag-hku

<span class="c"># quickstart.py</span>
import asyncio
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

async def main():
    rag = LightRAG(working_dir="./rag_storage",
                   llm_model_func=gpt_4o_mini_complete,
                   embedding_func=openai_embed)
    await rag.initialize_storages()
    await rag.ainsert(open("report.txt", encoding="utf-8").read())
    for mode in ["naive", "local", "global", "hybrid", "mix"]:
        print(mode, await rag.aquery("기초연구 지출비중 축소의 영향은?", param=QueryParam(mode=mode)))
    await rag.finalize_storages()

asyncio.run(main())`, []],
      ["Neo4j + LangChain", `운영 환경에서 가장 흔한 조합입니다. 그래프 DB에 적재하고 Cypher 또는 Text2Cypher로 질의합니다. Neo4j 공식 파이썬 패키지 neo4j-graphrag도 있습니다.`,
`docker compose up -d        <span class="c"># 이 실습의 docker-compose.yml (neo4j:5)</span>
pip install langchain-neo4j

from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain.chat_models import init_chat_model

graph = Neo4jGraph(url="bolt://localhost:7687", username="neo4j", password="...")
graph.refresh_schema(); print(graph.schema)

chain = GraphCypherQAChain.from_llm(
    init_chat_model("anthropic:claude-opus-5-5"), graph=graph,
    validate_cypher=True, return_intermediate_steps=True,
    allow_dangerous_requests=True)    <span class="c"># LLM이 만든 쿼리 실행에 동의 → 읽기 전용 계정 권장</span>
chain.invoke({"query": "사회후생을 높이는 정책은?"})`, ["lab/07_neo4j_text2cypher.py", "docker-compose.yml"]],
      ["Graphiti", `시간 인식 지식그래프로 에이전트 메모리를 만듭니다. Neo4j 같은 그래프 DB가 필요하고, 기본 LLM·임베딩은 OpenAI입니다.`,
`pip install graphiti-core

import asyncio
from datetime import datetime, timezone
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

async def main():
    g = Graphiti("bolt://localhost:7687", "neo4j", "...")
    await g.build_indices_and_constraints()
    await g.add_episode(name="doc03", episode_body="2022년 우리나라 R&D 지출은 GDP 대비 5.2%이다.",
                        source=EpisodeType.text, source_description="한국은행 보고서",
                        reference_time=datetime(2022, 1, 1, tzinfo=timezone.utc))
    for edge in await g.search("우리나라 R&D 지출 비중은?"):
        print(edge.fact, edge.valid_at, edge.invalid_at)   <span class="c"># 사실 + 유효 기간</span>
    await g.close()

asyncio.run(main())`, ["lab/temporal_kg.py"]],
    ];
    T.forEach(([name, desc, code, files], i) => {
      $("#setupTabs").append(el("button", {type: "button", role: "tab", id: "tab" + i, "aria-selected": String(i === 0), "aria-controls": "tp" + i}, esc(name)));
      const p = el("div", {class: "tabpanel", role: "tabpanel", id: "tp" + i, "aria-labelledby": "tab" + i});
      p.hidden = i !== 0;
      p.innerHTML = `<p style="max-width:74ch">${esc(desc)}</p><pre class="cmd">${code}</pre>` +
        (files.length ? `<p style="font-size:.86rem">관련 파일: ${files.map(f => `<button type="button" class="filelink" data-file="${f}">${f}</button>`).join(" · ")}</p>` : "");
      $("#setupPanels").append(p);
    });
    $("#setupTabs").addEventListener("click", e => {
      const b = e.target.closest("[role=tab]"); if (!b) return;
      $$("#setupTabs [role=tab]").forEach(t => { const on = t === b; t.setAttribute("aria-selected", on); $("#" + t.getAttribute("aria-controls")).hidden = !on; });
    });
  })();

  /* 실습 카드 */
  (function labs() {
    const L = [
      ["lab/00_prepare_pdf.py", "PDF → 실습 문서", "PyPDFLoader로 보고서 로드, 잡음 정제, 문단 번호 기준 19개 문서로 분할", true, false, "ingest"],
      ["app/server.py", "라이브 실험실 서버", "FastAPI. 실습 코드를 실행하고 단계별 결과·LLM 스트리밍을 제공", true, false, "vector"],
      ["app/pipelines.py", "단계 추적기", "각 파이프라인을 단계로 쪼개 입력·출력·시간을 기록", true],
      ["lab/01_graph_basics.py", "그래프 기초", "노드·엣지, 최단 경로, PageRank, Personalized PageRank, 커뮤니티", true],
      ["lab/02_vector_rag.py", "기본 벡터 RAG", "LCEL 체인으로 검색 → 답변. 멀티홉에서 어떤 문서를 놓치는지 확인", false, false, "vector"],
      ["lab/03_build_graph.py", "LLM으로 그래프 만들기", "Pydantic 구조화 출력으로 트리플 추출, 엔티티 해소, kg_extracted.json 저장", false, true, "extract"],
      ["lab/04_local_graph_rag.py", "Local Search", "엔티티 연결 → 경로·이웃 확장 → PPR 순위 → 트리플+원문 컨텍스트", false, false, "graph"],
      ["lab/05_global_graph_rag.py", "Global Search", "Louvain 커뮤니티 → 요약 리포트 → Map-Reduce 답변", false, false, "global"],
      ["lab/06_compare_eval.py", "검색 성능 비교", "벡터 vs 그래프 vs 하이브리드 Recall@k", true, false, "compare"],
      ["lab/07_neo4j_text2cypher.py", "Neo4j · Text2Cypher", "그래프 DB 적재, Cypher 경로 질의, GraphCypherQAChain (Docker 필요)", false],
      ["lab/08_agentic_graph_rag.py", "Agentic GraphRAG", "create_agent + 그래프 탐색 도구 4개. 에이전트가 경로를 스스로 찾음", false, true, "agent"],
      ["lab/09_temporal_memory.py", "시간 인식 메모리", "유효 기간이 있는 사실, 무효화, 시점별 질의 (Graphiti 개념)", true, false, "temporal"],
      ["lab/retrievers.py", "검색기 3종", "vector / graph / hybrid 검색과 단계별 상세 결과", true],
    ];
    $("#labCards").innerHTML = L.map(([f, t, d, free, need, live]) =>
      `<div class="lab"><button type="button" class="filelink fn" data-file="${f}">${f}</button><b>${t}</b><p>${d}</p><span>${free ? `<span class="pill free">키 없이 실행</span>` : need ? `<span class="pill need">LLM 필요</span>` : `<span class="pill">LLM 선택</span>`}${live ? ` <button type="button" class="filelink live" data-live="${live}">▶ 실험실</button>` : ""}</span></div>`).join("");
    const D = [
      ["data/source/bok_2024_05_innovation_growth.pdf", "원본 PDF", "한국은행 「혁신과 경제성장」 49쪽 (코드 뷰어에서는 열리지 않음)"],
      ["data/docs/doc09_저업력_중소기업_자금조달_어려움과_신생기업_.md", "주제별 문서 19개", "문단 번호·BOX 기준으로 나눈 문서. 각 문서에 출처(문단·쪽) 표기"],
      ["data/kg.json", "지식그래프", "노드 45개, 관계 60개. 모든 관계에 출처 문서 id"],
      ["data/questions.json", "평가 질문 8개", "단일 사실 2, 멀티홉 5, 전역 1 + 정답과 사실별 근거 그룹"],
      ["data/community_summaries.json", "커뮤니티 리포트", "Global Search용 리포트 7개 (보고서 수치로 작성)"],
    ];
    $("#dataCards").innerHTML = D.map(([f, t, d]) => f.endsWith(".pdf")
      ? `<a class="lab" href="/api/pdf" target="_blank" rel="noopener" style="text-decoration:none;color:inherit"><span class="fn">${f}</span><b>${t}</b><p>${d.replace(" (코드 뷰어에서는 열리지 않음)", " · 누르면 새 탭에서 열림")}</p></a>`
      : `<button type="button" class="lab" data-file="${f}"><span class="fn">${f}</span><b>${t}</b><p>${d}</p></button>`).join("");
  })();

  /* 발표 모드 (강의 화면) */
  (function present() {
    let idx = 0;
    const show = i => {
      idx = Math.max(0, Math.min(sections.length - 1, i));
      sections.forEach((s, j) => s.classList.toggle("active", j === idx));
      $("#pcount").textContent = `${idx + 1} / ${sections.length}`;
      window.scrollTo(0, 0);
    };
    const enter = () => {
      const y = window.scrollY + 120; let cur = 0;
      sections.forEach((s, i) => { if (s.offsetTop <= y) cur = i; });
      document.body.classList.add("present"); $("#presentBtn").textContent = "읽기 모드"; show(cur);
    };
    const exit = () => { const s = sections[idx]; document.body.classList.remove("present"); $("#presentBtn").textContent = "발표 모드"; s.scrollIntoView(); };
    GR.exitPresent = () => { if (document.body.classList.contains("present")) exit(); };
    $("#presentBtn").addEventListener("click", () => document.body.classList.contains("present") ? exit() : enter());
    $("#exitBtn").addEventListener("click", exit);
    $("#prevBtn").addEventListener("click", () => show(idx - 1));
    $("#nextBtn").addEventListener("click", () => show(idx + 1));
    document.addEventListener("keydown", e => {
      if (!document.body.classList.contains("present") || !$("#drawer").hidden || document.body.classList.contains("in-lab") || e.repeat) return;
      if (/input|textarea|select/i.test(e.target.tagName)) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); show(idx + 1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); show(idx - 1); }
      else if (e.key === "Escape") exit();
    });
    document.addEventListener("click", e => {
      const a = e.target.closest('a[href^="#"]'); if (!a || !document.body.classList.contains("present")) return;
      const i = sections.findIndex(s => "#" + s.id === a.getAttribute("href")); if (i >= 0) { e.preventDefault(); show(i); }
    });
  })();

  /* 글자 크게 (프로젝터용) */
  $("#zoomBtn").addEventListener("click", () => {
    const on = document.documentElement.classList.toggle("zoom");
    try { localStorage.setItem("gr-zoom", on ? "1" : ""); } catch (e) {}
  });
  try { if (localStorage.getItem("gr-zoom")) document.documentElement.classList.add("zoom"); } catch (e) {}
})();

/* 코드·데이터 뷰어 (서버에서 실제 파일을 읽어 옴) */
(function files() {
  const {$, $$, esc, el, api} = GR;
  const LANG = {py: "python", json: "json", md: "markdown", yml: "yaml", txt: "plaintext", example: "ini", html: "xml", css: "css", js: "javascript"};
  const cache = {};
  let current = null, lastFocus = null, treeLoaded = false;
  async function loadTree() {
    if (treeLoaded) return; treeLoaded = true;
    const list = await api("/api/files");
    const groups = [["설정", f => !f.includes("/")], ["실습 코드", f => f.startsWith("lab/")], ["라이브 실험실", f => f.startsWith("app/")],
      ["문서", f => f.startsWith("data/docs/")], ["데이터", f => f.startsWith("data/") && !f.startsWith("data/docs/")]];
    for (const [g, pred] of groups) {
      const fs = list.filter(pred); if (!fs.length) continue;
      $("#tree").append(el("h4", {}, g));
      fs.forEach(f => $("#tree").append(el("button", {type: "button", "data-open": f, title: f}, esc(f.replace(/^(lab|app|data)\//, "")))));
    }
  }
  GR.openFile = async function (f, range) {
    if ($("#drawer").hidden) lastFocus = document.activeElement;
    $("#drawer").hidden = false;
    loadTree().then(() => $$("#tree button").forEach(b => b.setAttribute("aria-current", b.dataset.open === f)));
    $("#fpath").textContent = f + (range ? `  (${range.start}–${range.end}행)` : "");
    try { cache[f] ??= (await api(`/api/file?path=${encodeURIComponent(f)}`)).content; }
    catch (e) { $("#code").textContent = e.message; return; }
    current = f;
    const src = cache[f], lang = LANG[f.split(".").pop()] || "plaintext";
    let html = esc(src);
    try { if (window.hljs && lang !== "plaintext") html = hljs.highlight(src, {language: lang, ignoreIllegals: true}).value; } catch (e) {}
    $("#code").innerHTML = html;
    const n = src.split("\n").length;
    $("#gutter").textContent = Array.from({length: n}, (_, i) => i + 1).join("\n");
    $$("#tree button").forEach(b => b.setAttribute("aria-current", b.dataset.open === f));
    const viewer = $("#viewer"), band = $("#band");
    requestAnimationFrame(() => {
      if (range) {
        const gut = $("#gutter"), lh = (gut.scrollHeight - 28) / n, top = 14 + (range.start - 1) * lh;
        band.style.top = top + "px"; band.style.height = (range.end - range.start + 1) * lh + "px"; band.hidden = false;
        viewer.scrollTop = Math.max(0, top - 80);
      } else { band.hidden = true; viewer.scrollTop = 0; }
    });
    $("#closeBtn").focus();
  };
  GR.openCode = async (file, symbol) => {
    try { const r = await api(`/api/coderef?file=${encodeURIComponent(file)}&symbol=${encodeURIComponent(symbol)}`); GR.openFile(file, r); }
    catch (e) { GR.openFile(file); }
  };
  const close = () => { $("#drawer").hidden = true; lastFocus?.focus?.(); };
  $("#tree").addEventListener("click", e => { const b = e.target.closest("[data-open]"); if (b) GR.openFile(b.dataset.open); });
  $("#closeBtn").addEventListener("click", close);
  $("#drawer").addEventListener("click", e => { if (e.target.id === "drawer") close(); });
  $("#openFiles").addEventListener("click", () => GR.openFile(current || "README.md"));
  $("#copyBtn").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(cache[current]); $("#copyBtn").textContent = "복사됨"; }
    catch (e) { const r = document.createRange(); r.selectNodeContents($("#code")); getSelection().removeAllRanges(); getSelection().addRange(r); $("#copyBtn").textContent = "선택됨"; }
    setTimeout(() => $("#copyBtn").textContent = "복사", 1500);
  });
  document.addEventListener("click", e => {
    const c = e.target.closest("[data-code]"); if (c) { const [f, s] = c.dataset.code.split("#"); GR.openCode(f, s); return; }
    const f = e.target.closest("[data-file]"); if (f) { GR.openFile(f.dataset.file); return; }
    const d = e.target.closest("[data-doc]"); if (d) { const doc = GR.config?.docs.find(x => x.id === d.dataset.doc); if (doc) GR.openFile(doc.file); }
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#drawer").hidden) { e.stopPropagation(); close(); } }, true);
})();
