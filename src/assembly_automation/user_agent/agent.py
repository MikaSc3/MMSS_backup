"""Tool-calling conversational agent for one product workflow session."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping

import yaml

from assembly_automation.workflows.runtime.llms import create_llm

from .artifact_change import ArtifactChangePlanner
from .lc_runtime import AgentRuntimeContext, AllowedToolsMiddleware, ToolEventMiddleware
from .storage import atomic_write_json
from .tools import WorkflowAgentTools


AgentEventCallback = Callable[[dict[str, Any]], None]


TOOL_TRANSITIONS = {
    "inspect_session": "Thank you. Next I’ll inspect the current session state so I can continue from the correct stage.",
    "ingest_documents": "Thank you. Next I’ll review the supporting documents and summarize the relevant context.",
    "analyse_assembly": "Thank you. Next I’ll preprocess the STEP assembly and analyze the complete assembly structure.",
    "analyse_monoparts": "Thank you. Next I’ll analyze the unique parts and build the enriched BOM for your review.",
    "generate_sequence": "Thank you. Next I’ll generate the assembly sequence and then pause for your revision or approval.",
    "revise_sequence": "Understood. Next I’ll revise the assembly sequence using your feedback and present the replacement.",
    "ffa_evaluation": "Thank you. Next I’ll render the approved sequence, analyze the interactions, perform the FfA assessment, and prepare the report.",
    "change_artifact": "Understood. I’ll locate the relevant descriptive fields, apply the correction, and save the validated artifact without rerunning its analysis.",
    "automation_concept_idea_generator": "Understood. Next I'll generate a global automation idea from your direction and the current FfA evidence for your review.",
    "automation_concept_planner": "Thank you. Next I'll plan every assembly step in parallel and consolidate the required equipment.",
    "revise_automation_concept": "Understood. I'll apply that bounded feedback to a new consolidated equipment-list revision.",
    "generate_engineering_powerpoint": "Generating the editable engineering PowerPoint from the latest saved artifacts.",
}

# One concise, application-controlled message per state-changing tool call.
TOOL_TRANSITIONS.update({
    # Session inspection is instantaneous routing, so it stays out of chat.
    "inspect_session": "",
    "ingest_documents": "Reviewing the supporting documents.",
    "analyse_assembly": "Preprocessing the STEP assembly.",
    "analyse_monoparts": "Analyzing the unique parts and building the BOM.",
    "generate_sequence": "Generating the assembly sequence for review.",
    "revise_sequence": "Revising the assembly sequence from your feedback.",
    "ffa_evaluation": "Running interaction analysis, FfA assessment, and report generation.",
    "change_artifact": "Applying the requested artifact correction.",
    "automation_concept_idea_generator": "Generating a global automation idea for review.",
    "automation_concept_planner": "Planning the assembly steps and consolidating equipment requirements.",
    "revise_automation_concept": "Revising the consolidated equipment requirements.",
    "layout_planner": "Planning equipment positions and rendering the schematic layout.",
    "revise_layout": "Applying the layout changes and regenerating the schematic rendering.",
    "cost_planner": "Matching equipment to the shared price catalogue and calculating costs.",
    "generate_engineering_powerpoint": "Generating the engineering PowerPoint.",
})


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item.get("text", "")) if isinstance(item, dict) else str(item)
                         for item in value).strip()
    return str(value or "")


def _transition(tool_calls: list[Mapping[str, Any]]) -> str:
    for call in tool_calls:
        text = TOOL_TRANSITIONS.get(str(call.get("name", "")))
        if text:
            return text
    return ""


class UserFacingAgent:
    """Persisted multi-turn chat whose side effects go through WorkflowAgentTools."""

    def __init__(self, *, toolbox: WorkflowAgentTools, settings: Mapping[str, Any],
                 llm_profiles: Mapping[str, Any], llm: Any = None,
                 event_callback: AgentEventCallback | None = None):
        allowed = {"enabled", "llm", "prompt", "tools", "max_tool_rounds", "artifact_change",
                   "introduction"}
        unknown = set(settings) - allowed
        if unknown:
            raise ValueError(f"Unknown user_agent settings: {sorted(unknown)}")
        if settings.get("enabled", True) is not True:
            raise ValueError("user_agent is disabled")
        self.toolbox = toolbox
        self.toolbox.set_status_callback(self.announce)
        self.settings = dict(settings)
        self.events = event_callback
        self.history_path = toolbox.paths.user_agent_root / "conversation.json"
        self.checkpoint_path = toolbox.paths.user_agent_root / "langgraph_checkpoints.sqlite"
        self._checkpoint_connection: sqlite3.Connection | None = None
        self._checkpointer: Any | None = None
        self._thread_id = f"user_agent:{toolbox.paths.root.name}"
        self.system_prompt = self._load_prompt(str(settings.get("prompt", "system_v1")))
        enabled_tools = list(settings.get("tools") or [])
        if "change_artifact" in enabled_tools:
            artifact_change = settings.get("artifact_change")
            if not isinstance(artifact_change, Mapping):
                raise ValueError("user_agent.artifact_change settings are required when change_artifact is enabled")
            self.toolbox.artifact_change_planner = ArtifactChangePlanner(
                artifact_change, llm_profiles)
        self.tools = toolbox.as_langchain_tools(enabled_tools)
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.internal_tool_map = {tool.name: tool for tool in toolbox.as_langchain_tools([
            "edit_intermediate_artifact", "edit_artifact_fields"])}
        llm_settings = settings.get("llm")
        if isinstance(llm_settings, str):
            profile, overrides = llm_settings, {}
        elif isinstance(llm_settings, Mapping):
            profile = llm_settings.get("profile")
            overrides = {key: value for key, value in llm_settings.items() if key != "profile"}
        else:
            profile, overrides = None, {}
        if not isinstance(profile, str) or not profile:
            raise ValueError("user_agent.llm must name a profile")
        self.chat_model = llm or create_llm(profile, llm_profiles, overrides)
        self.model = self.chat_model.bind_tools(self.tools)
        self._agent_graph: Any | None = None
        self._uses_langchain_agent = self._is_langchain_chat_model(self.chat_model)
        if self._uses_langchain_agent:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_connection = sqlite3.connect(self.checkpoint_path,
                                                           check_same_thread=False)
            from langgraph.checkpoint.sqlite import SqliteSaver
            self._checkpointer = SqliteSaver(self._checkpoint_connection)
            self._checkpointer.setup()
        self.max_tool_rounds = int(settings.get("max_tool_rounds", 8))
        if self.max_tool_rounds < 1:
            raise ValueError("user_agent.max_tool_rounds must be positive")
        if not self.history_path.exists():
            self._write_history([])

    @staticmethod
    def _is_langchain_chat_model(model: Any) -> bool:
        """Keep injected test doubles on the transitional compatibility loop."""
        try:
            from langchain_core.language_models import BaseChatModel
            return isinstance(model, BaseChatModel)
        except ImportError:
            return False

    def _langchain_agent(self) -> Any:
        """Build the compiled outer agent once; middleware supplies per-turn policy."""
        if self._agent_graph is None:
            if self._checkpointer is None:
                raise RuntimeError("LangGraph checkpoint storage is not initialized")
            from langchain.agents import create_agent
            self._agent_graph = create_agent(
                model=self.chat_model,
                tools=self.tools,
                system_prompt=self.system_prompt,
                middleware=[AllowedToolsMiddleware(), ToolEventMiddleware(self._on_lc_tool_event)],
                checkpointer=self._checkpointer,
                name="ffa_navigator",
            )
        return self._agent_graph

    @staticmethod
    def _load_prompt(prompt_id: str) -> str:
        path = Path(__file__).with_name("prompts.yaml")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        prompt = (document.get("system") or {}).get(prompt_id) if isinstance(document, dict) else None
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Unknown user-agent system prompt: {prompt_id}")
        return prompt.strip()

    def _history(self) -> list[dict[str, str]]:
        value = json.loads(self.history_path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError(f"Invalid conversation history: {self.history_path}")
        return value

    def _write_history(self, value: list[dict[str, str]]) -> None:
        atomic_write_json(self.history_path, value)

    def close(self) -> None:
        """Release the per-session checkpoint database when the controller stops."""
        if self._checkpoint_connection is not None:
            self._checkpoint_connection.close()
            self._checkpoint_connection = None

    def _emit(self, event_type: str, **values: Any) -> None:
        if self.events:
            self.events({"type": event_type, **values})

    def announce(self, message: str) -> None:
        """Persist and display a deterministic assistant message before tool use."""
        text = message.strip()
        if not text:
            raise ValueError("announcement cannot be empty")
        history = self._history()
        history.append({"role": "assistant", "content": text})
        self._write_history(history)
        self._emit("assistant_message", content=text, intermediate=False)

    def _on_lc_tool_event(self, phase: str, value: Mapping[str, Any]) -> None:
        """Bridge LangChain middleware events to the existing UI event contract."""
        name = str(value.get("tool", ""))
        if phase == "started":
            transition = _transition([{"name": name}])
            if transition:
                history = self._history()
                history.append({"role": "assistant", "content": transition})
                self._write_history(history)
                self._emit("assistant_message", content=transition, intermediate=True)
            self._emit("tool_started", tool=name, arguments=value.get("arguments") or {})
            return
        self._emit("tool_completed", tool=name, result=value.get("result"))

    def _invoke_langchain(self, text: str, history: list[dict[str, str]]) -> dict[str, Any]:
        """Run one turn through ``create_agent`` with a state-filtered tool set."""
        from langchain_core.messages import AIMessage, HumanMessage

        config = {"configurable": {"thread_id": self._thread_id},
                  "recursion_limit": self.max_tool_rounds * 2 + 4}
        graph = self._langchain_agent()
        checkpoint = graph.get_state(config)
        saved_messages = checkpoint.values.get("messages", []) if checkpoint else []
        if saved_messages:
            messages = [HumanMessage(content=text)]
        else:
            messages = []
            for item in history:
                cls = HumanMessage if item.get("role") == "user" else AIMessage
                messages.append(cls(content=item.get("content", "")))
            messages.append(HumanMessage(content=text))
        enabled = {tool.name for tool in self.tools}
        context = AgentRuntimeContext(
            allowed_tool_names=frozenset(enabled & self.toolbox.allowed_tool_names()),
            user_message=text,
        )
        self._active_user_message = text
        try:
            result = graph.invoke(
                {"messages": messages},
                context=context,
                config=config,
            )
        finally:
            self._active_user_message = None
        result_messages = result.get("messages", []) if isinstance(result, Mapping) else []
        responses = [message for message in result_messages
                     if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None)]
        final_text = _content_text(responses[-1].content).strip() if responses else ""
        if not final_text:
            final_text = "I could not complete this turn. Please try again."
        records = []
        for message in result_messages:
            if getattr(message, "type", "") == "tool":
                records.append({"tool": getattr(message, "name", ""),
                                "result": _content_text(getattr(message, "content", ""))})
        # The LangGraph checkpoint preserves model state, but the Streamlit
        # view deliberately reads this portable conversation artifact. Persist
        # the completed turn as well, otherwise an app rerun loses the answer.
        persisted = self._history()
        persisted.append({"role": "assistant", "content": final_text})
        self._write_history(persisted)
        self._emit("assistant_message", content=final_text, intermediate=False)
        return {"response": final_text, "tool_calls": records,
                "session": self.toolbox.inspect_session()}

    def invoke(self, user_message: str, *, visible_user_message: bool = True,
               allow_tools: bool = True) -> dict[str, Any]:
        """Process one turn; system-driven prompts can remain outside visible history."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        text = user_message.strip()
        if not text:
            raise ValueError("user_message cannot be empty")
        history = self._history()
        history_before_turn = list(history)
        if visible_user_message:
            history.append({"role": "user", "content": text})
            self._write_history(history)
        if allow_tools and self._uses_langchain_agent:
            return self._invoke_langchain(text, history_before_turn)
        messages: list[Any] = [SystemMessage(content=self.system_prompt)]
        for item in history_before_turn:
            cls = HumanMessage if item.get("role") == "user" else AIMessage
            messages.append(cls(content=item.get("content", "")))
        messages.append(HumanMessage(content=text))
        tool_records: list[dict[str, Any]] = []
        final_text = ""
        try:
            for _round in range(self.max_tool_rounds + 1):
                response = (self.model if allow_tools else self.chat_model).invoke(messages)
                messages.append(response)
                spoken = _content_text(response.content)
                if not response.tool_calls:
                    final_text = spoken
                    if spoken:
                        self._emit("assistant_message", content=spoken, intermediate=False)
                    break
                if not allow_tools:
                    raise RuntimeError("The hidden introduction attempted to call a workflow tool")
                if _round >= self.max_tool_rounds:
                    raise RuntimeError("User agent exceeded its configured tool-call rounds")
                transition = _transition(response.tool_calls)
                # Suppress model-generated self-narration on tool-call turns.
                # The application owns the single visible progress message.
                visible = transition
                if visible:
                    history.append({"role": "assistant", "content": visible})
                    self._write_history(history)
                    self._emit("assistant_message", content=visible, intermediate=True)
                for call in response.tool_calls:
                    name, arguments = call.get("name"), call.get("args") or {}
                    tool = self.tool_map.get(name)
                    if tool is None:
                        observation = {"status": "error", "error": f"Unknown tool: {name}"}
                    else:
                        self._emit("tool_started", tool=name, arguments=arguments)
                        try:
                            observation = tool.invoke(arguments)
                        except Exception as exc:
                            observation = {"status": "error",
                                           "error": f"{type(exc).__name__}: {exc}"}
                        self._emit("tool_completed", tool=name, result=observation)
                    tool_records.append({"tool": name, "arguments": arguments,
                                         "result": observation})
                    messages.append(ToolMessage(
                        content=json.dumps(observation, ensure_ascii=False, default=str),
                        tool_call_id=call.get("id", name or "tool"), name=name))
            if not final_text:
                final_text = "I could not complete this turn within the configured tool-call limit."
            history.append({"role": "assistant", "content": final_text})
            self._write_history(history)
            return {"response": final_text, "tool_calls": tool_records,
                    "session": self.toolbox.inspect_session()}
        finally:
            pass

    def execute_tool(self, tool_name: str, arguments: Mapping[str, Any], *,
                     user_message: str, visible_in_chat: bool = True) -> dict[str, Any]:
        """Execute one explicit UI action through the same audited tool boundary."""
        text = user_message.strip()
        if not text:
            raise ValueError("user_message cannot be empty")
        tool = self.tool_map.get(tool_name) or self.internal_tool_map.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool is not enabled for this agent: {tool_name}")
        history = self._history()
        self._emit("tool_started", tool=tool_name, arguments=dict(arguments))
        try:
            result = tool.invoke(dict(arguments))
            self._emit("tool_completed", tool=tool_name, result=result)
            summary = _tool_summary(tool_name, result)
            if visible_in_chat:
                history.extend([{"role": "user", "content": text},
                                {"role": "assistant", "content": summary}])
                self._write_history(history)
                self._emit("assistant_message", content=summary, intermediate=False)
            return {"response": summary,
                    "tool_calls": [{"tool": tool_name, "arguments": dict(arguments),
                                    "result": result}],
                    "session": self.toolbox.inspect_session()}
        except Exception as exc:
            self._emit("tool_completed", tool=tool_name,
                       result={"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            raise


def _tool_summary(tool_name: str, result: Any) -> str:
    status = result.get("status") if isinstance(result, Mapping) else None
    if tool_name in {"edit_intermediate_artifact", "edit_artifact_fields"} and isinstance(result, Mapping):
        return f"Updated {result.get('artifact')} and saved the previous version in history."
    if tool_name == "change_artifact" and isinstance(result, Mapping):
        locations = ", ".join(result.get("changed_locations") or [])
        return (f"Updated {result.get('target')} ({locations}) and saved the previous version "
                "in history. Downstream results were marked stale where required.")
    if tool_name == "revise_sequence" and isinstance(result, Mapping):
        return f"Created sequence revision {result.get('revision_id')}."
    if tool_name == "automation_concept_idea_generator" and isinstance(result, Mapping):
        return f"Created automation idea {result.get('revision_id')} for review."
    if tool_name in {"automation_concept_planner", "revise_automation_concept"} and isinstance(result, Mapping):
        return f"Created detailed step plans and consolidated equipment list {result.get('revision_id')} for review."
    if tool_name == "layout_planner" and isinstance(result, Mapping):
        return f"Created equipment layout {result.get('revision_id')} and its schematic rendering for review."
    if tool_name == "revise_layout" and isinstance(result, Mapping):
        return f"Updated equipment layout {result.get('revision_id')} and regenerated its schematic rendering."
    if tool_name == "cost_planner" and isinstance(result, Mapping):
        return f"Created catalogue-backed cost estimate {result.get('revision_id')} for review."
    return f"{tool_name.replace('_', ' ').title()} completed" + (f" with status {status}." if status else ".")


def generate_introduction(settings: Mapping[str, Any], llm_profiles: Mapping[str, Any],
                          *, llm: Any = None) -> str:
    """Generate the pre-session welcome without constructing workflow tools."""
    from langchain_core.messages import HumanMessage, SystemMessage

    intro = settings.get("introduction") or {}
    if not isinstance(intro, Mapping):
        raise ValueError("user_agent.introduction must be a mapping")
    llm_settings = settings.get("llm")
    if isinstance(llm_settings, str):
        profile, overrides = llm_settings, {}
    elif isinstance(llm_settings, Mapping):
        profile = llm_settings.get("profile")
        overrides = {key: value for key, value in llm_settings.items() if key != "profile"}
    else:
        profile, overrides = None, {}
    if not isinstance(profile, str) or not profile:
        raise ValueError("user_agent.llm must name a profile")
    overrides["max_completion_tokens"] = int(intro.get("max_completion_tokens", 600))
    overrides["timeout"] = float(intro.get("timeout_seconds", 12))
    overrides["max_retries"] = int(intro.get("max_retries", 1))
    model = llm or create_llm(profile, llm_profiles, overrides)
    prompt = UserFacingAgent._load_prompt(str(settings.get("prompt", "system_v1")))
    instruction = str(intro.get("message") or (
        "Introduce yourself to the user. Briefly explain that you will guide STEP preprocessing, "
        "assembly and part review, sequence review, and the final automation assessment. "
        "The user has not uploaded an assembly yet, so invite them to upload a STEP file. "
        "Do not use tools or claim that processing has started."))
    response = model.invoke([SystemMessage(content=prompt), HumanMessage(content=instruction)])
    if getattr(response, "tool_calls", None):
        raise RuntimeError("The pre-session introduction attempted to call a workflow tool")
    content = _content_text(getattr(response, "content", "")).strip()
    if not content:
        raise RuntimeError("The user-facing agent returned an empty introduction")
    return content
