import os
import json
import base64
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from io import BytesIO
from PIL import Image
import yaml
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from prompts import PROMPT_CATALOG


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class LLMConfig:
    """Azure OpenAI Configuration"""
    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "latest"


@dataclass
class EnrichmentTask:
    """Single enrichment task configuration"""
    name: str
    prompt_template: str
    target_fields: List[str]
    image_keywords: List[str]


@dataclass
class PromptTemplate:
    """Prompt template structure"""
    role: str
    task: str
    context_fields: List[str]
    output_format: Dict
    
    def render(self, context: Dict) -> str:
        """Build prompt from context data"""
        context_lines = [
            f"- {field}: {self._get_value(context, field)}"
            for field in self.context_fields
            if self._get_value(context, field) is not None
        ]
        
        return f"""{self.role}

TASK:
{self.task}

CONTEXT:
{chr(10).join(context_lines)}

OUTPUT FORMAT (JSON):
{json.dumps(self.output_format, indent=2)}

Respond ONLY with valid JSON matching the output format."""
    
    def _get_value(self, data: Dict, path: str):
        """Get nested value using dot notation"""
        for key in path.split('.'):
            data = data.get(key) if isinstance(data, dict) else None
            if data is None:
                return None
        return data


# ============================================================================
# CORE SERVICES
# ============================================================================

class VisionLLM:
    """Simplified Azure OpenAI Vision API wrapper"""
    
    def __init__(self, config: LLMConfig):
        self.llm = AzureChatOpenAI(
            azure_endpoint=config.endpoint,
            api_key=config.api_key,
            deployment_name=config.deployment,
            api_version=config.api_version
        )
    
    def enrich(self, prompt: str, image_paths: List[str], system_msg: str) -> Optional[Dict]:
        """Call LLM with images and parse JSON response"""
        try:
            # Encode images
            image_contents = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{self._encode_image(p)}"}
                }
                for p in image_paths
            ]
            
            # Build message
            messages = [
                SystemMessage(content=system_msg),
                HumanMessage(content=[{"type": "text", "text": prompt}] + image_contents)
            ]
            
            # Call LLM
            response = self.llm.invoke(messages)
            
            # Parse JSON response
            return json.loads(response.content)
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON response: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] LLM call failed: {e}")
            return None
    
    def _encode_image(self, path: str) -> str:
        """Encode image to base64"""
        img = Image.open(path)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()


class PromptLibrary:
    """Manages prompt templates"""
    
    def __init__(self, library_path: Path):
        self.path = Path(library_path)
        self.path.mkdir(exist_ok=True)
        self._cache = {}
    
    # In PromptLibrary.load():
    def load(self, name: str) -> PromptTemplate:
        """Load template from catalog or file"""
        if name in PROMPT_CATALOG:
            prompt_def = PROMPT_CATALOG[name]
            return PromptTemplate(**prompt_def.to_dict())
        if name not in self._cache:
            file_path = self.path / f"{name}.yaml"
            with open(file_path) as f:
                data = yaml.safe_load(f)
            self._cache[name] = PromptTemplate(**data)
        return self._cache[name]
    
    def save(self, name: str, template: PromptTemplate):
        """Save template to library"""
        file_path = self.path / f"{name}.yaml"
        with open(file_path, 'w') as f:
            yaml.dump(template.__dict__, f)
        self._cache[name] = template


# ============================================================================
# ENRICHMENT ENGINE
# ============================================================================

