"""
Environment smoke test for LangChain/OpenAI, pythonOCC, MarkItDown, and Streamlit.

Run:
    python 0_env_test.py
"""

from __future__ import annotations

import os
import re
from importlib.metadata import PackageNotFoundError, version

import langchain
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from check_document_ui_env import main as check_document_ui_env

try:
    import OCC
    from OCC.Core.AIS import AIS_Shape
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCC.Core.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NOM_PLASTIC
    from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCC.Display.SimpleGui import init_display

    OCC_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    OCC = None
    AIS_Shape = None
    BRepPrimAPI_MakeBox = None
    Graphic3d_MaterialAspect = None
    Graphic3d_NOM_PLASTIC = None
    Quantity_Color = None
    Quantity_TOC_RGB = None
    init_display = None
    OCC_IMPORT_ERROR = exc


MODEL_REGISTRY = {
    "4o": {
        "env_key": "AZURE_ENDPOINT_4O",
        "deployment": "gpt-4o",
        "api_key_env": "API_KEY_GPT_4",
        "api_version": "2024-12-01-preview",
        "use_v1_api": False,
    },
    "4.1": {
        "env_key": "AZURE_ENDPOINT_41",
        "deployment": "gpt-4.1",
        "api_key_env": "API_KEY_GPT_4",
        "api_version": "2024-12-01-preview",
        "use_v1_api": False,
    },
    "5.4": {
        "env_key": "AZURE_ENDPOINT_54",
        "deployment": "gpt-5.4",
        "api_key_env": "API_KEY_GPT_5",
        "api_version": "2025-04-01-preview",
        "use_v1_api": True,
        "deployment_env": "AZURE_DEPLOYMENT_54",
    },
}


def load_env_files() -> None:
    """Load the repo env files used by quick tests and workflow modules."""
    load_dotenv()
    load_dotenv("agent/.env")


def print_import_status() -> None:
    """Print versions and prove workflow-style imports are available."""
    load_env_files()

    print("LangChain Version:\t", langchain.__version__)
    if OCC_IMPORT_ERROR is None:
        print("OCC Version:\t\t", OCC.VERSION)
    else:
        print("OCC Version:\t\t", f"MISSING/ERROR ({OCC_IMPORT_ERROR})")
    print("LangChain/OpenAI:\t", ChatOpenAI.__name__, AzureChatOpenAI.__name__)
    print("Messages:\t\t", SystemMessage.__name__, HumanMessage.__name__)
    print_markitdown_status()


def print_markitdown_status() -> None:
    """Check whether MarkItDown is installed for document ingestion."""
    try:
        from markitdown import MarkItDown

        try:
            markitdown_version = version("markitdown")
        except PackageNotFoundError:
            markitdown_version = "installed, version unknown"

        print("MarkItDown:\t\t", f"OK ({markitdown_version}) - {MarkItDown.__name__}")
    except Exception as exc:
        print("MarkItDown:\t\t", f"MISSING/ERROR ({exc}) try python -m pip install \"markitdown[all]\"")


def create_llm(model_alias: str | None = None) -> ChatOpenAI | AzureChatOpenAI:
    """Create a small LangChain LLM client using the workflow env-var pattern."""
    model_alias = model_alias or os.getenv("APA_ENV_TEST_MODEL", "5.4")
    cfg = MODEL_REGISTRY.get(model_alias, MODEL_REGISTRY["5.4"])

    raw_endpoint = (
        os.getenv(cfg["env_key"])
        or os.getenv("AZURE_ENDPOINT_54")
        or os.getenv("AZURE_ENDPOINT")
        or ""
    )
    api_key = (
        os.getenv(cfg.get("api_key_env", "API_KEY_GPT_4"))
        or os.getenv("API_KEY_GPT_4")
    )
    api_version = os.getenv("AZURE_API_VERSION") or cfg["api_version"]
    deployment_env_key = cfg.get("deployment_env")
    deployment = (
        (os.getenv(deployment_env_key) if deployment_env_key else None)
        or cfg["deployment"]
    )

    if not api_key:
        raise RuntimeError(
            f"No API key found. Checked {cfg.get('api_key_env')} and API_KEY_GPT_4."
        )
    if not raw_endpoint:
        raise RuntimeError(
            f"No endpoint found. Checked {cfg['env_key']}, AZURE_ENDPOINT_4O, and AZURE_ENDPOINT."
        )

    if cfg["use_v1_api"]:
        base = re.match(r"(https?://[^/]+)", raw_endpoint)
        base_url = (base.group(1) if base else raw_endpoint.rstrip("/")) + "/openai/v1/"
        print(f"Creating ChatOpenAI: model={model_alias}, deployment={deployment}")
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=deployment,
            temperature=0,
            max_tokens=512,
        )

    print(f"Creating AzureChatOpenAI: model={model_alias}, deployment={deployment}")
    return AzureChatOpenAI(
        azure_endpoint=raw_endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=deployment,
        temperature=0,
        max_tokens=512,
    )


def ask_llm_once() -> None:
    """Ask the user for a terminal prompt and send it to the configured LLM."""
    print("\nLLM smoke test")
    user_prompt = input("What do you want to ask the LLM? ").strip()
    if not user_prompt:
        print("No prompt entered; skipping LLM call.")
        return

    llm = create_llm()
    messages = [
        SystemMessage(content="You are a concise assistant for a local environment test."),
        HumanMessage(content=user_prompt),
    ]
    response = llm.invoke(messages)
    print("\nLLM response:")
    print(response.content)


def open_box_with_occ_renderer() -> None:
    """Open a simple box in the pythonOCC viewer."""
    if OCC_IMPORT_ERROR is not None:
        raise RuntimeError(f"pythonOCC is not available: {OCC_IMPORT_ERROR}")

    display, start_display, _add_menu, _add_function_to_menu = init_display()

    box_shape = BRepPrimAPI_MakeBox(100.0, 80.0, 60.0).Shape()
    ais_box = AIS_Shape(box_shape)
    ais_box.SetColor(Quantity_Color(0.18, 0.44, 0.78, Quantity_TOC_RGB))

    material = Graphic3d_MaterialAspect(Graphic3d_NOM_PLASTIC)
    material.SetShininess(0.15)
    ais_box.SetMaterial(material)

    display.Context.Display(ais_box, True)
    display.FitAll()

    print("Opening OCC viewer with test box. Close the viewer window to exit.")
    start_display()


if __name__ == "__main__":
    print_import_status()
    print("\nMarkItDown and Streamlit smoke tests")
    if check_document_ui_env() != 0:
        raise SystemExit(1)
    ask_llm_once()
    open_box_with_occ_renderer()
