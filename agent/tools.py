
from __future__ import annotations

def matches_image_keyword(filename: str, keyword: str) -> bool:
	"""
	Gibt True zurück, wenn keyword als ganzes Wort (mit _ oder - oder am Anfang/Ende) im Dateinamen (ohne Extension) vorkommt.
	Beispiel: 'iso1_transp_0_3' matched nur 'iso1_transp_0_3.png', nicht 'explosion_iso1_transp_0_3.png'.
	"""
	import os
	import re
	base = os.path.splitext(os.path.basename(filename))[0]
	return re.search(rf'(^|[_\-]){re.escape(keyword)}($|[_\-])', base) is not None

import base64
import io
import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal, Union

import yaml
from dotenv import load_dotenv
from langchain.tools import tool
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from pydantic import BaseModel, Field
from typing_extensions import Annotated

try:
	from agent.prompt_store import get_prompt_template, render_examples_block, get_system_and_human_prompts
except ImportError:  # pragma: no cover
	from prompt_store import get_prompt_template, render_examples_block, get_system_and_human_prompts

try:
	from agent.structured_output import (
		AssemblyAnalysis,
		AssemblyBatchAnalysis,
		CertaintyItem,
		GeometricFeature,
		PartOverview,
		SinglePartAnalysis,
		SinglePartBatchAnalysis,
	)
except ImportError:  # pragma: no cover
	from structured_output import (
		AssemblyAnalysis,
		AssemblyBatchAnalysis,
		CertaintyItem,
		GeometricFeature,
		PartOverview,
		SinglePartAnalysis,
		SinglePartBatchAnalysis,
	)


# Load environment variables from .env in the same directory
from pathlib import Path as _Path
load_dotenv(_Path(__file__).parent / ".env")


class ImageLoader:
	"""Find and base64-encode images from a single directory (non-recursive).
	
	Features:
	- Image caching via LRU cache (reduces redundant encoding)
	- Keyword-based image search
	- Vision-compatible base64 encoding
	"""

	def __init__(self, search_dir: str | Path):
		self.search_dir = Path(search_dir)
		if not self.search_dir.exists() or not self.search_dir.is_dir():
			raise ValueError(f"Search directory does not exist or is not a directory: {self.search_dir}")
		# Cache for encoded images (path -> base64)
		self._cache: Dict[Path, str] = {}

	def find_images(self, keywords: List[str], extension: str = ".png") -> Dict[str, List[Path]]:
		"""Return all images in search_dir that match each keyword (case-insensitive).

		Only searches directly inside search_dir (no recursion).
		"""
		normalized_keywords = [k.strip().lower() for k in (keywords or []) if k and str(k).strip()]
		candidates = sorted(
			[p for p in self.search_dir.glob(f"*{extension}") if p.is_file()],
			key=lambda p: p.name.lower(),
		)

		matches: Dict[str, List[Path]] = {k: [] for k in normalized_keywords}
		from agent.tools import matches_image_keyword
		for img_path in candidates:
			for k in normalized_keywords:
				if matches_image_keyword(img_path.name, k):
					matches[k].append(img_path)
		return matches

	def encode_image(self, image_path: Path) -> str:
		"""Read image bytes and return base64 string.
		
		Uses cache to avoid re-encoding the same image multiple times.
		"""
		# Check cache first
		if image_path in self._cache:
			return self._cache[image_path]
		
		# Encode and cache
		img_bytes = image_path.read_bytes()
		b64_str = base64.b64encode(img_bytes).decode("utf-8")
		self._cache[image_path] = b64_str
		return b64_str

	def find_and_encode(
		self,
		keywords: List[str],
		extension: str = ".png",
	) -> Tuple[Dict[str, List[str]], List[str]]:
		"""Find & encode multiple images per keyword (non-recursive).

		Returns:
			(encoded, warnings)
			encoded: dict keyword -> list[base64]
		"""
		warnings: List[str] = []
		found = self.find_images(keywords, extension=extension)
		encoded: Dict[str, List[str]] = {}

		for keyword, paths in found.items():
			if not paths:
				warnings.append(f"No images found for keyword '{keyword}' in {self.search_dir}")
				encoded[keyword] = []
				continue

			encoded_list: List[str] = []
			for p in paths:
				try:
					encoded_list.append(self.encode_image(p))
				except Exception as e:
					warnings.append(f"Could not read/encode '{p.name}': {e}")
			encoded[keyword] = encoded_list

			if not encoded_list:
				warnings.append(f"All images for keyword '{keyword}' failed to encode in {self.search_dir}")

		return encoded, warnings

	@staticmethod
	def build_vision_image_items(img_b64_list: List[str], mime: str = "image/png") -> List[dict]:
		"""Build OpenAI/LangChain-compatible multimodal image items."""
		return [
			{
				"type": "image_url",
				"image_url": {"url": f"data:{mime};base64,{b64}"},
			}
			for b64 in (img_b64_list or [])
			if b64
		]


class JsonLoader:
	"""Find and load JSON files from a single directory (non-recursive)."""

	def __init__(self, search_dir: str | Path):
		self.search_dir = Path(search_dir)
		if not self.search_dir.exists() or not self.search_dir.is_dir():
			raise ValueError(f"Search directory does not exist or is not a directory: {self.search_dir}")

	def find_json_files(self, keywords: List[str], extension: str = ".json") -> Dict[str, List[Path]]:
		"""Return all JSON files in search_dir that match each keyword (case-insensitive).

		Only searches directly inside search_dir (no recursion).
		"""
		normalized_keywords = [k.strip().lower() for k in (keywords or []) if k and str(k).strip()]
		candidates = sorted(
			[p for p in self.search_dir.glob(f"*{extension}") if p.is_file()],
			key=lambda p: p.name.lower(),
		)

		matches: Dict[str, List[Path]] = {k: [] for k in normalized_keywords}
		for json_path in candidates:
			stem_lower = json_path.stem.lower()
			for k in normalized_keywords:
				if k in stem_lower:
					matches[k].append(json_path)
		return matches

	def load_json_text(self, json_path: Path) -> str:
		with open(json_path, "r", encoding="utf-8") as f:
			data = json.load(f)
		return json.dumps(data, indent=2, ensure_ascii=False)

	def find_and_load(self, keywords: List[str], extension: str = ".json") -> Tuple[Dict[str, List[Dict[str, str]]], List[str]]:
		warnings: List[str] = []
		found = self.find_json_files(keywords, extension=extension)
		loaded: Dict[str, List[Dict[str, str]]] = {}

		for keyword, paths in found.items():
			if not paths:
				warnings.append(f"No JSON files found for keyword '{keyword}' in {self.search_dir}")
				loaded[keyword] = []
				continue

			items: List[Dict[str, str]] = []
			for p in paths:
				try:
					items.append({
						"file_name": p.name,
						"file_path": str(p),
						"json_text": self.load_json_text(p),
					})
				except Exception as e:
					warnings.append(f"Could not read/parse '{p.name}': {e}")
			loaded[keyword] = items

			if not items:
				warnings.append(f"All JSON files for keyword '{keyword}' failed to load in {self.search_dir}")

		return loaded, warnings

	@staticmethod
	def build_json_context_block(loaded: Dict[str, List[Dict[str, str]]]) -> str:
		"""Build a readable text block (optional helper for prompt construction)."""
		lines: List[str] = ["Metadata JSON files:"]
		for kw, items in (loaded or {}).items():
			if not items:
				continue
			lines.append(f"\n[Keyword: {kw}]")
			for it in items:
				file_name = it.get("file_name", "")
				file_path = it.get("file_path", "")
				json_text = it.get("json_text", "")
				if file_path:
					lines.append(f"\n--- {file_name} ---\nPath: {file_path}\n{json_text}")
				else:
					lines.append(f"\n--- {file_name} ---\n{json_text}")
		if len(lines) == 1:
			lines.append("(none)")
		return "\n".join(lines)


# ============================================================================
# Universal JSON Key Extraction Utility
# ============================================================================

