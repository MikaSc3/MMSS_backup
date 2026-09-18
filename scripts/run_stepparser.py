# Simple usage
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from stepparser.processor import StepProcessor
#from .... import LLMEnhancer

processor = StepProcessor(
    input_folder="data/input/STEP",
    output_folder="data/processed/stepparser",
    skip_if_processed=True,
    color_mode="geometry",
    transparency_values=[0.0, 0.3],  # Add more values like [0.0, 0.2, 0.5] for transparent renderings
    headless_mode=True  # Set to True to enable headless rendering with aggressive display cleanup
                        # Use this if section view rendering hangs on complex assemblies
)


# llm_enhancer = LLMEnhancer(
#     input_folder = "data/processed/stepparser",
#     output_folder = "data/processed/llm_enhanced",
#     max_token_usage = 200,
#     Tools = [],
#     allowed_renderings = ["Isometric","Explosion"]
#     Role = ...
#     Prompt_template = ...
#     Example = 
#     #..... add more important parameters that i might want to tweak - 
# )

# Process all STEP files
processor.process_all_step_files()


