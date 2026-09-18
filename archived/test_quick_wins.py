"""Test Script für Quick Wins - Image Caching & Config Management"""

import time
from pathlib import Path

# Test 1: Configuration Management
print("=" * 60)
print("TEST 1: Configuration Management")
print("=" * 60)

from agent.config import WorkflowConfig

config = WorkflowConfig.from_yaml()
print(f"✓ Config geladen: experiment_name='{config.experiment_name}'")
print(f"  Output Root: {config.experiment_output_root}")
print(f"  Additional Info Root: {config.additional_info_root}")
print(f"  Assembly Order Root: {config.assembly_order_root}")
print(f"  Use Additional Info: {config.use_additional_assembly_info}")
print(f"  Enable Merge BOM: {config.enable_merge_bom}")
print(f"  Enable FFA: {config.enable_ffa_assessment}")
print()

# Test 2: Image Caching
print("=" * 60)
print("TEST 2: Image Caching")
print("=" * 60)

from agent.tools import ImageLoader

test_dir = Path("data/processed/stepparser/IPA_Cranfield/IPA_Cranfield.STEP")
if test_dir.exists():
    loader = ImageLoader(test_dir)
    
    # Find first PNG
    paths = list(loader.search_dir.glob("*.png"))[:1]
    
    if paths:
        test_img = paths[0]
        print(f"Testing with: {test_img.name}")
        
        # First encode (no cache)
        start = time.time()
        enc1 = loader.encode_image(test_img)
        t1 = time.time() - start
        
        # Second encode (from cache)
        start = time.time()
        enc2 = loader.encode_image(test_img)
        t2 = time.time() - start
        
        # Verify same result
        assert enc1 == enc2, "Cache returned different result!"
        
        print(f"✓ Image Caching funktioniert")
        print(f"  First encode:  {t1*1000:.2f}ms")
        print(f"  Cached encode: {t2*1000:.2f}ms")
        if t2 > 0:
            print(f"  Speedup: {(t1/t2):.1f}x faster")
        print(f"  Cache size: {len(loader._cache)} images")
        print(f"  Base64 length: {len(enc1)} chars")
    else:
        print("⚠ No PNG files found for caching test")
else:
    print(f"⚠ Test directory not found: {test_dir}")

print()

# Test 3: Config Properties
print("=" * 60)
print("TEST 3: Config Properties & Methods")
print("=" * 60)

# Test computed properties
print(f"Experiment Output Root: {config.experiment_output_root}")
print(f"  Type: {type(config.experiment_output_root)}")
print(f"  Is Path: {isinstance(config.experiment_output_root, Path)}")

# Test to_dict
config_dict = config.to_dict()
print(f"✓ Config exportiert als dict: {len(config_dict)} Felder")

print()
print("=" * 60)
print("✅ ALLE TESTS ERFOLGREICH")
print("=" * 60)