def extract_json_keys_from_file(
	json_path: Path,
	keys: List[str],
	part_id_name_list: Optional[List[str]] = None
) -> dict:
	"""
	Extrahiert spezifische Keys aus einer JSON-Datei (verschachtelt, nur gewünschte Felder).
	
	Args:
		json_path: Pfad zur JSON-Datei
		keys: Liste der zu extrahierenden Keys (z.B. ["part_id", "volume", "bounding_box"])
		part_id_name_list: Optional - Liste von part_id_names (z.B. ["part001_bearing", "part002_bolt"])
			- Wenn leer/None: Alle Parts werden geladen
			- Wenn gefüllt: Nur Parts mit matching part_id werden geladen (extrahiert aus part_id_name durch Split)
	
	Returns:
		Dict mit extrahierten Daten (verschachtelte Struktur erhalten)
		
	Beispiel Input JSON:
		{
			"parts": [
				{"part_id": "part001", "part_name": "bearing", "volume": 100, "other_data": "..."},
				{"part_id": "part002", "part_name": "bolt", "volume": 50, "other_data": "..."}
			]
		}
	
	Beispiel Aufruf:
		extract_json_keys_from_file(json_path, ["part_id", "volume"], ["part001_bearing"])
		
	Beispiel Output:
		{
			"parts": [
				{"part_id": "part001", "volume": 100}
			]
		}
	"""
	try:
		with open(json_path, 'r', encoding='utf-8') as f:
			data = json.load(f)
	except Exception as e:
		print(f"[WARNING] Failed to load JSON {json_path.name}: {e}")
		return {}
	
	# Extract part_ids from part_id_name_list (split at first "_")
	filter_part_ids = None
	if part_id_name_list:
		filter_part_ids = set()
		for entry in part_id_name_list:
			# Extract part_id from "part001_bearing" -> "part001"
			part_id = entry.split("_")[0] if "_" in entry else entry
			filter_part_ids.add(part_id)
	
	# Helper function to extract specific keys from a dict
	def extract_keys(obj: dict, keys_to_extract: List[str]) -> dict:
		# NEW: If no keys specified, return complete object
		if not keys_to_extract:
			return obj.copy()
		
		extracted = {}
		for key in keys_to_extract:
			if key in obj:
				extracted[key] = obj[key]
		return extracted
	
	# Process the JSON data
	result = {}
	
	# If JSON is a dict, extract top-level keys first
	if isinstance(data, dict):
		# Extract top-level keys (e.g., assembly_id, total_parts, bounding_box)
		result = extract_keys(data, keys)
		
		# Additionally, process "parts" list if it exists
		if "parts" in data and isinstance(data["parts"], list):
			# Check if parts is a list of dicts (BOM structure) or list of strings (assembly overview)
			if data["parts"] and isinstance(data["parts"][0], dict):
				# BOM structure: filter and extract keys from part dicts
				filtered_parts = []
				for part in data["parts"]:
					if isinstance(part, dict):
						part_id = part.get("part_id")
						
						# Filter by part_id if filter is active
						if filter_part_ids is not None:
							if part_id not in filter_part_ids:
								continue
						
						# Extract only the specified keys
						extracted_part = extract_keys(part, keys)
						if extracted_part:
							filtered_parts.append(extracted_part)
				
				# Only include parts if non-empty OR explicitly requested in keys
				if filtered_parts or "parts" in keys:
					result["parts"] = filtered_parts
			else:
				# Assembly overview structure: keep parts list as-is (list of strings)
				# Only include if "parts" is explicitly requested in keys
				if "parts" in keys:
					result["parts"] = data["parts"]
	
	# If JSON is a list of dicts (less common)
	elif isinstance(data, list):
		filtered_items = []
		for item in data:
			if isinstance(item, dict):
				part_id = item.get("part_id")
				
				# Filter by part_id if filter is active
				if filter_part_ids is not None:
					if part_id not in filter_part_ids:
						continue
				
				extracted_item = extract_keys(item, keys)
				if extracted_item:
					filtered_items.append(extracted_item)
		
		result = filtered_items
	
	return result


# ============================================================================
# Structured Output Models wurden nach agent/structured_output.py verschoben
# ============================================================================


ImageDescribeTask = Literal["AssemblyAnalysis", "SinglePartAnalysis"]


# ── LLM Model Registry ───────────────────────────────────────────────────────
# Maps the short model alias used in experiment YAMLs (llm_model: "4o" / "4.1" / "5.4")
# to the corresponding Azure env-var keys and deployment name.
# 'api_key_env' is optional; falls back to API_KEY_GPT_4 if not set.
# 'use_v1_api'=True → uses ChatOpenAI with base_url=endpoint/openai/v1/ (Responses API for GPT-5.x)
#              False → uses AzureChatOpenAI with azure_endpoint (Chat Completions for GPT-4.x)
# IMPORTANT: 'deployment' must match the EXACT deployment name in Azure AI Foundry
#            (Deployments → Name column). For GPT-5.x override via AZURE_DEPLOYMENT_54.
_MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
	"4o":  {"env_key": "AZURE_ENDPOINT_4O",  "deployment": "gpt-4o",  "api_key_env": "API_KEY_GPT_4", "api_version": "2024-12-01-preview", "use_v1_api": False},
	"4.1": {"env_key": "AZURE_ENDPOINT_41",  "deployment": "gpt-4.1", "api_key_env": "API_KEY_GPT_4", "api_version": "2024-12-01-preview", "use_v1_api": False},
	"5.4": {"env_key": "AZURE_ENDPOINT_54",  "deployment": "gpt-5.4", "api_key_env": "API_KEY_GPT_5", "api_version": "2025-04-01-preview", "use_v1_api": True,
	        "deployment_env": "AZURE_DEPLOYMENT_54"},
}

# Cache keyed by (max_completion_tokens, model_alias) so switching models
# between runs doesn't reuse a stale client.
_IMG_DESCRIBER_LLM_CACHE: Dict[tuple, AzureChatOpenAI] = {}


def _get_img_describer_llm(*, max_completion_tokens: int, llm_model_override: Optional[str] = None) -> AzureChatOpenAI:
	global _IMG_DESCRIBER_LLM_CACHE

	# Read active model from experiment settings; fall back to "5.4"
	try:
		try:
			from agent.prompt_store import load_experiment_settings
		except ImportError:
			from prompt_store import load_experiment_settings  # type: ignore
		settings = load_experiment_settings()
		model = llm_model_override or settings.get("llm_model") or "5.4"
		if llm_model_override:
			print(f"[LLM] llm_model from override: '{model}' (APA_EXPERIMENT_YAML={os.getenv('APA_EXPERIMENT_YAML')})")
		else:
			print(f"[LLM] llm_model from settings: '{model}' (APA_EXPERIMENT_YAML={os.getenv('APA_EXPERIMENT_YAML')})")
	except Exception as e:
		print(f"[LLM] WARNING: Could not read llm_model from settings ({e}), falling back to '5.4'")
		model = llm_model_override or "5.4"

	cache_key = (int(max_completion_tokens), model)
	if cache_key not in _IMG_DESCRIBER_LLM_CACHE:
		cfg = _MODEL_REGISTRY.get(model, _MODEL_REGISTRY["5.4"])
		# Endpoint: primary env var → fallback to old AZURE_ENDPOINT for backwards compat
		raw_endpoint = (
			os.getenv(cfg["env_key"])
			or os.getenv("AZURE_ENDPOINT_4O")
			or os.getenv("AZURE_ENDPOINT")
			or ""
		)
		# Per-model API key → fallback to shared GPT-4 key
		api_key = (
			os.getenv(cfg.get("api_key_env", "API_KEY_GPT_4"))
			or os.getenv("API_KEY_GPT_4")
		)
		# Per-model api_version; env-var override takes precedence
		api_version = os.getenv("AZURE_API_VERSION") or cfg.get("api_version", "2024-12-01-preview")
		# Deployment name: env-var override → registry default
		deployment_env_key = cfg.get("deployment_env")
		deployment = (
			(os.getenv(deployment_env_key) if deployment_env_key else None)
			or cfg["deployment"]
		)
		if cfg.get("use_v1_api"):
			# GPT-5.x: Responses API via /openai/v1/ – extract base URL, strip any path
			import re as _re
			base = _re.match(r"(https?://[^/]+)", raw_endpoint)
			base_url = (base.group(1) if base else raw_endpoint.rstrip("/")) + "/openai/v1/"
			print(f"[LLM] Creating ChatOpenAI (v1/Responses): model={model}, deployment='{deployment}', base_url='{base_url}'")
			_IMG_DESCRIBER_LLM_CACHE[cache_key] = ChatOpenAI(
				base_url=base_url,
				api_key=api_key,
				model=deployment,
				max_completion_tokens=int(max_completion_tokens),
				temperature=0,
				seed=42,
			)
		else:
			# GPT-4.x: Chat Completions via AzureChatOpenAI
			print(f"[LLM] Creating AzureChatOpenAI: model={model}, deployment='{deployment}', api_version='{api_version}'")
			_IMG_DESCRIBER_LLM_CACHE[cache_key] = AzureChatOpenAI(
				azure_endpoint=raw_endpoint,
				api_key=api_key,
				api_version=api_version,
				azure_deployment=deployment,
				max_completion_tokens=int(max_completion_tokens),
				temperature=0,
				seed=42,
			)
	return _IMG_DESCRIBER_LLM_CACHE[cache_key]


def _format_assembly_context_json(assembly_result: Dict[str, object]) -> str:
	try:
		return json.dumps(assembly_result, ensure_ascii=False, separators=(",", ":"))
	except Exception:
		return str(assembly_result)


def _resolve_and_validate_path(file_path: str) -> Tuple[Optional[Path], Optional[str]]:
	try:
		p = Path(file_path)
		workspace_root = Path(__file__).resolve().parents[1]
		if not p.is_absolute():
			p = (workspace_root / p).resolve()
		else:
			p = p.resolve()

		try:
			p.relative_to(workspace_root)
		except Exception:
			return None, f"Refusing to access path outside workspace: {p}"

		return p, None
	except Exception as e:
		return None, f"Invalid path '{file_path}': {e}"


def _resolve_and_validate_dir(dir_path: str) -> Tuple[Optional[Path], Optional[str]]:
	try:
		p = Path(dir_path)
		workspace_root = Path(__file__).resolve().parents[1]
		if not p.is_absolute():
			p = (workspace_root / p).resolve()
		else:
			p = p.resolve()

		try:
			p.relative_to(workspace_root)
		except Exception:
			return None, f"Refusing to access directory outside workspace: {p}"

		if not p.exists() or not p.is_dir():
			return None, f"Invalid directory: {p}"

		return p, None
	except Exception as e:
		return None, f"Invalid directory path '{dir_path}': {e}"


def _downscale_image_bytes_if_needed(
	img_bytes: bytes,
	*,
	mime: str,
	downscaling_factor: float,
) -> bytes:
	if not img_bytes:
		return img_bytes
	if downscaling_factor is None or downscaling_factor >= 1.0:
		return img_bytes

	try:
		from PIL import Image
	except Exception:
		return img_bytes

	try:
		with Image.open(io.BytesIO(img_bytes)) as img:
			w, h = img.size
			new_w = max(1, int(w * float(downscaling_factor)))
			new_h = max(1, int(h * float(downscaling_factor)))
			if new_w == w and new_h == h:
				return img_bytes

			try:
				resample = Image.Resampling.LANCZOS  # Pillow >= 9
			except Exception:
				resample = Image.LANCZOS

			scaled = img.resize((new_w, new_h), resample=resample)

			buf = io.BytesIO()
			mime_l = (mime or "").lower().strip()
			if mime_l in {"image/jpeg", "image/jpg"}:
				if scaled.mode in {"RGBA", "LA", "P"}:
					scaled = scaled.convert("RGB")
				scaled.save(buf, format="JPEG", quality=85, optimize=True, progressive=True)
			elif mime_l == "image/webp":
				scaled.save(buf, format="WEBP", quality=80, method=6)
			else:
				# Default: keep PNG semantics (lossless, supports alpha)
				scaled.save(buf, format="PNG", optimize=True)
			return buf.getvalue()
	except Exception:
		return img_bytes


