"""Central construction of configured chat-model clients."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping


def _secret(profile: Mapping[str, Any], key: str, *, required: bool = True) -> str | None:
    env_name = profile.get(key)
    value = os.getenv(str(env_name)) if env_name else None
    if required and not value:
        raise ValueError(f"Missing environment variable configured by {key}: {env_name}")
    return value


def create_llm(profile_name: str, profiles: Mapping[str, Any], overrides: Mapping[str, Any] | None = None):
    """Create one LangChain chat model from a named, provider-neutral profile."""
    configured = profiles.get(profile_name)
    if not isinstance(configured, dict):
        raise ValueError(f"Unknown LLM profile: {profile_name}")
    overrides = dict(overrides or {})
    allowed_overrides = {"max_completion_tokens", "temperature", "seed"}
    unknown_overrides = set(overrides) - allowed_overrides
    if unknown_overrides:
        raise ValueError(f"Unsupported LLM overrides: {sorted(unknown_overrides)}")
    profile = {**configured, **overrides}
    allowed = {"provider", "model", "deployment", "deployment_env", "endpoint_env",
               "base_url", "base_url_env", "api_key_env", "api_version",
               "api_version_env", "max_completion_tokens", "temperature", "seed"}
    unknown = set(profile) - allowed
    if unknown:
        raise ValueError(f"Unknown settings for LLM profile {profile_name}: {sorted(unknown)}")
    provider = profile.get("provider")
    model = profile.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError(f"LLM profile {profile_name} requires model")
    common = {key: profile[key] for key in ("temperature", "seed", "max_completion_tokens") if key in profile}

    from langchain_openai import AzureChatOpenAI, ChatOpenAI

    if provider == "azure_openai":
        deployment = (os.getenv(str(profile.get("deployment_env"))) if profile.get("deployment_env") else None) or profile.get("deployment") or model
        api_version = (os.getenv(str(profile.get("api_version_env"))) if profile.get("api_version_env") else None) or profile.get("api_version")
        return AzureChatOpenAI(azure_endpoint=_secret(profile, "endpoint_env"),
                               api_key=_secret(profile, "api_key_env"),
                               api_version=api_version, azure_deployment=deployment, **common)
    if provider == "azure_openai_v1":
        endpoint = _secret(profile, "endpoint_env") or ""
        host = re.match(r"https?://[^/]+", endpoint)
        if not host:
            raise ValueError(f"Invalid Azure endpoint for profile {profile_name}")
        deployment = (os.getenv(str(profile.get("deployment_env"))) if profile.get("deployment_env") else None) or profile.get("deployment") or model
        return ChatOpenAI(base_url=host.group(0) + "/openai/v1/", api_key=_secret(profile, "api_key_env"),
                          model=deployment, **common)
    if provider in ("openai", "openai_compatible"):
        base_url = (os.getenv(str(profile.get("base_url_env"))) if profile.get("base_url_env") else None) or profile.get("base_url")
        api_key = _secret(profile, "api_key_env", required=provider == "openai") or "local"
        kwargs = {"model": model, "api_key": api_key, **common}
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)
    raise ValueError(f"Unsupported LLM provider: {provider!r}")
