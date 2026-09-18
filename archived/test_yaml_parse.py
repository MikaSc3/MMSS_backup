import yaml
from pathlib import Path

yaml_path = Path("configs/prompts.yaml")
data = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))

print("YAML parsing successful")
print("Top-level keys:", list(data.keys()))

prompts = data.get('prompts', {})
print(f"\nTotal prompts: {len(prompts)}")
print("Prompt IDs:", list(prompts.keys()))

if 'ffa_assessment_full_v1' in prompts:
    print("\n✓ ffa_assessment_full_v1 FOUND")
    prompt_entry = prompts['ffa_assessment_full_v1']
    print(f"  Type: {type(prompt_entry)}")
    if isinstance(prompt_entry, dict):
        print(f"  Keys: {list(prompt_entry.keys())}")
        if 'text' in prompt_entry:
            print(f"  Text length: {len(prompt_entry['text'])}")
            print(f"  First 100 chars: {prompt_entry['text'][:100]}")
else:
    print("\n✗ ffa_assessment_full_v1 NOT FOUND")