def _encode_image_as_data_url(
	image_path: Path,
	mime: str = "image/png",
	*,
	downscaling_factor: float = 1.0,
) -> str:
	img_bytes = image_path.read_bytes()
	img_bytes = _downscale_image_bytes_if_needed(img_bytes, mime=mime, downscaling_factor=downscaling_factor)
	b64 = base64.b64encode(img_bytes).decode("utf-8")
	return f"data:{mime};base64,{b64}"


def _collect_matching_images(
	searchdir: Path,
	keywords: List[str],
	extension: str = ".png",
	*,
	allow_all_if_no_keywords: bool = False,
) -> Tuple[List[Path], List[str]]:
	warnings: List[str] = []
	normalized_keywords = [k.strip().lower() for k in (keywords or []) if k and str(k).strip()]
	if not normalized_keywords:
		if not allow_all_if_no_keywords:
			return [], ["No keywords provided."]
		candidates = sorted(
			[p for p in searchdir.glob(f"*{extension}") if p.is_file()],
			key=lambda p: p.name.lower(),
		)
		if not candidates:
			warnings.append(f"No images found in {searchdir}")
		return candidates, warnings

	candidates = sorted(
		[p for p in searchdir.glob(f"*{extension}") if p.is_file()],
		key=lambda p: p.name.lower(),
	)

	matched: List[Path] = []
	seen: set[str] = set()
	for p in candidates:
		stem_lower = p.stem.lower()
		if any(k in stem_lower for k in normalized_keywords):
			if p.name.lower() not in seen:
				matched.append(p)
				seen.add(p.name.lower())

	if not matched:
		warnings.append(f"No images matched keywords {normalized_keywords} in {searchdir}")
	return matched, warnings


def _filter_images_by_views(images: List[Path], view_keywords: List[str], label: str) -> Tuple[List[Path], List[str]]:
	warnings: List[str] = []
	view_keywords = [k.strip().lower() for k in (view_keywords or []) if k and str(k).strip()]
	if not view_keywords:
		return images, warnings

	filtered = [p for p in images if any(k in p.stem.lower() for k in view_keywords)]
	if not filtered and images:
		warnings.append(f"View filter {label}={view_keywords} removed all images; using unfiltered selection")
		return images, warnings
	return filtered, warnings


_EXPERIMENT_SETTINGS: Dict[str, object] = {
	"img_to_analyse_assy": ["top"],
	"img_to_analyse_monopart": ["top"],
	"max_images_per_call": None,
	"use_assembly_context": True,
	"prompt_id_assy": "assembly_describer_v1",
	"prompt_id_monopart": "monopart_describer_v1",
	"prompt_id_system": "system_prompt_v1",
}


def _get_experiment_settings() -> Dict[str, object]:
	settings: Dict[str, object] = dict(_EXPERIMENT_SETTINGS)
	workspace_root = Path(__file__).resolve().parents[1]

	def _merge_yaml(path: Path) -> None:
		try:
			if not path.exists() or not path.is_file():
				return
			data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
			if isinstance(data, dict):
				settings.update(data)
		except Exception:
			return

	_merge_yaml(workspace_root / "configs" / "default_settings.yaml")
	_merge_yaml(workspace_root / "experiment.yaml")

	exp_env = os.getenv("APA_EXPERIMENT_YAML")
	if exp_env and str(exp_env).strip():
		exp_path = Path(str(exp_env))
		if not exp_path.is_absolute():
			exp_path = (workspace_root / exp_path).resolve()
		else:
			exp_path = exp_path.resolve()
		try:
			exp_path.relative_to(workspace_root)
			_merge_yaml(exp_path)
		except Exception:
			pass

	return settings


def format_content_agent_context_block(
	additional_context_block: Optional[str],
	settings: Optional[Dict[str, object]] = None,
	*,
	label: str = "CONTENT_AGENT_CONTEXT",
) -> Optional[Tuple[str, str]]:
	"""Return a standardized prompt block for tool-call scoped content-agent context."""
	if not additional_context_block or not str(additional_context_block).strip():
		return None

	settings = settings or {}
	try:
		content_agent_settings = settings.get("content_agent")
		if not isinstance(content_agent_settings, dict):
			content_agent_settings = {}
		max_chars = int(
			settings.get("content_agent_max_context_chars")
			or content_agent_settings.get("max_context_chars")
			or 12000
		)
	except Exception:
		max_chars = 12000

	text = str(additional_context_block).strip()
	if max_chars > 0 and len(text) > max_chars:
		text = text[:max_chars] + "\n... (truncated)"

	wrapped = (
		"The following context was collected from the user and uploaded documents. "
		"Use it as supporting information. Prefer geometry/renderings/BOM when conflicts exist, "
		"but use this context to interpret unclear parts, constraints, and assembly intent.\n\n"
		+ text
	)
	return (label, wrapped)


