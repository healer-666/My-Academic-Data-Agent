# Academic Data Agent — 架构图生图提示词

> 以下 7 段提示词供 DALL-E / Midjourney / Stable Diffusion 等生图大模型使用。
> 每段对应一张架构图，英文为主以获得最佳生图效果，中文注释供理解。

---

## Prompt 1 — 总体六层架构

```
Create a clean, professional system architecture diagram on a dark navy background (#0F172A to #1E293B gradient). The diagram shows a 6-layer vertical stack architecture for an "Academic Data Agent" system. Title at top: "Academic Data Agent — Overall Architecture" in white, with subtitle "Neuro-Symbolic LLM Agent for Reliable Statistical Data Analysis" in gray.

Layer 1 (blue accent #3B82F6): "Input Layer / Data Context" — contains 4 connected boxes: "main.py / Gradio Web", "document_ingestion", "data_context", "config / .env", "RuntimeConfig". Connected left-to-right with blue arrows.

Layer 2 (purple accent #8B5CF6): "Retrieval Layer / Memory System" — contains 4 boxes: "RAG Service (ChromaDB + Keywords)", "Success / Failure Memory", "KnowledgeContextProvider", "Evidence Register". Connected with gray arrows.

Layer 3 (amber accent #F59E0B): "Analysis Execution Layer" — contains 5 boxes in a row: "LLM Reasoning (DeepSeek V4 Flash)", "JSON Protocol", "PythonInterpreterTool", "TavilySearchTool", "prompts.py". A curved ReAct loop arrow cycles back from prompts to LLM. Label: "ReAct loop (max 6 steps)".

Layer 4 (green accent #10B981): "Governance / Audit Layer" — contains 5 boxes: "execution_audit (AST)", "report_contract (7-section check)", "symbolic_rules (9 rules)", "review_service", "vision_review".

Layer 5 (red accent #EF4444): "Harness / Regression Layer" — contains 5 boxes: "eval/run_eval (10 tasks)", "compare_baseline", "symbolic_ablation", "failure_taxonomy", "regression_rules".

Layer 6 (cyan accent #06B6D4): "Presentation / QA Layer" — contains 5 boxes: "Gradio Web Workbench", "CLI (Rich terminal)", "history_qa", "presentation rendering", "artifact_service".

A floating box on the right side labeled "Core Orchestrator / agent_runner.py". Dashed vertical lines connect layers. Each layer has a colored left-border stripe. Legend at bottom: blue=LLM, green=Symbolic Rule, purple=Data Store, amber=Tool/Executor.

Style: modern tech diagram, flat design, rounded corners, subtle glow effects, no 3D, suitable for presentation slides.
```

---

## Prompt 2 — 主执行流水线 (10 阶段)

```
Create a vertical pipeline flowchart on a dark navy background (#0F172A to #1E293B). Title: "Main Execution Pipeline — 10 Stages" with subtitle "run_analysis() complete orchestration".

A central dashed vertical line runs from top to bottom. Along this line, numbered circles (1-10) mark each stage, connected by downward gray arrows. Each stage has a description text to the right and a module reference box on the far right.

Stage 1 (blue circle): "Config Loading" — load_runtime_config(), modules: config.py, model_registry.py
Stage 2 (blue circle): "Data Context" — ingest_input_document() → build_data_context(), modules: document_ingestion.py, data_context.py
Stage 3 (purple circle): "Memory Retrieval" — SuccessMemory + FailureMemory, modules: memory/service.py, memory/extractor.py
Stage 4 (purple circle): "RAG Retrieval" — hybrid dense + keyword → rerank → evidence register, modules: rag/service.py, rag/reranker.py
Stage 5 (purple circle): "Knowledge Assembly" — KnowledgeContextProvider.collect(), module: knowledge_context.py
Stage 6 (amber box, not a circle): "ReAct Analysis Loop" — contains 3 sub-steps: 6a LLM reasoning (JSON output), 6b Tool execution (Python/Tavily), 6c Observation feedback. A curved dashed amber arrow loops back. Label: "cycle (max 6 steps)". On the right: "finish → parse output" with extract_report_and_telemetry(), analyze_evidence_coverage(), save_agent_trace().
Stage 7 (green circle): "Execution Audit (AST)" — verify Stage1 saves cleaned_data.csv, Stage2 reloads, module: execution_audit.py
Stage 8 (green circle): "Report Contract Check" — 7 required sections + figure interpretation + effect size/CI + causal language + citation verification, modules: report_contract.py, symbolic_rules.py
Stage 9 (red box): "Review Loop" — contains: 9 review submission, 9v visual review (optional). Quality modes: draft=0, standard=1, publication=2+visual. Modules: review_service.py, vision_review.py. A red dashed arrow loops rejection back to Stage 6.
Stage 10 (purple circle): "Memory Writeback" — success → SuccessMemory, failure → FailureMemory.

Bottom-right: "AnalysisRunResult" output box in cyan.

Style: clean pipeline visualization, numbered stages, color-coded by subsystem, suitable for technical presentation.
```

