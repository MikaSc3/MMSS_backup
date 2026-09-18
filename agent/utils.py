from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set


def invoke_with_retry(
    llm_structured: Any,
    messages: list,
    max_retries: int = 5,
    base_backoff: float = 2.0,
) -> Any:
    """Invoke a LangChain structured-output LLM with exponential-backoff retry.

    Retries on HTTP 429 / RateLimitError up to *max_retries* times.
    Wait times: base_backoff * 2^attempt  →  2 s, 4 s, 8 s, 16 s, 32 s.
    All other exceptions are re-raised immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return llm_structured.invoke(messages)
        except Exception as exc:
            is_rate_limit = (
                "429" in str(exc)
                or "RateLimitReached" in str(exc)
                or "rate_limit" in str(exc).lower()
                or "RateLimitError" in type(exc).__name__
            )
            if is_rate_limit and attempt < max_retries:
                wait = base_backoff * (2 ** attempt)
                print(f"    [RETRY] Rate limit hit – waiting {wait:.0f}s "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


def wprint(state: Dict[str, Any], msg: str) -> None:
	if bool(state.get("workflow_print", False)):
		print(msg, flush=True)


def carry(state: Dict[str, Any], **updates: Any) -> Dict[str, Any]:
	"""LangGraph StateGraph(dict) replaces state each node.

	To avoid losing config keys (e.g. workflow_print, parallel, limits), we carry
	forward the full prior state and update only what changed.
	"""
	out = dict(state)
	out.update(updates)
	return out


def safe_basename(p: Any) -> Optional[str]:
	try:
		if not p:
			return None
		return Path(str(p)).name
	except Exception:
		return None


def sha256_text(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def format_metadata_files_in_prompt(tool_result: Any) -> str:
	"""Format tool-returned metadata attachment info for concise workflow logs."""
	if not isinstance(tool_result, dict):
		return "(unknown)"
	files = tool_result.get("metadata_files_in_prompt")
	if not isinstance(files, list) or not files:
		meta = tool_result.get("metadata")
		if isinstance(meta, list) and meta:
			return ", ".join([str(x) for x in meta if str(x).strip()])
		return "(none)"

	chunks: List[str] = []
	for it in files:
		if not isinstance(it, dict):
			continue
		label = str(it.get("label") or "").strip() or "(unknown)"
		p = str(it.get("path") or "").strip()
		name = Path(p).name if p else "(unknown)"
		bytes_ = it.get("bytes")
		sub = str(it.get("injected_subfield") or "").strip()
		suffix = f"::{sub}" if sub else ""
		if isinstance(bytes_, int):
			chunks.append(f"{label}{suffix}={name} ({bytes_} bytes)")
		else:
			chunks.append(f"{label}{suffix}={name}")
	return ", ".join(chunks) if chunks else "(none)"


def token_usage_from_tool_result(tool_result: Any) -> Dict[str, int]:
	"""Extract token usage from a tool result produced by agent/tools.py."""
	if not isinstance(tool_result, dict):
		return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	analysis = tool_result.get("analysis")
	if not isinstance(analysis, dict):
		return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	stats = analysis.get("stats")
	if not isinstance(stats, dict):
		return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	usage = stats.get("token_usage")
	if not isinstance(usage, dict):
		return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

	inp = int(usage.get("input_tokens") or 0)
	out = int(usage.get("output_tokens") or 0)
	tot = usage.get("total_tokens")
	total = int(tot) if isinstance(tot, int) else int(inp + out)
	return {"input_tokens": inp, "output_tokens": out, "total_tokens": total}


DEFAULT_STATS_KEEP: Set[str] = {
	"task",
	"view_filter_keywords",
	"images_after_view_filter_count",
	"downscaling_factor",
	"tokens_per_img",
	"computed_max_completion_tokens",
	"prompt_id",
	"examples_requested",
	"context_block_labels",
	"context_block_char_lens",
	"selected_image_count",
	"selected_total_bytes",
	"llm_invoke_ms",
	"total_runtime_ms",
	"token_usage",
}


def reduce_stats(stats: Any, *, keep: Optional[Iterable[str]] = None) -> Dict[str, Any]:
	if not isinstance(stats, dict):
		return {}
	keep_set = set(keep) if keep is not None else DEFAULT_STATS_KEEP
	return {k: stats.get(k) for k in keep_set if k in stats}


def extract_step_details(tool_result: Any, *, include_step_details: bool = True) -> Dict[str, Any]:
	"""Extract a compact step summary for the run manifest."""
	if not isinstance(tool_result, dict):
		return {}
	analysis = tool_result.get("analysis")
	if not isinstance(analysis, dict):
		analysis = {}

	searchdir = tool_result.get("searchdir")
	out: Dict[str, Any] = {
		"searchdir_name": safe_basename(searchdir),
		"metadata_written_file": safe_basename(tool_result.get("metadata_written_path")),
		"metadata_files_in_prompt": [],
	}

	mf = tool_result.get("metadata_files_in_prompt")
	if isinstance(mf, list):
		for it in mf:
			if not isinstance(it, dict):
				continue
			out["metadata_files_in_prompt"].append(
				{
					"label": it.get("label"),
					"file": safe_basename(it.get("path")),
					"bytes": it.get("bytes"),
					"injected_subfield": it.get("injected_subfield"),
				}
			)

	if include_step_details:
		sel = analysis.get("selected")
		if isinstance(sel, list):
			out["selected_images"] = [
				x.get("pic_name")
				for x in sel
				if isinstance(x, dict) and x.get("pic_name")
			]
		out["stats"] = reduce_stats(analysis.get("stats"))
		out["warnings"] = tool_result.get("warnings")

	return out