def _describe_images_in_dir_impl(
	*,
	root: Path,
	keywords: List[str],
	task: ImageDescribeTask,
	limit: int,
	context_json: Optional[str] = None,
	context_label: str = "ASSEMBLY_CONTEXT_JSON",
	context_blocks: Optional[List[Tuple[str, str]]] = None,
	allow_all_if_no_keywords: bool = False,
	extra_images: Optional[List[Path]] = None,
	extra_images_label: str = "ASSEMBLY_REFERENCE_IMAGES",
	additional_context_block: Optional[str] = None,
) -> Dict[str, object]:
	start_t = time.perf_counter()
	warnings: List[str] = []
	settings = _get_experiment_settings()
	original_limit = int(limit) if (limit is not None) else None
	try:
		downscaling_factor = float(settings.get("downscaling_factor") or 1.0)
	except Exception:
		downscaling_factor = 1.0

	matched_by_keywords, match_warnings = _collect_matching_images(
		root,
		keywords,
		extension=".png",
		allow_all_if_no_keywords=allow_all_if_no_keywords,
	)
	warnings.extend(match_warnings)
	matched_keyword_count = len(matched_by_keywords)

	view_key = "img_to_analyse_assy" if task == "AssemblyAnalysis" else "img_to_analyse_monopart"
	raw_views = settings.get(view_key) or settings.get("img_to_analyse")
	if raw_views and view_key != "img_to_analyse" and not settings.get(view_key):
		view_key = "img_to_analyse"

	view_keywords = [str(x).strip().lower() for x in (raw_views or []) if str(x).strip()]
	matched_after_view, view_warnings = _filter_images_by_views(matched_by_keywords, view_keywords, label=view_key)
	warnings.extend(view_warnings)
	matched_after_view_count = len(matched_after_view)

	max_images_per_call = settings.get("max_images_per_call")
	if isinstance(max_images_per_call, int) and max_images_per_call > 0:
		limit = min(limit, max_images_per_call) if (limit is not None and limit > 0) else max_images_per_call
	effective_limit = int(limit) if (limit is not None) else None

	if limit is not None and limit > 0:
		matched = matched_after_view[: int(limit)]
	else:
		matched = matched_after_view

	selected = [{"pic_name": p.name, "file_path": str(p)} for p in matched]
	if not matched:
		return {"searchdir": str(root), "selected": selected, "task": task, "result": None, "warnings": warnings}

	try:
		tokens_per_img = int(settings.get("img_describer_tokens_per_img") or 4000)
	except Exception:
		tokens_per_img = 4000
	computed_max_tokens = tokens_per_img * (len(matched) + len(extra_images or []))
	max_tokens = computed_max_tokens
	llm = _get_img_describer_llm(max_completion_tokens=max_tokens)

	if task == "AssemblyAnalysis":
		schema = AssemblyBatchAnalysis
		try:
			system_prompt_template, human_prompt_template = get_system_and_human_prompts("AAI", settings)
		except ValueError as e:
			raise ValueError(f"Failed to load AAI prompts: {e}")
		system_prompt_id = settings.get("AAI_system_prompt_id") or settings.get("base_system_prompt_id")
		human_prompt_id = settings.get("AAI_human_prompt_id")
		example_ids = settings.get("include_examples_assy") or []
		examples_block = render_examples_block(example_ids)
	else:
		schema = SinglePartBatchAnalysis
		try:
			system_prompt_template, human_prompt_template = get_system_and_human_prompts("AMI", settings)
		except ValueError as e:
			raise ValueError(f"Failed to load AMI prompts: {e}")
		system_prompt_id = settings.get("AMI_system_prompt_id") or settings.get("base_system_prompt_id")
		human_prompt_id = settings.get("AMI_human_prompt_id")
		example_ids = settings.get("include_examples_monopart") or []
		examples_block = render_examples_block(example_ids)

	if extra_images:
		extra_lines = "\n".join([f"- {p.name} [assembly context]" for p in extra_images])
		part_lines  = "\n".join([f"- {p.name} [part to analyse]" for p in matched])
		name_lines = extra_lines + "\n" + part_lines
	else:
		name_lines = "\n".join([f"- {p.name}" for p in matched])
	examples_text = f"\n\n{examples_block}" if examples_block else ""

	blocks: List[Tuple[str, str]] = []
	if context_blocks:
		blocks = [(str(lbl), str(val)) for (lbl, val) in context_blocks if str(lbl).strip() and str(val).strip()]
	elif context_json:
		blocks = [(str(context_label), str(context_json))]
	content_agent_block = format_content_agent_context_block(additional_context_block, settings)
	if content_agent_block:
		blocks.append(content_agent_block)

	# Start with human prompt template, then add context and examples
	human_prompt_parts = [human_prompt_template]
	
	if examples_text:
		human_prompt_parts.append(examples_text)
	
	if blocks:
		context_text = "\n\n".join([f"{lbl}:\n{val}" for (lbl, val) in blocks])
		human_prompt_parts.append(f"\n\n=== INPUT DATA ===\n{context_text}")
	
	human_prompt_parts.append(f"\n\nImages (in order):\n{name_lines}")
	prompt = "".join(human_prompt_parts)

	workflow_print = bool(settings.get("workflow_print", False))
	try:
		preview_chars = int(settings.get("workflow_print_prompt_preview_chars") or 800)
	except Exception:
		preview_chars = 800

	def _extract_token_usage(raw_msg: object) -> Optional[Dict[str, int]]:
		"""Best-effort extraction across LangChain/OpenAI variants."""
		try:
			usage = getattr(raw_msg, "usage_metadata", None)
			if isinstance(usage, dict):
				out: Dict[str, int] = {}
				for k in ("input_tokens", "output_tokens", "total_tokens"):
					v = usage.get(k)
					if isinstance(v, int):
						out[k] = v
				if out:
					# normalize total
					if "total_tokens" not in out:
						out["total_tokens"] = int(out.get("input_tokens", 0) + out.get("output_tokens", 0))
					return out
		except Exception:
			pass

		try:
			meta = getattr(raw_msg, "response_metadata", None)
			if isinstance(meta, dict):
				cand = meta.get("token_usage") or meta.get("usage")
				if isinstance(cand, dict):
					# OpenAI-style keys
					pt = cand.get("prompt_tokens")
					ct = cand.get("completion_tokens")
					tt = cand.get("total_tokens")
					out2: Dict[str, int] = {}
					if isinstance(pt, int):
						out2["input_tokens"] = pt
					if isinstance(ct, int):
						out2["output_tokens"] = ct
					if isinstance(tt, int):
						out2["total_tokens"] = tt
					if out2:
						if "total_tokens" not in out2:
							out2["total_tokens"] = int(out2.get("input_tokens", 0) + out2.get("output_tokens", 0))
						return out2
		except Exception:
			pass

		return None

	try:
		content: List[dict] = [{"type": "text", "text": prompt}]
		# Prepend assembly reference images (spatial context) if provided
		if extra_images:
			content.append({"type": "text", "text": f"\n[{extra_images_label}: {len(extra_images)} image(s) – use for spatial/assembly context only]"})
			for p in extra_images:
				content.append({"type": "image_url", "image_url": {"url": _encode_image_as_data_url(p, downscaling_factor=downscaling_factor)}})
			content.append({"type": "text", "text": "\n[PART IMAGES – analyse the following part]"})
		for p in matched:
			content.append(
				{
					"type": "image_url",
					"image_url": {"url": _encode_image_as_data_url(p, downscaling_factor=downscaling_factor)},
				}
			)

		# Create System + Human message structure
		system_msg = {"role": "system", "content": system_prompt_template}
		human_msg = {"role": "user", "content": content}
		messages = [system_msg, human_msg]
		
		invoke_t0 = time.perf_counter()
		raw_msg: object | None = None
		structured: object
		try:
			# Prefer raw+parsed so we can capture token usage.
			resp = llm.with_structured_output(schema, include_raw=True).invoke(messages)
			if isinstance(resp, dict) and ("parsed" in resp or "raw" in resp):
				raw_msg = resp.get("raw")
				structured = resp.get("parsed")
			else:
				structured = resp
		except TypeError:
			# Backward compatibility for older LangChain versions.
			structured = llm.with_structured_output(schema).invoke(messages)
		invoke_ms = int((time.perf_counter() - invoke_t0) * 1000)

		data = structured.model_dump() if hasattr(structured, "model_dump") else dict(structured)  # type: ignore[arg-type]
		data["images_used"] = [p.name for p in matched]

		total_bytes = 0
		try:
			total_bytes = sum(p.stat().st_size for p in matched)
		except Exception:
			total_bytes = 0

		token_usage = _extract_token_usage(raw_msg) if raw_msg is not None else None
		total_ms = int((time.perf_counter() - start_t) * 1000)

		stats: Dict[str, object] = {
			"task": task,
			"keywords": [str(k) for k in (keywords or []) if str(k).strip()],
			"allow_all_if_no_keywords": bool(allow_all_if_no_keywords),
			"images_matched_keyword_count": matched_keyword_count,
			"view_filter_key": view_key,
			"view_filter_keywords": view_keywords,
			"images_after_view_filter_count": matched_after_view_count,
			"limit_arg": original_limit,
			"max_images_per_call_setting": max_images_per_call,
			"limit_effective": effective_limit,
			"downscaling_factor": downscaling_factor,
			"tokens_per_img": tokens_per_img,
			"computed_max_completion_tokens": computed_max_tokens,
			"system_prompt_id": system_prompt_id,
			"human_prompt_id": human_prompt_id,
			"examples_requested": [str(x) for x in (example_ids or []) if str(x).strip()],
			"context_block_labels": [lbl for (lbl, _) in blocks],
			"context_block_char_lens": [len(str(val)) for (_, val) in blocks],
			"extra_images_count": len(extra_images) if extra_images else 0,
			"extra_images_label": extra_images_label if extra_images else None,
			"selected_image_count": len(matched),
			"selected_total_bytes": total_bytes,
			"max_completion_tokens": getattr(llm, "max_completion_tokens", None),
			"llm_invoke_ms": invoke_ms,
			"total_runtime_ms": total_ms,
			"token_usage": token_usage,
		}
		if workflow_print:
			stats.update(
				{
					"prompt_char_len": len(prompt),
					"prompt_preview": (prompt[:preview_chars] + ("..." if len(prompt) > preview_chars else "")),
				}
			)

		return {
			"searchdir": str(root),
			"selected": selected,
			"task": task,
			"stats": stats,
			"result": data,
			"warnings": warnings,
		}
	except Exception as e:
		warnings.append(f"Batch image description failed: {e}")
		return {"searchdir": str(root), "selected": selected, "task": task, "result": None, "warnings": warnings}


@tool
def find_bom_json(datasource_root: str, limit: int = 20) -> Dict[str, object]:
	"""Find *BOM*.json files in a datasource root (non-recursive, 1-level deep).

	Searches for JSON files whose stem contains "bom" in:
	- the given datasource_root directory, and
	- each immediate subdirectory of datasource_root.

	Args:
		datasource_root: Directory to scan (must be inside workspace).
		limit: Max number of matches returned.

	Returns:
		Dict with keys:
		- datasource_root: resolved directory path
		- matches: list of {file_name, file_path, parent_dir}
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	root, err = _resolve_and_validate_dir(datasource_root)
	if err:
		return {"datasource_root": str(datasource_root), "matches": [], "warnings": [err]}

	matches: List[Dict[str, str]] = []

	def scan_dir(d: Path) -> None:
		for p in sorted(d.glob("*.json"), key=lambda x: x.name.lower()):
			if "bom" in p.stem.lower():
				matches.append({"file_name": p.name, "file_path": str(p), "parent_dir": d.name})

	scan_dir(root)
	try:
		for sub in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda x: x.name.lower()):
			scan_dir(sub)
	except Exception as e:
		warnings.append(f"Could not iterate subfolders of '{root}': {e}")

	seen: set[str] = set()
	deduped: List[Dict[str, str]] = []
	for m in matches:
		key = m.get("file_path", "")
		if key and key not in seen:
			seen.add(key)
			deduped.append(m)

	if limit is not None and limit > 0:
		deduped = deduped[: int(limit)]
	if not deduped:
		warnings.append(f"No *BOM*.json found in {root} or its immediate subfolders")
	return {"datasource_root": str(root), "matches": deduped, "warnings": warnings}


@tool
def resolve_stepparser_layout(datasource_root: str) -> Dict[str, object]:
	"""Resolve the deterministic folder layout produced by the stepparser pipeline.

	This reduces token/tool-call overhead by avoiding directory discovery in the agent.

	Expected layouts (both supported):
	1) datasource_root is the *assembly parent* directory, containing:
	   - one '*.STEP' directory (assembly images + BOM + assembly metadata)
	   - multiple 'Part_*' directories
	2) datasource_root is already the '*.STEP' directory itself.

	Non-recursive: only inspects the given directory (and at most its parent once).

	Args:
		datasource_root: Either the assembly parent directory OR the '*.STEP' directory.

	Returns:
		Dict with keys:
		- datasource_root: resolved input directory
		- assembly_parent_dir: resolved parent directory that contains Part_* dirs
		- assembly_dir: resolved '*.STEP' directory
		- bom_json_path: resolved '*-BOM.json' path (or None)
		- assembly_metadata_path: resolved assembly metadata json path (or None)
		- part_dirs: sorted list of resolved Part_* directory paths
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	root, err = _resolve_and_validate_dir(datasource_root)
	if err:
		return {
			"datasource_root": str(datasource_root),
			"assembly_parent_dir": None,
			"assembly_dir": None,
			"bom_json_path": None,
			"assembly_metadata_path": None,
			"part_dirs": [],
			"warnings": [err],
		}

	def _is_step_dir(p: Path) -> bool:
		name = p.name.lower()
		return p.is_dir() and name.endswith(".step")

	assembly_dir: Optional[Path] = None
	assembly_parent: Optional[Path] = None

	if _is_step_dir(root):
		assembly_dir = root
		assembly_parent = root.parent
	else:
		assembly_parent = root
		step_dirs = sorted([p for p in root.iterdir() if _is_step_dir(p)], key=lambda p: p.name.lower())
		if not step_dirs:
			warnings.append("No '*.STEP' directory found under datasource_root")
			assembly_dir = None
		else:
			assembly_dir = step_dirs[0]
			if len(step_dirs) > 1:
				warnings.append(f"Multiple '*.STEP' directories found; using first: {assembly_dir.name}")

	part_dirs: List[Path] = []
	if assembly_parent and assembly_parent.exists() and assembly_parent.is_dir():
		try:
			candidates = [p for p in assembly_parent.iterdir() if p.is_dir() and p.name.lower().startswith("part_")]
			def _part_sort_key(p: Path) -> Tuple[int, str]:
				m = re.match(r"(?i)^part_(\d+)$", p.name.strip())
				if m:
					try:
						return (int(m.group(1)), p.name.lower())
					except Exception:
						return (10**9, p.name.lower())
				return (10**9, p.name.lower())
			part_dirs = sorted(candidates, key=_part_sort_key)
		except Exception as e:
			warnings.append(f"Could not list Part_* directories: {e}")

	bom_json_path: Optional[Path] = None
	assembly_metadata_path: Optional[Path] = None
	if assembly_dir and assembly_dir.exists() and assembly_dir.is_dir():
		# BOM: prefer '*-BOM.json', but accept any '*BOM*.json'
		bom_candidates = sorted([p for p in assembly_dir.glob("*-BOM.json") if p.is_file()], key=lambda p: p.name.lower())
		if not bom_candidates:
			bom_candidates = sorted([p for p in assembly_dir.glob("*BOM*.json") if p.is_file()], key=lambda p: p.name.lower())
		if bom_candidates:
			bom_json_path = bom_candidates[0]
			if len(bom_candidates) > 1:
				warnings.append(f"Multiple BOM JSONs found; using first: {bom_json_path.name}")
		else:
			warnings.append("No '*-BOM.json' (or '*BOM*.json') found in assembly_dir")

		# Assembly metadata: prefer stepparser variant
		meta_candidates = sorted([p for p in assembly_dir.glob("*-Metadata_assembly_stepparser.json") if p.is_file()], key=lambda p: p.name.lower())
		if not meta_candidates:
			meta_candidates = sorted([p for p in assembly_dir.glob("*-Metadata_assembly.json") if p.is_file()], key=lambda p: p.name.lower())
		if meta_candidates:
			assembly_metadata_path = meta_candidates[0]
			if len(meta_candidates) > 1:
				warnings.append(f"Multiple assembly metadata JSONs found; using first: {assembly_metadata_path.name}")

	return {
		"datasource_root": str(root),
		"assembly_parent_dir": str(assembly_parent) if assembly_parent else None,
		"assembly_dir": str(assembly_dir) if assembly_dir else None,
		"bom_json_path": str(bom_json_path) if bom_json_path else None,
		"assembly_metadata_path": str(assembly_metadata_path) if assembly_metadata_path else None,
		"part_dirs": [str(p) for p in part_dirs],
		"warnings": warnings,
	}


