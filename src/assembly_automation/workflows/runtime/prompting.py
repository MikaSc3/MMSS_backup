"""Shared prompt and configured-input assembly for LLM workflow nodes."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import mimetypes
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class PromptPayload:
    messages: list[dict[str, Any]]
    system_prompt: str
    human_prompt: str
    inputs: list[dict[str, Any]]
    images: list[str]
    prompt_hashes: dict[str, str]


def load_prompt(path: str | Path, prompt_id: str, expected_role: str) -> str:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    prompts = data.get("prompts") if isinstance(data, dict) else None
    entry = prompts.get(prompt_id) if isinstance(prompts, dict) else None
    if isinstance(entry, str):
        text, role = entry, expected_role
    elif isinstance(entry, dict):
        text, role = entry.get("text"), entry.get("role", expected_role)
    else:
        raise ValueError(f"Unknown prompt ID: {prompt_id}")
    if role != expected_role or not isinstance(text, str) or not text.strip():
        raise ValueError(f"Prompt {prompt_id!r} must be a nonempty {expected_role} prompt")
    return text.strip()


def _format(value: Any, variables: Mapping[str, Any]) -> Any:
    return value.format_map(variables) if isinstance(value, str) else value


def _get(value: Any, path: str) -> Any:
    current = value
    for component in path.split(".") if path else []:
        if isinstance(current, dict) and component in current:
            current = current[component]
        else:
            raise ValueError(f"JSON field does not exist: {path}")
    return current


def _put(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    components = path.split(".")
    for component in components[:-1]:
        current = current.setdefault(component, {})
    current[components[-1]] = value


def _select_json(value: Any, spec: Mapping[str, Any], variables: Mapping[str, Any]) -> Any:
    selector = spec.get("select")
    if selector:
        if not isinstance(selector, dict):
            raise ValueError("JSON select must be a mapping")
        candidates = _get(value, str(selector.get("path", "")))
        if not isinstance(candidates, list):
            raise ValueError("JSON select.path must identify a list")
        field = str(selector.get("field", ""))
        expected = _format(selector.get("equals"), variables)
        matches = [item for item in candidates if isinstance(item, dict) and _get(item, field) == expected]
        mode = selector.get("mode", "one")
        if mode == "one":
            if len(matches) != 1:
                raise ValueError(f"JSON selector expected one match, found {len(matches)}")
            value = matches[0]
        elif mode == "all":
            value = matches
        else:
            raise ValueError("JSON select.mode must be one or all")
    fields = spec.get("fields")
    if fields is None:
        return value
    if not isinstance(fields, list) or any(not isinstance(item, str) for item in fields):
        raise ValueError("JSON fields must be a list of dot paths")
    def project(item: Any) -> dict[str, Any]:
        selected: dict[str, Any] = {}
        for raw_field in fields:
            field = str(_format(raw_field, variables))
            _put(selected, field, _get(item, field))
        return selected
    return [project(item) for item in value] if isinstance(value, list) else project(value)


def _encode_image(path: Path, factor: float) -> str:
    raw = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    if factor < 1:
        try:
            from PIL import Image
            with Image.open(BytesIO(raw)) as image:
                size = (max(1, int(image.width * factor)), max(1, int(image.height * factor)))
                image.thumbnail(size)
                output = BytesIO()
                image.save(output, format="JPEG" if mime == "image/jpeg" else "PNG")
                raw = output.getvalue()
        except ImportError:
            pass
    return f"data:{mime};base64,{b64encode(raw).decode('ascii')}"


def build_prompt(
    *,
    prompts_path: str | Path,
    system_prompt_id: str,
    human_prompt_id: str,
    input_specs: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
) -> PromptPayload:
    """Build provider-neutral multimodal messages from configured inputs."""
    variables = dict(context or {})
    system = _format(load_prompt(prompts_path, system_prompt_id, "system"), variables)
    human = _format(load_prompt(prompts_path, human_prompt_id, "human"), variables)
    blocks: list[str] = []
    image_items: list[dict[str, Any]] = []
    used: list[dict[str, Any]] = []
    images: list[str] = []

    for input_id, raw_spec in input_specs.items():
        if not isinstance(raw_spec, dict):
            raise ValueError(f"Input {input_id!r} must be a mapping")
        if not raw_spec.get("enabled", True):
            continue
        kind = raw_spec.get("kind")
        source_name = raw_spec.get("source", input_id)
        source = variables.get(source_name) if kind == "text" else artifacts.get(source_name)
        required = raw_spec.get("required", False)
        if source is None:
            if required:
                raise ValueError(f"Required input {input_id!r} has no source {source_name!r}")
            continue
        label = str(raw_spec.get("label", input_id)).upper()

        if kind == "json":
            value = json.loads(Path(source).read_text(encoding="utf-8")) if isinstance(source, (str, Path)) else source
            selected = _select_json(value, raw_spec, variables)
            text = json.dumps(selected, ensure_ascii=False, indent=2)
            limit = raw_spec.get("max_chars")
            if limit is not None and len(text) > int(limit):
                text = text[:int(limit)] + "\n... (truncated)"
            blocks.append(f"[{label}]\n{text}")
            used.append({"id": input_id, "kind": kind, "source": str(source_name), "fields": raw_spec.get("fields")})
        elif kind == "text":
            text = str(source).strip()
            limit = raw_spec.get("max_chars")
            if limit is not None and len(text) > int(limit):
                text = text[:int(limit)] + "\n... (truncated)"
            if text:
                blocks.append(f"[{label}]\n{text}")
                used.append({"id": input_id, "kind": kind, "characters": len(text)})
        elif kind == "images":
            root = Path(source) / _format(raw_spec.get("path", ""), variables)
            patterns = raw_spec.get("patterns", ["*.png"])
            found: list[Path] = []
            for pattern in patterns:
                found.extend(root.glob(_format(pattern, variables)))
            unique = sorted({item.resolve() for item in found if item.is_file()}, key=lambda item: item.name.lower())
            limit = int(raw_spec.get("limit", 0))
            selected = unique[:limit] if limit > 0 else unique
            if required and not selected:
                raise ValueError(f"Required image input {input_id!r} matched no files in {root}")
            factor = float(raw_spec.get("downscale_factor", 1.0))
            if not 0 < factor <= 1:
                raise ValueError(f"{input_id}.downscale_factor must be > 0 and <= 1")
            for path in selected:
                image_items.append({"type": "image_url", "image_url": {"url": _encode_image(path, factor)}})
                relative = path.relative_to(Path(source).resolve())
                images.append((Path(str(source_name)) / relative).as_posix())
            if selected:
                blocks.append(f"[{label}]\n" + "\n".join(path.name for path in selected))
                used.append({"id": input_id, "kind": kind, "source": str(source_name),
                             "path": str(raw_spec.get("path", "")), "files": [path.name for path in selected]})
        else:
            raise ValueError(f"Input {input_id!r} has unsupported kind: {kind!r}")

    human_text = human + (("\n\n=== INPUT DATA ===\n\n" + "\n\n".join(blocks)) if blocks else "")
    content: list[dict[str, Any]] = [{"type": "text", "text": human_text}, *image_items]
    return PromptPayload(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
        system_prompt=system,
        human_prompt=human_text,
        inputs=used,
        images=images,
        prompt_hashes={"system": sha256(system.encode()).hexdigest(), "human": sha256(human_text.encode()).hexdigest()},
    )
