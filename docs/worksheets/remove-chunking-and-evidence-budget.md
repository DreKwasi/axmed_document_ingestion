# Worksheet: Remove Chunking and Evidence Volume Budget

## Context & User Requirements
- The user requested removing artificial character budgets and chunking restrictions from evidence processing.
- Instead of slicing documents into micro-chunks and forcing models into iterative chunk retrieval loops, the agent receives the complete document context directly in the user message.
- LangChain Google Gemini is configured via `init_chat_model` (`google_genai:gemini-3.5-flash-lite`) as the sole semantic provider.

## Key Changes
1. **`backend/app/extraction/evidence_workspace.py`**:
   - Replaced `EvidenceChunk` and chunk-splitting logic (`RecursiveCharacterTextSplitter`, `_json_chunks`, `_page_chunks`, `_text_chunks`) with intact `EvidenceItem` document sections.
   - Removed backward compatibility alias `EvidenceChunk = EvidenceItem`, `@property def chunks`, and redundant `chunks` atlas keys.
   - `EvidenceWorkspace` always operates in `mode="whole_source"`.
   - Enhanced `_resolve` to resolve document references and offset slices cleanly without false positives.
2. **`backend/app/extraction/semantic_agent.py`**:
   - Removed evidence-volume budget blocking from `_inspect_items`; character volume is tracked for telemetry without failing executions.
   - `_source_message` always includes the full `request.context` directly.
   - Configured `create_agent` with `ToolStrategy(SemanticCandidate)` for structured output compatibility with Gemini tool calling.
3. **`backend/app/extraction/llm.py`**:
   - Uses `init_chat_model(f"google_genai:{settings.gemini_model}", api_key=settings.gemini_api_key, timeout=...)`.
4. **Validation**:
   - Updated tests in `test_semantic_agent.py` and `test_evidence_workspace.py`.
   - `bin/agent-validate targeted` passed cleanly (0 frontend lint warnings, 32 frontend unit tests passed, Ruff passed, Mypy passed 29 files, 124 backend unit tests passed).