@tool
def load_json_texts(searchdir: str, keywords: List[str]) -> Dict[str, object]:
	"""Load JSON files from a single directory by keyword (non-recursive).

	Finds files in `searchdir` whose filename stem contains any keyword (case-insensitive)
	and returns their content pretty-printed as JSON text.

	Args:
		searchdir: Directory to scan (no recursion).
		keywords: Keywords to match against JSON filename stems.

	Returns:
		Dict with keys:
		- searchdir: resolved directory
		- json: dict keyword -> list[{file_name, file_path, json_text}]
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	try:
		loader = JsonLoader(searchdir)
	except Exception as e:
		return {"searchdir": str(searchdir), "json": {k: [] for k in (keywords or [])}, "warnings": [f"Invalid searchdir: {e}"]}

	loaded, load_warnings = loader.find_and_load(keywords)
	warnings.extend(load_warnings)
	return {"searchdir": str(loader.search_dir), "json": loaded, "warnings": warnings}


@tool
def list_directories_and_files(searchdir: str) -> Dict[str, object]:
	"""List files in a directory and files in its immediate subdirectories.

	This is a NON-RECURSIVE inspector used to discover folder structure.
	It returns:
	- files directly under `searchdir`
	- for each immediate subfolder: the files directly inside that subfolder

	Args:
		searchdir: Directory to list.

	Returns:
		Dict with keys:
		- searchdir: resolved directory
		- files: list of filenames in the root
		- directories: dict subdir_name -> list of filenames
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	root = Path(searchdir)
	if not root.exists() or not root.is_dir():
		return {"searchdir": str(searchdir), "files": [], "directories": {}, "warnings": [f"Invalid searchdir: not a directory: {root}"]}

	try:
		children = list(root.iterdir())
	except Exception as e:
		return {"searchdir": str(root), "files": [], "directories": {}, "warnings": [f"Could not list directory '{root}': {e}"]}

	root_files = sorted([p.name for p in children if p.is_file()], key=str.lower)
	directories: Dict[str, List[str]] = {}
	for d in sorted([p for p in children if p.is_dir()], key=lambda p: p.name.lower()):
		try:
			files_in_dir = sorted([p.name for p in d.iterdir() if p.is_file()], key=str.lower)
			directories[d.name] = files_in_dir
		except Exception as e:
			directories[d.name] = []
			warnings.append(f"Could not list files in '{d}': {e}")

	return {"searchdir": str(root), "files": root_files, "directories": directories, "warnings": warnings}


@tool
def read_json_file(file_path: str) -> Dict[str, object]:
	"""Read a JSON file from disk (workspace-safe).

	The path is validated to ensure it is inside the workspace root.

	Args:
		file_path: Absolute path or workspace-relative path to a JSON file.

	Returns:
		Dict with keys:
		- file_path: resolved path
		- data: parsed JSON object (or None on error)
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	p, err = _resolve_and_validate_path(file_path)
	if err:
		return {"file_path": str(file_path), "data": None, "warnings": [err]}
	if not p.exists() or not p.is_file():
		return {"file_path": str(p), "data": None, "warnings": [f"File not found: {p}"]}

	try:
		with open(p, "r", encoding="utf-8") as f:
			data = json.load(f)
		return {"file_path": str(p), "data": data, "warnings": warnings}
	except Exception as e:
		return {"file_path": str(p), "data": None, "warnings": [f"Could not read/parse JSON: {e}"]}


@tool
def write_json_file(file_path: str, data: Dict[str, object], overwrite: bool = False) -> Dict[str, object]:
	"""Write a JSON file to disk (workspace-safe).

	The path is validated to ensure it is inside the workspace root.
	If overwrite is False and the target exists, a new sibling file is created:
	- <name>_updated.json (or _updated_2, ...)

	Args:
		file_path: Absolute path or workspace-relative path to a JSON file.
		data: JSON-serializable object to write.
		overwrite: If True, overwrite the target path if it exists.

	Returns:
		Dict with keys:
		- written_path: final path written
		- overwritten: bool
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	p, err = _resolve_and_validate_path(file_path)
	if err:
		return {"written_path": str(file_path), "overwritten": False, "warnings": [err]}
	if p.suffix.lower() != ".json":
		warnings.append(f"Target does not end with .json, writing anyway: {p.name}")
	p.parent.mkdir(parents=True, exist_ok=True)

	target = p
	overwritten = False
	if target.exists() and not overwrite:
		stem = target.stem
		candidate = target.with_name(f"{stem}_updated{target.suffix}")
		idx = 2
		while candidate.exists():
			candidate = target.with_name(f"{stem}_updated_{idx}{target.suffix}")
			idx += 1
		target = candidate
	elif target.exists() and overwrite:
		overwritten = True

	try:
		with open(target, "w", encoding="utf-8") as f:
			json.dump(data, f, indent=2, ensure_ascii=False)
		return {"written_path": str(target), "overwritten": overwritten, "warnings": warnings}
	except Exception as e:
		return {"written_path": str(target), "overwritten": False, "warnings": [f"Could not write JSON: {e}"]}


def _metadata_assembly_filename(assembly_dir: Path) -> str:
	"""Return the conventional (base) metadata filename for an assembly image directory."""
	return f"{assembly_dir.name}-Metadata_assembly.json"


def _metadata_assembly_enriched_filename(assembly_dir: Path) -> str:
	"""Return the conventional enriched metadata filename for an assembly image directory."""
	# Strip .STEP extension and use underscores for clean naming
	clean_name = assembly_dir.name.replace('.STEP', '').replace('.step', '')
	return f"{clean_name}_Overview_Enriched.json"


def _metadata_monopart_enriched_filename(part_dir: Path) -> str:
	"""Return the conventional enriched metadata filename for a monopart image directory."""
	return f"{part_dir.name}_Data_enriched.json"


def _write_json_atomic(path: Path, data: object) -> None:
	"""Write JSON atomically via a temporary file + os.replace()."""
	tmp = path.with_suffix(path.suffix + ".tmp")
	tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8", errors="replace")
	os.replace(str(tmp), str(path))


