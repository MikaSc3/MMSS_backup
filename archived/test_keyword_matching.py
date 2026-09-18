"""
Test keyword matching with YAML-parsed list
"""

from pathlib import Path
import yaml

# Test 1: Direct list
keywords_direct = ["isometric" ,"explosion"]
print(f"Test 1: Direct list")
print(f"  Keywords: {keywords_direct}")
print(f"  After strip: {[kw.strip() for kw in keywords_direct]}")

# Test 2: Load from YAML
yaml_content = """
ASV_finished_assy_keywords: ["isometric" ,"explosion"]
"""

parsed = yaml.safe_load(yaml_content)
keywords_yaml = parsed['ASV_finished_assy_keywords']
print(f"\nTest 2: From YAML")
print(f"  Keywords: {keywords_yaml}")
print(f"  After strip: {[kw.strip() for kw in keywords_yaml]}")

# Test 3: Actual directory matching
stepparser_dir = Path(__file__).parent / "data" / "processed" / "stepparser" / "worm gear demonstrator" / "worm gear demonstrator.STEP"
print(f"\nTest 3: File matching in {stepparser_dir.name}/")

if stepparser_dir.exists():
    all_pngs = list(stepparser_dir.glob("*.png"))
    print(f"  PNG files: {[f.name for f in all_pngs]}")
    
    for keyword_list in [keywords_direct, keywords_yaml]:
        print(f"\n  Testing keywords: {keyword_list}")
        keywords_stripped = [kw.strip() for kw in keyword_list]
        matches = []
        for img_file in all_pngs:
            for kw in keywords_stripped:
                if kw.lower() in img_file.name.lower():
                    matches.append(img_file.name)
                    break
        print(f"    Matched: {matches}")
else:
    print(f"  Directory not found!")
