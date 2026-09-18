from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langchain_openai import AzureChatOpenAI
from langchain.agents import create_agent
try:
    from agent.tools import (
        add,
        analyse_assembly_img,
        analyse_monopart_img,
        multiply,
        read_json_file,
        write_json_file,
    )
    from agent.structured_output import (
        TopicInfo,
        Math,
        PictureItem,
        Visible_Parts,
        PictureAnalysis,
    )
    from agent.prompt_store import get_system_prompt, get_user_bootstrap_prompt
except ImportError:  # pragma: no cover
    from tools import (
        add,
        analyse_assembly_img,
        analyse_monopart_img,
        multiply,
        read_json_file,
        write_json_file,
    )
    from structured_output import (
        TopicInfo,
        Math,
        PictureItem,
        Visible_Parts,
        PictureAnalysis,
    )
    from prompt_store import get_system_prompt, get_user_bootstrap_prompt
from dotenv import load_dotenv
import os
from langgraph.checkpoint.memory import InMemorySaver
from pathlib import Path
import uuid

import json

load_dotenv()

if not os.getenv("API_KEY_GPT_4") or not (os.getenv("AZURE_ENDPOINT_4O") or os.getenv("AZURE_ENDPOINT")):
    print("Warnung: Umgebungsvariablen wurden nicht geladen. Überprüfen Sie die .env-Datei.")
else:
    print("Umgebungsvariablen erfolgreich geladen.")
# Example paths
# `searchdir` points to the *assembly rendering folder* (contains assembly images + json).
searchdir = Path(r"C:\Users\KAB-MS\VSCode\apa_from_cad\data\processed\stepparser\IPA_Reducer_Case\IPA_Reducer_Case.STEP")
# `datasource_root` points to the parent that contains the assembly folder + Part_1, Part_2, ...
datasource_root = searchdir.parent

# Example: build initial messages (TEXT ONLY) to keep token usage low.
messages = [HumanMessage(content=get_user_bootstrap_prompt(datasource_root))]


# Initialize LLM
llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_ENDPOINT_4O") or os.getenv("AZURE_ENDPOINT"),
    api_key=os.getenv("API_KEY_GPT_4"),
    api_version="latest",
    deployment_name="gpt-4o",
    max_completion_tokens=5000,
    temperature=0,
)


config = {"configurable": {"thread_id": str(uuid.uuid4())}}
system_prompt = get_system_prompt(datasource_root)


agent = create_agent(
    model=llm,
    tools = [
        add,
        multiply,
        read_json_file,
        write_json_file,
        analyse_assembly_img,
        analyse_monopart_img,
    ],
    system_prompt = system_prompt,
    checkpointer = InMemorySaver()
    )

response = agent.invoke(
    {"messages": messages}, config
)

#response={'messages': [HumanMessage(content=[{'type': 'text', 'text': 'Analysiere jedes Bild separat und gib pro Bild eine Antwort.\n\nImages (in order):\n- Belt Roller Support.STEP-isometric.png\n- Belt Roller Support.STEP-top.png'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,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'}}], additional_kwargs={}, response_metadata={}, id='34482eeb-8622-497f-9135-fbc002ba0663'), AIMessage(content='', additional_kwargs={'refusal': None}, response_metadata={'token_usage': {'completion_tokens': 100, 'prompt_tokens': 1877, 'total_tokens': 1977, 'completion_tokens_details': {'accepted_prediction_tokens': 0, 'audio_tokens': 0, 'reasoning_tokens': 0, 'rejected_prediction_tokens': 0}, 'prompt_tokens_details': {'audio_tokens': 0, 'cached_tokens': 1536}}, 'model_provider': 'openai', 'model_name': 'gpt-4o-2024-11-20', 'system_fingerprint': 'fp_b54fe76834', 'id': 'chatcmpl-Cw1iT27zpbXLVwEDoUsVVSLPo98bZ', 'prompt_filter_results': [{'prompt_index': 1, 'content_filter_result': {'sexual': {'filtered': False, 'severity': 'safe'}, 'violence': {'filtered': False, 'severity': 'safe'}, 'hate': {'filtered': False, 'severity': 'safe'}, 'self_harm': {'filtered': False, 'severity': 'safe'}}}, {'prompt_index': 2, 'content_filter_result': {'sexual': {'filtered': False, 'severity': 'safe'}, 'violence': {'filtered': False, 'severity': 'safe'}, 'hate': {'filtered': False, 'severity': 'safe'}, 'self_harm': {'filtered': False, 'severity': 'safe'}}}, {'prompt_index': 0, 'content_filter_result': {}}], 'finish_reason': 'length', 'logprobs': None, 'content_filter_results': {}}, id='lc_run--284777cb-9fff-43ff-a26c-0649001308fd-0', invalid_tool_calls=[{'type': 'invalid_tool_call', 'id': 'call_kYrvjcQ4QF2rCT15Ph53OQy5', 'name': 'PictureAnalysis', 'args': '{"pictures":[{"pic_name":"Belt Roller Support.STEP-isometric.png","description":"The image shows an isometric view of a belt roller support assembly. The assembly consists of a roller mounted on a base with supporting arms. The roller is cylindrical and appears to be designed for guiding or supporting a belt. The base has four mounting points with bolts for securing the assembly.","important_facts":["Isometric view of the belt roller support.","Includes a', 'error': 'Function PictureAnalysis arguments:\n\n{"pictures":[{"pic_name":"Belt Roller Support.STEP-isometric.png","description":"The image shows an isometric view of a belt roller support assembly. The assembly consists of a roller mounted on a base with supporting arms. The roller is cylindrical and appears to be designed for guiding or supporting a belt. The base has four mounting points with bolts for securing the assembly.","important_facts":["Isometric view of the belt roller support.","Includes a\n\nare not valid JSON. Received JSONDecodeError Unterminated string starting at: line 1 column 449 (char 448)\nFor troubleshooting, visit: https://docs.langchain.com/oss/python/langchain/errors/OUTPUT_PARSING_FAILURE '}], usage_metadata={'input_tokens': 1877, 'output_tokens': 100, 'total_tokens': 1977, 'input_token_details': {'audio': 0, 'cache_read': 1536}, 'output_token_details': {'audio': 0, 'reasoning': 0}})]}

print(response)