def save_structured_json(
	output_path: Path | str,
	data: object,
	schema: Optional[object] = None,
	add_metadata: bool = True,
	atomic: bool = True
) -> None:
	"""
	Universal JSON saver for Pydantic models and dicts.
	
	Automatically:
	- Detects Pydantic models and uses .model_dump()
	- Adds schema metadata (name, version, timestamp)
	- Supports atomic writes (via temp file)
	- Handles nested models correctly
	
	Args:
		output_path: Where to save JSON
		data: Pydantic model instance or dict
		schema: Optional Pydantic model class for metadata (auto-detected if data is model)
		add_metadata: Add _schema_info metadata to JSON
		atomic: Use atomic write (temp file + rename)
	
	Examples:
		# Pydantic model
		sequence = AssemblySequence(...)
		save_structured_json("output.json", sequence)
		
		# Dict with schema reference
		save_structured_json("output.json", my_dict, schema=AssemblySequence)
		
		# No metadata
		save_structured_json("output.json", my_dict, add_metadata=False)
	"""
	from pathlib import Path
	from datetime import datetime, timezone
	from pydantic import BaseModel
	
	output_path = Path(output_path)
	output_path.parent.mkdir(parents=True, exist_ok=True)
	
	# Auto-detect Pydantic model and extract data
	if isinstance(data, BaseModel):
		if schema is None:
			schema = type(data)
		json_data = data.model_dump()
	elif hasattr(data, "model_dump"):  # Duck typing for Pydantic v2
		if schema is None:
			schema = type(data)
		json_data = data.model_dump()
	elif isinstance(data, dict):
		json_data = data
	else:
		# Fallback: try to convert to dict
		json_data = dict(data) if hasattr(data, "__dict__") else data
	
	# Add schema metadata
	if add_metadata and schema is not None:
		schema_name = getattr(schema, "__name__", str(schema))
		schema_module = getattr(schema, "__module__", "unknown")
		
		# Get schema fields if Pydantic
		schema_fields = None
		if hasattr(schema, "model_fields"):
			schema_fields = list(schema.model_fields.keys())
		
		metadata_info = {
			"schema_name": schema_name,
			"schema_module": schema_module,
			"schema_fields": schema_fields,
			"created_at": datetime.now(timezone.utc).isoformat(),
			"format_version": "1.0"
		}
		
		# Insert at top of JSON (if dict)
		if isinstance(json_data, dict):
			json_data = {"_schema_info": metadata_info, **json_data}
	
	# Write JSON
	if atomic:
		_write_json_atomic(output_path, json_data)
	else:
		with open(output_path, "w", encoding="utf-8") as f:
			json.dump(json_data, f, indent=2, ensure_ascii=False)


def _get_experiment_output_dir() -> Optional[Path]:
	"""Get experiment output directory from environment variable.
	
	Returns None if not set (fallback to stepparser directory).
	"""
	exp_output = os.environ.get("APA_EXPERIMENT_OUTPUT_DIR")
	if exp_output:
		return Path(exp_output)
	return None


def _save_assembly_metadata_enriched(assembly_dir: Path, metadata: Dict[str, object], overwrite: bool) -> Tuple[Optional[Path], List[str]]:
	"""Save enriched assembly metadata JSON.
	
	If APA_EXPERIMENT_OUTPUT_DIR is set, writes to experiment folder.
	Otherwise, writes to assembly_dir (backward compatibility).
	"""
	warnings: List[str] = []
	
	# Determine output directory
	exp_output_dir = _get_experiment_output_dir()
	if exp_output_dir:
		# Experiment mode: write to data/experiments/{exp_name}/{assembly_name}/
		output_dir = exp_output_dir
		output_dir.mkdir(parents=True, exist_ok=True)
	else:
		# Legacy mode: write to stepparser directory
		output_dir = assembly_dir
	
	target = output_dir / _metadata_assembly_enriched_filename(assembly_dir)

	if target.exists() and not overwrite:
		idx = 2
		candidate = target.with_name(f"{target.stem}_{idx}{target.suffix}")
		while candidate.exists():
			idx += 1
			candidate = target.with_name(f"{target.stem}_{idx}{target.suffix}")
		target = candidate

	try:
		from agent.structured_output import AssemblyAnalysis
		save_structured_json(target, metadata, schema=AssemblyAnalysis, add_metadata=True)
		return target, warnings
	except Exception as e:
		warnings.append(f"Could not write assembly metadata JSON '{target.name}': {e}")
		return None, warnings


def _save_monopart_metadata_enriched(part_dir: Path, metadata: Dict[str, object]) -> Tuple[Optional[Path], List[str]]:
	"""Save enriched monopart metadata JSON.
	
	If APA_EXPERIMENT_OUTPUT_DIR is set, writes to experiment folder/enriched_parts/.
	Otherwise, writes to part_dir (backward compatibility).
	"""
	warnings: List[str] = []
	
	# Determine output directory
	exp_output_dir = _get_experiment_output_dir()
	if exp_output_dir:
		# Experiment mode: write to data/experiments/{exp_name}/{assembly_name}/enriched_parts/
		output_dir = exp_output_dir / "enriched_parts"
		output_dir.mkdir(parents=True, exist_ok=True)
	else:
		# Legacy mode: write to stepparser directory
		output_dir = part_dir
	
	target = output_dir / _metadata_monopart_enriched_filename(part_dir)
	try:
		from agent.structured_output import SinglePartAnalysis
		save_structured_json(target, metadata, schema=SinglePartAnalysis, add_metadata=True)
		return target, warnings
	except Exception as e:
		warnings.append(f"Could not write monopart metadata JSON '{target.name}': {e}")
		return None, warnings