---

## Prompt 3 — Neuro-Symbolic 治理架构

```
Create a split-view architecture diagram on dark navy background. Title: "Neuro-Symbolic Governance Architecture" with subtitle "9 symbolic rules + AST audit + report contract + 3 ablation profiles".

Left side (blue border #3B82F6): "Neural (Neural Side)" — subtitle: "semantic understanding, reasoning, text generation". Contains:
- "DeepSeek V4 Flash (Primary LLM)" — JSON structured output, ReAct reasoning, report writing, data analysis, thinking-disabled mode
- "Vision LLM (Configurable Visual Review)" — chart quality review, label readability, axis checks
- "Prompt Engineering (prompts.py)" — build_system_prompt(), academic guardrails, report contract checklist, drawing protocol, symbolic rules injection
- "Knowledge Context Assembly" — user intent + success/failure memory + RAG citations + evidence register
- Two tool boxes side by side: "PythonInterpreterTool (exec() sandbox)" and "TavilySearchTool (domain search)"
- "JSON Structured Protocol" — {decision, action, tool_name, tool_input, final_answer}

Center: vertical dashed divider line with a "Constraints" label badge.

Right side (green border #10B981): "Symbolic (Symbolic Side)" — subtitle: "rule validation, AST audit, contract checks, blocking & repair". Contains 3 rule category boxes:

1. "Execution Audit Rules (3 rules)" — stage.save_cleaned_data, stage.reload_cleaned_data, stage.no_raw_reuse. Implementation: execution_audit.py, AST syntax tree analysis, _PathAuditVisitor, severity: blocking.

2. "Report Contract Rules (4 rules)" — report.required_sections (7 sections), report.figure_interpretation, report.statistical_reporting (effect size/CI), report.non_causal_language. Implementation: report_contract.py, regex detection, severity: blocking.

3. "Evidence & Task Alignment Rules (2 rules)" — evidence.valid_citations, task.data_structure_alignment. Severity: blocking/warning.

Below rules: "Ablation Profiles (Symbolic Profiles)" with 3 boxes:
- "full" (green): prompt + checker + blocking
- "prompt_only" (amber): prompt-only constraints (soft)
- "none" (red): JSON/tool protocol only

Bottom: "SymbolicRule data structure" showing: rule_id | category | description | severity | prompt_text | checker_name | failure_message | repair_hint.

Green arrows flow from center divider to each rule category. Style: balanced split layout, professional, presentation-ready.
```

---

## Prompt 4 — RAG 检索子系统

```
Create a data flow diagram on dark navy background. Title: "RAG Retrieval Subsystem" with subtitle "ChromaDB vector retrieval + keyword retrieval → hybrid reranking → evidence register".

Phase 1 (purple accent, top section): "Phase 1 — Document Ingestion & Indexing". A horizontal pipeline of 5 boxes connected by purple arrows:
1. "User Upload File" (.txt / .md / .pdf)
2. "document_reader" — loading, segmentation, chunking (overlap)
3. "embeddings" — OpenAI Embedding Client
4. "vector_store" — ChromaDB PersistentClient, dense vector storage
5. "keyword_index" — JSON TF-IDF index, fallback when no embedding

A dashed arrow also branches from embeddings to keyword_index.

Phase 2 (purple accent, middle section): "Phase 2 — Retrieval & Reranking". Contains:
- "query_builder" — build_retrieval_queries(), dense + keyword query bundles
- "Dense Vector Retrieval" — ChromaDB query → cosine similarity, embedding dimension matching
- "Keyword Retrieval" — TF-IDF keyword scoring, standalone when no embedding
- "reranker (Hybrid Reranking)" — dense × 1.6 + keyword × 0.35 + query/column/header match + knowledge type weight + source penalty

Arrows: query_builder splits to both dense and keyword, both feed into reranker.

Phase 3 (green accent, bottom section): "Output — RagRetrievalResult" with 3 output boxes: RetrievedChunk[], Evidence Register, Citation Labels. Labels show: evidence_id, citation_label [REF-X], source_locator, score, chunk_text.

Bottom-left panel: "Hybrid Retrieval Strategy" explaining dense path (document → embedding → ChromaDB → cosine Top-K), keyword path (document → TF-IDF → JSON index → keyword scoring), and reranking formula. Degrade note: "No embedding API → keyword-only mode".

Bottom-right panel: "Module Map (rag/ subpackage)" listing all modules: rag/service.py, rag/models.py, rag/document_reader.py, rag/embeddings.py, rag/vector_store.py, rag/keyword_index.py, rag/reranker.py, rag/query_builder.py, and external callers: agent_runner.py, knowledge_context.py, reporting.py, history_qa.py.

Style: clear data flow, phased layout, color-coded phases, presentation-quality.
```