class EnrichmentEngine:
    """Orchestrates LLM enrichment workflow"""
    
    def __init__(self, llm: VisionLLM, prompts: PromptLibrary):
        self.llm = llm
        self.prompts = prompts
    
    def enrich_assembly(self, assembly_path: Path, tasks: List[EnrichmentTask]) -> int:
        """
        Enrich all parts in an assembly
        Returns: number of parts enriched
        """
        enriched_count = 0
        
        # Find all part directories
        part_dirs = [d for d in assembly_path.iterdir() 
                    if d.is_dir() and not d.name.endswith('_assembly')]
        
        for part_dir in part_dirs:
            if self._enrich_part(part_dir, tasks):
                enriched_count += 1
        
        return enriched_count
    
    def _enrich_part(self, part_dir: Path, tasks: List[EnrichmentTask]) -> bool:
        """Enrich single part with multiple tasks"""
        
        # Load properties
        props_file = part_dir / "properties.json"
        if not props_file.exists():
            print(f"[SKIP] No properties.json in {part_dir.name}")
            return False
        
        with open(props_file) as f:
            properties = json.load(f)
        
        # Execute each enrichment task
        enriched = False
        for task in tasks:
            if self._execute_task(part_dir, properties, task):
                enriched = True
        
        if enriched:
            # Save enriched properties
            output_file = part_dir / "properties_enriched.json"
            with open(output_file, 'w') as f:
                json.dump(properties, f, indent=2)
            print(f"[✓] {part_dir.name}")
            return True
        
        return False
    
    def _execute_task(self, part_dir: Path, properties: Dict, task: EnrichmentTask) -> bool:
        """Execute single enrichment task"""
        
        # Find images
        images = self._find_images(part_dir, task.image_keywords)
        if not images:
            print(f"[SKIP] No images for {task.name} in {part_dir.name}")
            return False
        
        # Load and render prompt
        template = self.prompts.load(task.prompt_template)
        prompt = template.render(properties)
        
        # Call LLM
        result = self.llm.enrich(prompt, images, template.role)
        if not result:
            return False
        
        # Update properties with results
        for field in task.target_fields:
            if field in result:
                self._set_field(properties, field, result[field])
        
        return True
    
    def _find_images(self, part_dir: Path, keywords: List[str]) -> List[str]:
        """Find images matching any keyword"""
        return [
            str(img) for img in part_dir.glob("*.png")
            if any(kw in img.name for kw in keywords)
        ]
    
    def _set_field(self, data: Dict, path: str, value):
        """Set nested field using dot notation"""
        keys = path.split('.')
        for key in keys[:-1]:
            data = data.setdefault(key, {})
        data[keys[-1]] = value


# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def run_enrichment(
    processed_dir: str,
    config: LLMConfig,
    tasks: List[EnrichmentTask],
    prompt_library_path: str
):
    """
    Main enrichment workflow
    
    Args:
        processed_dir: Directory containing assembly folders
        config: Azure OpenAI configuration
        tasks: List of enrichment tasks to execute
        prompt_library_path: Path to prompt templates
    """
    print("="*80)
    print("LLM DATA ENRICHMENT")
    print("="*80)
    
    # Initialize services
    llm = VisionLLM(config)
    prompts = PromptLibrary(Path(prompt_library_path))
    engine = EnrichmentEngine(llm, prompts)
    
    # Process all assemblies
    processed_path = Path(processed_dir)
    total_enriched = 0
    
    for assembly_dir in processed_path.iterdir():
        if not assembly_dir.is_dir():
            continue
        
        print(f"\n[Assembly: {assembly_dir.name}]")
        count = engine.enrich_assembly(assembly_dir, tasks)
        total_enriched += count
    
    print(f"\n[SUCCESS] Enriched {total_enriched} parts")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Configuration
    config = LLMConfig(
        endpoint="https://master-thesis-mika.cognitiveservices.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview",
        api_key="",
        deployment="gpt-4o",
        max_tokens= 200,
        temperature=0.0
    )
    
    # Define enrichment tasks
    tasks = [
        EnrichmentTask(
            name="part_description",
            prompt_template="part_description_v1",
            target_fields=["description_llm", "name_llm", "functional_role"],
            image_keywords=["iso"]
        ),
    ]
    
    # Run enrichment
    run_enrichment(
        processed_dir="./data/processed",
        config=config,
        tasks=tasks,
        prompt_library_path="./prompts"
    )