def _find_assembly_metadata_for_part_dir(part_dir: Path, pattern: str) -> Tuple[Optional[Path], List[str]]:
	"""Find an assembly metadata JSON file near a part directory.

	Search strategy:
	1. If APA_EXPERIMENT_OUTPUT_DIR is set, look in experiment output directory first
	2. Look in the part_dir itself
	3. Look in each immediate sibling directory under part_dir.parent
	Prefer a match inside a directory whose name contains '.STEP'.
	"""
	warnings: List[str] = []
	root = part_dir

	def _glob_in_dir(d: Path) -> List[Path]:
		try:
			return sorted([p for p in d.glob(pattern) if p.is_file()], key=lambda p: p.name.lower())
		except Exception:
			return []

	# 0) Check experiment output directory first
	exp_output_dir = _get_experiment_output_dir()
	if exp_output_dir:
		exp_matches = _glob_in_dir(exp_output_dir)
		if exp_matches:
			return exp_matches[0], warnings

	# 1) local
	local = _glob_in_dir(root)
	if local:
		return local[0], warnings

	# 2) siblings under parent
	parent = part_dir.parent
	step_candidates: List[Path] = []
	other_candidates: List[Path] = []
	try:
		for d in sorted([p for p in parent.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
			found = _glob_in_dir(d)
			if not found:
				continue
			if ".step" in d.name.lower():
				step_candidates.extend(found)
			else:
				other_candidates.extend(found)
	except Exception as e:
		warnings.append(f"Could not scan sibling dirs for Metadata_assembly: {e}")

	all_candidates = step_candidates + other_candidates
	if not all_candidates:
		warnings.append(f"No '{pattern}' found near part directory")
		return None, warnings
	if len(all_candidates) > 1:
		warnings.append(f"Multiple Metadata_assembly JSONs found; using first: {all_candidates[0].name}")
	return all_candidates[0], warnings


def _find_assembly_images_for_part_dir(
	part_dir: Path,
	keywords: List[str],
	limit: int = 4,
) -> Tuple[List[Path], List[str]]:
	"""Find assembly reference images near a part directory.

	Looks for .png files matching any of `keywords` in the sibling *.STEP directory
	(the directory that contains the full-assembly renderings).

	Args:
		part_dir: The monopart directory (e.g. .../stepparser/MyAssy/Part_001/).
		keywords: Filename substrings to match (case-insensitive).
		limit: Maximum number of images to return (0 = no limit).

	Returns:
		(list_of_image_paths, warnings)
	"""
	warnings: List[str] = []
	if not keywords:
		return [], warnings

	parent = part_dir.parent

	# Locate the assembly image directory among siblings.
	# Supports two naming conventions:
	#   1. assembly_*  (e.g. assembly_MyAssy/)   ← current stepparser output
	#   2. *.STEP      (e.g. MyAssy.STEP/)        ← legacy convention
	candidate_dirs: List[Path] = []
	try:
		step_dirs: List[Path] = []
		for sibling in sorted(parent.iterdir(), key=lambda p: p.name.lower()):
			if not sibling.is_dir():
				continue
			name_lc = sibling.name.lower()
			if name_lc.startswith("assembly_"):
				candidate_dirs.append(sibling)
			elif name_lc.endswith(".step"):
				step_dirs.append(sibling)
		# Prefer assembly_* over *.STEP; fall back to *.STEP if no assembly_* found
		if not candidate_dirs:
			candidate_dirs = step_dirs
	except Exception as e:
		warnings.append(f"Could not scan siblings for assembly images: {e}")

	if not candidate_dirs:
		warnings.append(
			f"No 'assembly_*' or '*.STEP' sibling directory found near '{part_dir.name}' – assembly images skipped"
		)
		return [], warnings

	if len(candidate_dirs) > 1:
		warnings.append(f"Multiple assembly image dirs found; using first: {candidate_dirs[0].name}")

	assy_dir = candidate_dirs[0]

	# Collect .png files matching any keyword
	images: List[Path] = []
	try:
		for img in sorted(assy_dir.glob("*.png"), key=lambda p: p.name.lower()):
			if any(kw.lower() in img.name.lower() for kw in keywords):
				images.append(img)
				if limit > 0 and len(images) >= limit:
					break
	except Exception as e:
		warnings.append(f"Could not scan '{assy_dir.name}' for assembly images: {e}")

	if not images:
		warnings.append(f"No assembly images matching {keywords!r} found in '{assy_dir.name}'")

	return images, warnings


@tool
def analyse_assembly_img(
	searchdir: str,
	keywords: Optional[List[str]] = None,
	limit: int = 8,
	overwrite_metadata: bool = True,
	additional_context_block: Optional[str] = None,
) -> Dict[str, object]:
	"""Analyse assembly images in a single directory and persist enriched structured metadata JSON.

	- Scans ONLY `searchdir` (non-recursive) for images.
	- Applies view filtering and prompt variants via experiment settings.
	- Produces ONE unified AssemblyAnalysis (structured output).
	- If experiment setting `AAI_use_assembly_metadata` is True, loads an existing assembly metadata JSON
	  from the same folder and appends it to the prompt as ASSEMBLY_METADATA_JSON.
	  Supported base filenames (searched in this order):
	  - `*-Metadata_assembly_stepparser.json`
	  - `*-Metadata_assembly.json`
	- Saves a combined JSON into `*-Metadata_assembly_enriched.json` in the SAME directory as the images:
	  it contains BOTH the loaded base metadata (if any) and the newly generated structured analysis.

	Args:
		searchdir: Directory containing the assembly images (workspace-safe).
		keywords: Optional filename keywords to pre-filter images (case-insensitive). If empty/None, all images are eligible.
		limit: Max number of images to send to the vision model (after filtering).
		overwrite_metadata: If True, overwrite existing enriched metadata file; otherwise create a numbered variant.

	Returns:
		Dict with keys:
		- searchdir: resolved directory
		- metadata_used_path: base metadata path injected (or None)
		- metadata_written_path: enriched metadata path written (or None)
		- analysis: result dict from the batch describer
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	root, err = _resolve_and_validate_dir(searchdir)
	if err:
		return {"searchdir": str(searchdir), "metadata_used_path": None, "metadata_written_path": None, "analysis": None, "warnings": [err]}

	settings = _get_experiment_settings()
	# NEW: JSON handling with extract_json_keys_from_file
	json_file_keyword = settings.get("AAI_json_file_keyword", "assembly_enriched")
	json_keys = settings.get("AAI_json_keys", ["assembly_name", "primary_function"])
	part_id_list = settings.get("AAI_part_id_list", [])

	# Persisting enriched metadata is independent from whether we inject it into the prompt.
	# We always try to load the base (prefer stepparser) so the enriched file can be the base + appended LLM output.
	metadata_used_path: Optional[Path] = None
	context_json: Optional[str] = None
	base_metadata_obj: Optional[object] = None
	extracted_data: Optional[dict] = None
	metadata_injected: Dict[str, object] = {
		"json_file_keyword": json_file_keyword,
		"json_keys": json_keys,
		"part_id_list": part_id_list,
		"metadata_path": None,
		"metadata_bytes": None,
		"metadata_injected_into_prompt": False,
		"metadata_top_level_key_count": None,
	}

	# Find JSON file matching keyword
	patterns = ["*-Metadata_assembly_stepparser.json", "*-Metadata_assembly.json"]
	candidates: List[Path] = []
	for json_file in root.glob("*.json"):
		if json_file_keyword.lower() in json_file.name.lower():
			candidates.append(json_file)
			break
	# Fallback to old patterns if no match
	if not candidates:
		seen: set[str] = set()
		for pattern in patterns:
			for p in sorted([p for p in root.glob(pattern) if p.is_file()], key=lambda p: p.name.lower()):
				key = str(p.resolve())
				if key in seen:
					continue
				seen.add(key)
				candidates.append(p)
				break

	if candidates:
		metadata_used_path = candidates[0]
		try:
			metadata_injected["metadata_path"] = str(metadata_used_path)
			metadata_injected["metadata_bytes"] = int(metadata_used_path.stat().st_size)
		except Exception:
			pass
		if len(candidates) > 1:
			warnings.append(f"Multiple assembly metadata JSONs found; using first: {metadata_used_path.name}")
		try:
			# Load full JSON for base metadata (enriched file needs complete base)
			with open(metadata_used_path, "r", encoding="utf-8") as f:
				data = json.load(f)
			base_metadata_obj = data
			
			# Extract only specified keys for prompt injection
			extracted_data = extract_json_keys_from_file(metadata_used_path, json_keys, part_id_list)
			
			if isinstance(extracted_data, dict):
				try:
					keys = list(extracted_data.keys())
					metadata_injected["metadata_top_level_key_count"] = len(keys)
				except Exception:
					pass
				context_json = _format_assembly_context_json(extracted_data)
				metadata_injected["metadata_injected_into_prompt"] = True
		except Exception as e:
			warnings.append(f"Could not read/parse assembly metadata JSON '{metadata_used_path.name}': {e}")
			base_metadata_obj = None
			context_json = None
	else:
		warnings.append(f"No assembly metadata JSON found matching keyword '{json_file_keyword}' or fallback patterns")

	# Load BOM enriched JSON as separate context block
	bom_context_json: Optional[str] = None
	bom_path: Optional[Path] = None
	bom_candidates: List[Path] = []
	
	# Search for BOM file (typically {assembly_name}_BOM_enriched.json)
	for bom_file in sorted(root.glob("*BOM_enriched.json")):
		bom_candidates.append(bom_file)
		break
	
	# Fallback search patterns
	if not bom_candidates:
		for pattern in ["*_BOM_enriched.json", "*_BOM.json", "*BOM*.json"]:
			for p in sorted(root.glob(pattern)):
				if p not in bom_candidates and p.is_file():
					bom_candidates.append(p)
					break
	
	if bom_candidates:
		bom_path = bom_candidates[0]
		try:
			with open(bom_path, "r", encoding="utf-8") as f:
				bom_data = json.load(f)
			
			# Stepparser now generates clean metadata at the source:
			# - No 'directory' field
			# - bounding_box is already simplified (x, y, z values directly)
			# No post-processing needed
			
			# Format BOM for prompt (potentially truncate if very large)
			bom_json_str = json.dumps(bom_data, indent=2)
			if len(bom_json_str) > 25000:  # Truncate large BOMs
				bom_json_str = bom_json_str[:25000] + "\n... (truncated due to size)"
			bom_context_json = bom_json_str
		except Exception as e:
			warnings.append(f"Could not read BOM JSON '{bom_path.name}': {e}")
			bom_context_json = None
	else:
		warnings.append(f"No BOM enriched JSON found (*BOM_enriched.json patterns)")

	# Load optional assembly text context. The loader prefers
	# data/ground_truth/assembly_sequence_ground_truth/{assembly}/ and falls
	# back to data/input/Textbased_Data/{assembly}/.
	additional_info_context: Optional[str] = None
	if bool(settings.get("AAI_use_additional_info", True)):
		try:
			from agent.core.text_processor import load_additional_info
			assembly_name_guess = root.parent.name
			if root.name.lower().startswith("assembly_"):
				assembly_name_guess = root.name[len("assembly_"):]
			elif root.name.lower().endswith(".step"):
				assembly_name_guess = root.name[:-5]
			additional_info_context = load_additional_info(assembly_name_guess)
		except Exception as e:
			warnings.append(f"Could not load additional assembly info: {e}")
	
	# Build context blocks with both assembly metadata and BOM
	context_blocks: List[Tuple[str, str]] = []
	if context_json:
		context_blocks.append(("ASSEMBLY_METADATA_JSON", context_json))
	if bom_context_json:
		context_blocks.append(("BOM_ENRICHED", bom_context_json))
	if additional_info_context:
		context_blocks.append(("ADDITIONAL_ASSEMBLY_INFO", additional_info_context))
	
	out = _describe_images_in_dir_impl(
		root=root,
		keywords=[str(k) for k in (keywords or []) if str(k).strip()],
		task="AssemblyAnalysis",
		limit=limit,
		context_blocks=context_blocks if context_blocks else None,
		allow_all_if_no_keywords=True,
		additional_context_block=additional_context_block,
	)
	warnings.extend(out.get("warnings", []) if isinstance(out, dict) else [])

	metadata_path: Optional[Path] = None
	if isinstance(out, dict) and isinstance(out.get("result"), dict):
		# Merge stepparser + enriched metadata (flatten "analysis" wrapper)
		enriched_payload = out.get("result")
		
		# Load stepparser metadata
		stepparser_metadata = {}
		if base_metadata_obj:
			stepparser_metadata = base_metadata_obj.copy()
		
		# Flatten LLM analysis (unwrap "analysis" key if present)
		llm_data = enriched_payload.get("analysis", enriched_payload) if isinstance(enriched_payload, dict) else {}
		
		# Merge: stepparser data + flattened LLM analysis
		merged_data = {**stepparser_metadata, **llm_data}
		
		metadata_path, save_warnings = _save_assembly_metadata_enriched(root, merged_data, overwrite=bool(overwrite_metadata))
		warnings.extend(save_warnings)
	else:
		warnings.append("No assembly result produced; metadata JSON not written")

	return {
		"searchdir": str(root),
		"metadata_used_path": str(metadata_used_path) if metadata_used_path else None,
		"metadata_written_path": str(metadata_path) if metadata_path else None,
		"metadata_injected": metadata_injected,
		"metadata_files_in_prompt": (
			[
				{
					"label": "ASSEMBLY_METADATA_JSON",
					"path": str(metadata_used_path),
					"bytes": metadata_injected.get("metadata_bytes"),
				}
			]
			if (metadata_used_path and bool(metadata_injected.get("metadata_injected_into_prompt")))
			else []
		),
		"metadata": (
			[
				f"ASSEMBLY_METADATA_JSON:{str(metadata_used_path)}"
			]
			if (metadata_used_path and bool(metadata_injected.get("metadata_injected_into_prompt")))
			else []
		),
		"analysis": out,
		"warnings": warnings,
	}


@tool
def analyse_monopart_img(
	searchdir: str,
	keywords: Optional[List[str]] = None,
	limit: int = 8,
	additional_context_block: Optional[str] = None,
) -> Dict[str, object]:
	"""Analyse part images in a single directory, optionally injecting assembly context.

	- Scans ONLY `searchdir` (non-recursive) for images.
	- Applies view filtering and prompt variants via experiment settings.
	- Produces ONE unified SinglePartAnalysis (structured output).
	- Experiment setting `AMI_use_monopart_metadata` controls whether and which monopart metadata JSON is injected:
	  - "None": do not inject any assembly metadata
	  - "Stepparser": inject `*Metadata_stepparser.json`
	  - "Enriched_Features": inject `*Metadata_Enriched_Features.json` (may not exist yet)
	- Experiment setting `AMI_use_assembly_metadata` controls whether and which assembly metadata JSON is injected:
	  - "None": do not inject assembly metadata
	  - "Stepparser": inject `*Metadata_assembly_stepparser.json`
	  - "Enriched": inject `*Metadata_assembly_enriched.json`
	
	Monopart metadata is loaded from the part directory itself.
	Assembly metadata is located via simple Python search (non-recursive, 1-level deep) near the part directory.

	Args:
		searchdir: Directory containing the part images (workspace-safe).
		keywords: Optional filename keywords to pre-filter images (case-insensitive). If empty/None, all images are eligible.
		limit: Max number of images to send to the vision model (after filtering).

	Returns:
		Dict with keys:
		- searchdir: resolved directory
		- metadata_path: resolved metadata json path used (or None)
		- assembly_metadata_path: resolved assembly metadata json path used (or None)
		- analysis: result dict from the batch describer
		- warnings: list of warning strings
	"""
	warnings: List[str] = []
	root, err = _resolve_and_validate_dir(searchdir)
	if err:
		return {
			"searchdir": str(searchdir),
			"metadata_path": None,
			"assembly_metadata_path": None,
			"analysis": None,
			"warnings": [err],
		}

	settings = _get_experiment_settings()
	# NEW: JSON handling with extract_json_keys_from_file
	mono_json_file_keyword = settings.get("AMI_json_file_keyword", "Metadata_stepparser")
	mono_json_keys = settings.get("AMI_json_keys", ["part_id", "volume", "bounding_box"])
	mono_part_id_list = settings.get("AMI_part_id_list", [])

	context_blocks: List[Tuple[str, str]] = []
	metadata_path: Optional[Path] = None
	assembly_metadata_path: Optional[Path] = None
	metadata_written_path: Optional[Path] = None
	base_monopart_obj: Optional[object] = None
	metadata_injected: Dict[str, object] = {
		"monopart": {
			"json_file_keyword": mono_json_file_keyword,
			"json_keys": mono_json_keys,
			"part_id_list": mono_part_id_list,
			"metadata_path": None,
			"metadata_bytes": None,
			"metadata_injected_into_prompt": False,
			"metadata_top_level_key_count": None,
		},
		"assembly": {
			"metadata_path": None,
			"metadata_bytes": None,
			"metadata_injected_into_prompt": False,
			"metadata_top_level_key_count": None,
		},
	}

	# Find monopart JSON file matching keyword
	candidates = []
	for json_file in root.glob("*.json"):
		if mono_json_file_keyword.lower() in json_file.name.lower():
			candidates.append(json_file)
			break

	if candidates:
		metadata_path = candidates[0]
		try:
			metadata_injected["monopart"]["metadata_path"] = str(metadata_path)
			metadata_injected["monopart"]["metadata_bytes"] = int(metadata_path.stat().st_size)
		except Exception:
			pass
		if len(candidates) > 1:
			warnings.append(f"Multiple '{mono_json_file_keyword}' found; using first: {metadata_path.name}")
		try:
			# Load full JSON for base metadata (enriched file needs complete base)
			with open(metadata_path, "r", encoding="utf-8") as f:
				data = json.load(f)
			base_monopart_obj = data
			
			# Extract only specified keys for prompt injection
			extracted_data = extract_json_keys_from_file(metadata_path, mono_json_keys, mono_part_id_list)
			
			if isinstance(extracted_data, dict):
				metadata_injected["monopart"]["metadata_top_level_key_count"] = len(list(extracted_data.keys()))
				mono_json = _format_assembly_context_json(extracted_data)
				context_blocks.append(("MONOPART_METADATA_JSON", mono_json))
				metadata_injected["monopart"]["metadata_injected_into_prompt"] = True
		except Exception as e:
			warnings.append(f"Could not read/parse monopart metadata JSON '{metadata_path.name}': {e}")
			pass
	else:
		warnings.append(f"No monopart metadata JSON found matching keyword '{mono_json_file_keyword}'")

	# Assembly metadata from parent directories - NEW: Use extract_json_keys_from_file
	assembly_json_file_keyword = settings.get("AMI_assembly_json_file_keyword", "Metadata_assembly_stepparser")
	assembly_json_keys = settings.get("AMI_assembly_json_keys", ["assembly_name", "primary_function"])
	assembly_part_id_list = settings.get("AMI_assembly_part_id_list", [])

	# Find assembly JSON in parent directories
	assembly_metadata_path, find_warnings = _find_assembly_metadata_for_part_dir(root, pattern=f"*{assembly_json_file_keyword}*.json")
	warnings.extend(find_warnings)
	
	if assembly_metadata_path and assembly_metadata_path.exists() and assembly_metadata_path.is_file():
		try:
			metadata_injected["assembly"]["metadata_path"] = str(assembly_metadata_path)
			metadata_injected["assembly"]["metadata_bytes"] = int(assembly_metadata_path.stat().st_size)
		except Exception:
			pass
		try:
			# Extract only specified keys for prompt injection
			extracted_assy_data = extract_json_keys_from_file(assembly_metadata_path, assembly_json_keys, assembly_part_id_list)
			
			if isinstance(extracted_assy_data, dict):
				metadata_injected["assembly"]["metadata_top_level_key_count"] = len(list(extracted_assy_data.keys()))
				assy_json = _format_assembly_context_json(extracted_assy_data)
				context_blocks.append(("ASSEMBLY_METADATA_JSON", assy_json))
				metadata_injected["assembly"]["metadata_injected_into_prompt"] = True
		except Exception as e:
			warnings.append(f"Could not read/parse assembly metadata JSON '{assembly_metadata_path.name}': {e}")

	# Assembly reference images (optional) – loaded from the sibling *.STEP directory
	raw_assy_img_kws = settings.get("AMI_assembly_img_keywords")
	assy_img_limit = int(settings.get("AMI_assembly_img_limit") or 4)
	extra_images: List[Path] = []
	if raw_assy_img_kws:
		assy_img_kws = [str(k) for k in raw_assy_img_kws if str(k).strip()]
		if assy_img_kws:
			found_imgs, img_warns = _find_assembly_images_for_part_dir(root, assy_img_kws, limit=assy_img_limit)
			extra_images.extend(found_imgs)
			warnings.extend(img_warns)
			if found_imgs:
				metadata_injected["assembly"]["assembly_images_count"] = len(found_imgs)
				metadata_injected["assembly"]["assembly_images_names"] = [p.name for p in found_imgs]

	out = _describe_images_in_dir_impl(
		root=root,
		keywords=[str(k) for k in (keywords or []) if str(k).strip()],
		task="SinglePartAnalysis",
		limit=limit,
		context_blocks=context_blocks,
		allow_all_if_no_keywords=True,
		extra_images=extra_images or None,
		extra_images_label="ASSEMBLY_REFERENCE_IMAGES",
		additional_context_block=additional_context_block,
	)
	warnings.extend(out.get("warnings", []) if isinstance(out, dict) else [])

	# Persisting enriched monopart metadata is independent from whether metadata was injected into the prompt.
	# Always try to load existing *Metadata_stepparser.json so the enriched file is base + appended LLM output.
	base_candidates = sorted([p for p in root.glob("*Metadata_stepparser.json") if p.is_file()], key=lambda p: p.name.lower())
	if base_candidates:
		try:
			with open(base_candidates[0], "r", encoding="utf-8") as f:
				base_monopart_obj = json.load(f)
			if len(base_candidates) > 1:
				warnings.append(f"Multiple '*Metadata_stepparser.json' found; using first for enrichment: {base_candidates[0].name}")
		except Exception as e:
			warnings.append(f"Could not read/parse monopart base metadata JSON '{base_candidates[0].name}': {e}")
			base_monopart_obj = None

	if isinstance(out, dict) and isinstance(out.get("result"), dict):
		if isinstance(base_monopart_obj, dict):
			enriched_payload: Dict[str, object] = dict(base_monopart_obj)
		elif base_monopart_obj is not None:
			enriched_payload = {"metadata_monopart_base": base_monopart_obj}
		else:
			enriched_payload = {}
		enriched_payload["metadata_monopart_enriched"] = out.get("result")
		metadata_written_path, save_warnings = _save_monopart_metadata_enriched(root, enriched_payload)
		warnings.extend(save_warnings)
	else:
		warnings.append("No monopart result produced; metadata JSON not written")

	return {
		"searchdir": str(root),
		"metadata_path": str(metadata_path) if metadata_path else None,
		"assembly_metadata_path": str(assembly_metadata_path) if assembly_metadata_path else None,
		"metadata_written_path": str(metadata_written_path) if metadata_written_path else None,
		"metadata_injected": metadata_injected,
		"metadata_files_in_prompt": [
			*([
				{
					"label": "MONOPART_METADATA_JSON",
					"path": str(metadata_path),
					"bytes": ((metadata_injected.get("monopart") or {}).get("metadata_bytes")),
				}
			] if (metadata_path and bool(((metadata_injected.get("monopart") or {}).get("metadata_injected_into_prompt")))) else []),
			*([
				{
					"label": "ASSEMBLY_METADATA_JSON",
					"path": str(assembly_metadata_path),
					"bytes": ((metadata_injected.get("assembly") or {}).get("metadata_bytes")),
				}
			] if (assembly_metadata_path and bool(((metadata_injected.get("assembly") or {}).get("metadata_injected_into_prompt")))) else []),
		],
		"metadata": [
			*([f"MONOPART_METADATA_JSON:{str(metadata_path)}"] if (metadata_path and bool(((metadata_injected.get("monopart") or {}).get("metadata_injected_into_prompt")))) else []),
			*([f"ASSEMBLY_METADATA_JSON:{str(assembly_metadata_path)}"] if (assembly_metadata_path and bool(((metadata_injected.get("assembly") or {}).get("metadata_injected_into_prompt")))) else []),
		],
		"analysis": out,
		"warnings": warnings,
	}


@tool
def multiply(x: float, y: float) -> float:
	"""Multiply two numbers.

	Args:
		x: First factor.
		y: Second factor.

	Returns:
		The product x*y.
	"""
	return x * y


@tool
def add(x: float, y: float) -> float:
	"""Add two numbers.

	Args:
		x: First addend.
		y: Second addend.

	Returns:
		The sum x+y.
	"""
	return x + y