---

## Prompt 5 — 记忆子系统 (三层记忆)

```
Create a three-column architecture diagram on dark navy background. Title: "Memory Subsystem Architecture" with subtitle "Three-layer memory: Success Experience · Failure Lessons · External Knowledge (RAG)".

Three equal columns, each with a tall rounded rectangle:

Column 1 (green #10B981 border): "Success Experience Memory" / "SuccessMemoryService". Contains 4 blocks:
- Write Flow: analysis complete → extract_memory_records() → rule extraction + LLM distillation → ChromaDB write
- Read Flow: new task → vector similarity search → Top-K experience records → inject into prompt context
- Data Model: MemoryRecord with fields: task_type, methods_used, key_findings, success_patterns, confidence_score, scope_key
- Purpose (italic, gray): "Guide method selection" — example: "Last time similar data used paired t-test, worked well"

Column 2 (red #EF4444 border): "Failure Lesson Memory" / "FailureMemoryService". Contains 4 blocks:
- Write Flow: analysis failed → extract_failure_memory_records() → error pattern extraction → ChromaDB write
- Read Flow: new task → vector similarity search → negative constraint records → inject as "don't do this"
- Data Model: FailureMemoryRecord with fields: error_type, failure_mode, prevention_hint, affected_rule, scope_key
- Purpose (italic, gray): "Avoid repeating mistakes" — example: "Last time forgot normality check for paired test → verify first this time"

Column 3 (purple #8B5CF6 border): "External Knowledge Memory" / "RAG Service (ChromaDB)". Contains 4 blocks:
- Indexing Flow: upload file → document_reader → vector + keyword dual indexing
- Retrieval Flow: data_context → query_builder → hybrid retrieval → reranker → evidence register
- Data Model: RetrievedChunk with fields: evidence_id, citation_label [REF-X], source_locator, score, chunk_text
- Purpose (italic, gray): "Domain knowledge support" — example: "Reference guide suggests Kruskal-Wallis [REF-1]"

Below columns: "Knowledge Context Assembly — KnowledgeContextProvider.collect()" banner (blue #3B82F6). Contains 5 input boxes: Success Memory ("recommended methods..."), Failure Memory ("avoid..."), RAG Citations ("[REF-1]...[REF-2]..."), User Query (raw analysis request), Evidence Register (Citation Label mapping).

Color-matched arrows from each column down to the assembly: green from success, red from failure, purple from RAG.

Output section (amber): "→ Inject into build_system_prompt() → ReAct loop context" — three memories merged as prompt context.

Bottom-left panel: "Scope Isolation" — derive_memory_scope_key() with 3 scope types: explicit scope, session scope, filename scope.

Bottom-right panel: "Storage Backend" listing ChromaDB modules and memory service modules.

Style: symmetric three-column layout, clear data flow, presentation-ready.
```

---

## Prompt 6 — 审稿循环与质量模式

```
Create a flowchart diagram on dark navy background. Title: "Review Loop & Quality Modes" with subtitle "Independent reviewer + multi-round revision + visual review + 3-tier quality modes".

Section 1 (green accent): "Pre-review Gates (Procedural Blocking)". Two side-by-side gate boxes:
- Gate 1: "Execution Audit (execution_audit)" — AST analysis of Python steps → verify two-stage data protocol (save → reload) → auto-reject if failed
- Gate 2: "Report Contract (report_contract)" — 7 required sections + figure interpretation + effect size/CI + causal language + citations → attach revision_brief if failed
Green arrow connecting Gate 1 → Gate 2.

Section 2 (red accent): "Review Loop". A horizontal flow:
1. Blue box: "Analyst Submits" (report + charts + telemetry)
2. Red box: "build_reviewer_task()" — data context + step tracking + audit results + evidence + memory
3. Red box: "Reviewer LLM" — build_reviewer_prompt(), standard/publication checklist, parse_reviewer_reply()
4. Diamond decision: "Accept?"
5. Green box (accept path): "ACCEPT → Continue"
6. Red box (reject path): "REJECT → build_revision_brief()" — revision points → analyst re-analyzes
7. Red dashed curved arrow loops from reject back to analyst submission, labeled "Revision Loop"

Gray arrows connect the linear flow. Green arrow from diamond to accept box.

Below review loop: purple box "Optional: Visual Review (vision_review) — enabled in publication mode when a vision model is configured"

Section 3: "Quality Mode Configuration" with 3 side-by-side comparison boxes:
- "draft" (gray): 0 review rounds, visual review off, for quick exploration/data preview, skips reviewer but keeps artifact validation
- "standard" (blue): 1 review round, visual review off, for daily analysis/teaching, max 1 revision if rejected
- "publication" (amber): 2 review rounds, visual review enabled when configured, for paper submission/formal reports, 2 review rounds + chart quality visual audit

Section 4 (purple accent): "Visual Review Flow (Vision Review)". 4 boxes in a row with purple arrows:
1. "select_visual_review_candidates()" — filter by review round, prioritize new/cited charts
2. "prepare_image_for_vision()" — resize → JPEG → base64 encoding
3. "Vision LLM Review" — check: label readability, axes, color contrast, legend clarity
4. "VisualReviewResult" — findings[] problem list, severity: critical/warning/info

Style: clear flow with decision diamond, side-by-side mode comparison, professional presentation layout.
```

