"""Content-agent helpers for the agent-driven app workflow v3."""

from __future__ import annotations

import json
import queue
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from agent.content_ingestion import DocumentBundle, ingest_documents

try:
    from agent.prompt_store import get_prompt_template
except Exception:  # pragma: no cover
    get_prompt_template = None


InputQueue = Any
UiCallback = Optional[Callable[..., None]]


@dataclass
class ContentUnderstanding:
    """Traceable content-agent output."""

    understanding_markdown: str
    additional_context_block: str
    document_count: int = 0
    warnings: list[str] | None = None


class ContentAgent:
    """Small terminal/UI-compatible content agent for V3.

    This first implementation keeps the orchestration deterministic. It can be
    backed by richer LLM/tool-calling behavior later while preserving the same
    public output: an approved context block passed to grouped workflow tools.
    """

    def __init__(
        self,
        session_root: str | Path,
        assembly_name: str,
        *,
        input_queue: InputQueue = None,
        ui_callback: UiCallback = None,
        max_context_chars: int = 12000,
    ) -> None:
        self.session_root = Path(session_root)
        self.assembly_name = assembly_name
        self.input_queue = input_queue
        self.ui_callback = ui_callback
        self.max_context_chars = max_context_chars
        self.agent_txt_dir = self.session_root / "Agent_txt_files"
        self.agent_txt_dir.mkdir(parents=True, exist_ok=True)

    def ingest_documents(self, document_paths: list[str | Path]) -> DocumentBundle:
        output_dir = self.agent_txt_dir / "ingested_documents"
        bundle = ingest_documents(document_paths, output_dir=output_dir)
        summary_path = output_dir / "_combined_ingested_documents.md"
        summary_path.write_text(bundle.combined_markdown, encoding="utf-8")
        return bundle

    def summarize_documents_with_llm(
        self,
        bundle: Optional[DocumentBundle],
        *,
        user_notes: str = "",
        max_chars: int = 32000,
        prompt_id: str = "readadditional_data_tool_v1",
    ) -> str:
        """LLM-backed implementation of Readadditional_Data_tool.

        The raw ingested documents may be much larger than the dialogue agent's
        useful context. This method compresses them into a manufacturing-focused
        summary that can be safely passed back to the conversational agent.
        """
        if not bundle or not bundle.documents:
            summary = "No additional documents were provided."
            self._save_document_summary(summary)
            return summary

        raw = bundle.combined_markdown.strip()
        if len(raw) > max_chars:
            raw = raw[:max_chars] + "\n\n[Raw ingested document text truncated before LLM summary.]"

        system_prompt = _load_required_prompt(prompt_id)

        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from agent.tools import _get_img_describer_llm

            llm = _get_img_describer_llm(max_completion_tokens=3000)
            messages = [
                SystemMessage(
                    content=system_prompt
                ),
                HumanMessage(
                    content=(
                        f"Assembly: {self.assembly_name}\n\n"
                        f"User notes:\n{user_notes or '(none)'}\n\n"
                        "Ingested documents:\n\n"
                        f"{raw}"
                    )
                ),
            ]
            response = llm.invoke(messages)
            summary = str(getattr(response, "content", response)).strip()
        except Exception as exc:
            summary = (
                "LLM document summary failed. Falling back to deterministic excerpts.\n\n"
                f"Error: {exc}\n\n"
                f"{self._summarize_documents(bundle)}"
            )

        self._save_document_summary(summary)
        return summary

    def build_understanding(
        self,
        *,
        bundle: Optional[DocumentBundle] = None,
        user_notes: str = "",
        corrections: str = "",
        assembly_analysis_summary: str = "",
        sequence_summary: str = "",
    ) -> ContentUnderstanding:
        warnings = list(bundle.warnings if bundle else [])
        document_sections = self._summarize_documents(bundle) if bundle else "No additional documents were provided."

        understanding = f"""# Content Agent Understanding

## Assembly

- Assembly name: `{self.assembly_name}`

## User Notes

{user_notes.strip() or "No manual user notes provided."}

## Uploaded Document Understanding

{document_sections}

## Assembly Analysis Feedback

{assembly_analysis_summary.strip() or "No assembly analysis feedback has been added yet."}

## Sequence Feedback

{sequence_summary.strip() or "No sequence feedback has been added yet."}

## User Corrections / Confirmed Additions

{corrections.strip() or "No corrections provided yet."}

## Ingestion Warnings

{self._format_warnings(warnings)}
"""

        context_block = f"""## User Provided Assembly Context

### User Intent
Use the following context as supporting information for CAD, part, sequence, and interaction interpretation.

### Assembly
- Assembly name: `{self.assembly_name}`

### Manual User Notes
{user_notes.strip() or "No manual notes provided."}

### Uploaded Document Summary
{document_sections}

### Confirmed User Corrections
{corrections.strip() or "No corrections provided."}

### Assembly Analysis Feedback
{assembly_analysis_summary.strip() or "No assembly-analysis-specific feedback provided."}

### Sequence Feedback
{sequence_summary.strip() or "No sequence-specific feedback provided."}

### Uncertainties
Prefer STEP geometry, renderings, and generated BOM data when they conflict with uploaded text. Treat document-derived hints as support, not as authoritative geometry.
"""
        context_block = self._truncate_context(context_block)

        result = ContentUnderstanding(
            understanding_markdown=understanding,
            additional_context_block=context_block,
            document_count=len(bundle.documents) if bundle else 0,
            warnings=warnings,
        )
        self.save_understanding(result)
        return result

    def save_understanding(self, understanding: ContentUnderstanding) -> None:
        (self.agent_txt_dir / "content_agent_understanding.md").write_text(
            understanding.understanding_markdown,
            encoding="utf-8",
        )
        (self.agent_txt_dir / "additional_context_block.md").write_text(
            understanding.additional_context_block,
            encoding="utf-8",
        )
        metadata = {
            "assembly_name": self.assembly_name,
            "document_count": understanding.document_count,
            "warnings": understanding.warnings or [],
            "context_chars": len(understanding.additional_context_block),
        }
        (self.agent_txt_dir / "content_agent_metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def ask(self, prompt: str, *, default: str = "") -> str:
        if self.input_queue is not None:
            self._emit("message", role="assistant", content=prompt)
            try:
                value = self.input_queue.get(timeout=None)
            except queue.Empty:
                value = default
            return str(value or default)
        return input(prompt).strip() or default

    def confirm_or_collect_corrections(self, understanding: ContentUnderstanding) -> str:
        print("\n" + "=" * 80)
        print("CONTENT AGENT UNDERSTANDING")
        print("=" * 80)
        print(understanding.understanding_markdown)
        answer = self.ask("\nIs this understanding correct? [Y/n] ", default="y").lower()
        if answer in {"", "y", "yes"}:
            return ""
        return self.ask("Please add corrections or missing context:\n> ", default="")

    def _summarize_documents(self, bundle: Optional[DocumentBundle]) -> str:
        if not bundle or not bundle.documents:
            return "No additional documents were provided."
        sections: list[str] = []
        for doc in bundle.documents:
            text = doc.text.strip() or "(no extracted text)"
            excerpt = text[:1800]
            if len(text) > len(excerpt):
                excerpt += "\n\n...(truncated excerpt; full extraction is saved in Agent_txt_files/ingested_documents)"
            warnings = self._format_warnings(doc.warnings)
            sections.append(
                f"### {doc.file_name}\n"
                f"- Type: `{doc.file_type}`\n"
                f"- Backend: `{doc.extraction_backend}`\n"
                f"- Source: `{doc.source_path}`\n"
                f"- Warnings: {warnings}\n\n"
                f"{excerpt}"
            )
        return "\n\n".join(sections)

    def _truncate_context(self, text: str) -> str:
        if len(text) <= self.max_context_chars:
            return text
        marker = "\n\n[Content agent context truncated to configured maximum characters.]"
        return text[: max(0, self.max_context_chars - len(marker))] + marker

    def _save_document_summary(self, summary: str) -> None:
        (self.agent_txt_dir / "additional_data_llm_summary.md").write_text(summary, encoding="utf-8")

    @staticmethod
    def _format_warnings(warnings: list[str] | None) -> str:
        if not warnings:
            return "None."
        return "\n".join(f"- {warning}" for warning in warnings)

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        if not self.ui_callback:
            return
        try:
            self.ui_callback(event_type, **kwargs)
        except TypeError:
            self.ui_callback({"type": event_type, **kwargs})


def extract_assembly_summary(state: Dict[str, Any]) -> str:
    """Create a compact text summary from the current assembly analysis state."""
    result = state.get("assembly_result") or {}
    analysis = result.get("analysis") if isinstance(result, dict) else None
    if isinstance(analysis, dict):
        for key in ("response", "content", "text", "analysis"):
            value = analysis.get(key)
            if value:
                return str(value)[:4000]
    if result:
        return json.dumps(result, indent=2, ensure_ascii=False)[:4000]
    return "No assembly analysis result available."


def _load_required_prompt(prompt_id: str) -> str:
    if get_prompt_template is None:
        raise RuntimeError("agent.prompt_store could not be imported")
    try:
        prompt = get_prompt_template(prompt_id)
    except Exception as exc:
        raise RuntimeError(f"Could not load prompt '{prompt_id}' from configs/prompts.yaml: {exc}") from exc
    if not prompt:
        raise ValueError(f"Prompt '{prompt_id}' was not found in configs/prompts.yaml")
    return prompt


def extract_sequence_summary(state: Dict[str, Any]) -> str:
    """Create a compact text summary from the current assembly sequence."""
    sequence_data = state.get("assembly_sequence_data") or {}
    steps = sequence_data.get("steps") if isinstance(sequence_data, dict) else None
    if not steps:
        path = state.get("assembly_sequence_path")
        if path and Path(path).exists():
            try:
                sequence_data = json.loads(Path(path).read_text(encoding="utf-8"))
                steps = sequence_data.get("steps")
            except Exception:
                steps = None
    if not steps:
        return "No assembly sequence available."
    lines = []
    for step in steps[:25]:
        if isinstance(step, dict):
            sid = step.get("step_id") or step.get("step_number") or "?"
            desc = step.get("step_description") or step.get("description") or step.get("joining_process") or ""
            lines.append(f"- Step {sid}: {desc}")
    if len(steps) > 25:
        lines.append(f"- ... {len(steps) - 25} additional steps not shown")
    return "\n".join(lines)