---

## Prompt 7 — 评测框架与消融实验

```
Create a data-rich evaluation framework diagram on dark navy background. Title: "Evaluation Framework & Ablation Experiments" with subtitle "10-task baseline evaluation → regression detection → symbolic ablation → failure taxonomy".

Left section: "10 Evaluation Tasks (eval/tasks/*.yaml)" — a table with 4 columns (Task, Scenario, Special, Typical Failure Mode) and 10 rows:
1. before_after_paired_measure | Paired pre/post biomarkers | — | review_rejection
2. two_group_small_sample | Small sample group comparison | — | review_rejection
3. multi_group_with_variance_shift | 3-group dose comparison | — | figure_interpretation_failure
4. missing_values_by_group | Group missing value analysis | — | cleaning_contract_failure
5. time_series_trend_clean | Time series trends | — | figure_interpretation_failure
6. outlier_sensitive_measurement | Outlier detection | — | figure_interpretation_failure
7. mixed_units_and_dirty_headers | Dirty data/mixed units | — | cleaning_contract_failure
8. correlation_without_causality | Correlation analysis | — | review_rejection
9. reference_guideline_lookup | RAG-guided interpretation | RAG | citation_evidence_failure
10. memory_constrained_repeat_task | Memory-constrained repeat | Memory | review_rejection

Footer: "All tasks share 6 key_checks: workflow_complete · cleaned_data · execution_audit · report · trace · charts" (amber highlight).

Right section: "Evaluation Pipeline" (red accent). Vertical flow of 5 boxes:
1. "run_eval.py — run 10 tasks in fixed order"
2. "per-task summary → aggregate eval run report"
3. "baseline snapshot: seed_v5 (10/10 accepted)" (green box)
4. "compare_baseline.py — regression detection"
5. "Regression Thresholds (regression_rules.json)" — accept_rate ≤ -5%, workflow ≤ -5%, audit_pass ≤ -1%, steps ≤ +2.0

Below pipeline: "Failure Taxonomy (failure_taxonomy)" box listing categories: cleaning_contract_failure, artifact_contract_failure, citation_evidence_failure, report_structure_failure, figure_interpretation_failure, review_rejection.

Middle section (purple accent): "Symbolic Ablation Experiment". Three large side-by-side profile boxes:
- "full" (green): prompt injection + checker execution + blocking. 9 rules all active. Baseline: seed_v5 (10/10 accepted). Strongest constraint, highest reliability.
- "prompt_only" (amber): prompt injection only (soft constraint). Rule text in prompt, no checker. Relies on LLM self-discipline. Tests "is prompt alone sufficient?"
- "none" (red): JSON/tool protocol only, no symbolic rules. Minimal system prompt. Pure LLM free-form. Control group: quantify symbolic rules' incremental contribution.

Bottom section: "Ablation Analysis Flow". 5 connected boxes with arrows:
1. "run_symbolic_ablation.py"
2. "Task × Config matrix traversal"
3. "build_paired_comparisons()"
4. "determine_evidence_level()"
5. "Ablation Report (Markdown + JSON)" (green box)

Evidence level badges: "strong" (green), "partial" (amber), "weak" (red).

Analysis notes: "full vs prompt_only: pass rate difference → checker's incremental contribution", "full vs none: pass rate difference → entire symbolic governance's incremental contribution".

Style: dense information layout, table + flowchart + comparison panels, professional evaluation dashboard aesthetic.
```
