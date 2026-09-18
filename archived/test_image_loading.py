#!/usr/bin/env python
"""
Debug: Check which images are actually being loaded
"""

import sys
from pathlib import Path

workspace_root = Path(__file__).parent
sys.path.insert(0, str(workspace_root))

from agent.Assembly_sequence_validation import attach_images_by_keywords


def main():
    """Test image loading with keywords."""
    
    # Test 1: Assembly images
    print("\n=== TEST 1: Assembly Images ===")
    stepparser_assy_dir = workspace_root / "data" / "processed" / "stepparser" / "IPA_Cranfield" / "IPA_Cranfield.STEP"
    keywords = ["isometric"]
    
    print(f"Directory: {stepparser_assy_dir}")
    print(f"Keywords: {keywords}")
    
    images = attach_images_by_keywords(stepparser_assy_dir, keywords)
    print(f"\nLoaded {len(images)} image(s):")
    for img in images:
        print(f"  - {img['filename']} ({len(img['b64'])} chars)")
    
    # Test 2: Step images
    print("\n=== TEST 2: Step Images (Step 1) ===")
    renderings_dir = workspace_root / "data" / "experiments" / "direct_run" / "IPA_Cranfield" / "sequence_renderings"
    keywords = ["isometric", "front", "top", "side"]
    
    print(f"Directory: {renderings_dir}")
    print(f"Keywords: {keywords}")
    
    all_step_images = attach_images_by_keywords(renderings_dir, keywords)
    print(f"\nLoaded {len(all_step_images)} image(s) total")
    
    # Filter to step 1
    step_1_images = [img for img in all_step_images 
                     if "step_01_" in img["filename"] or "step_1_" in img["filename"]]
    print(f"Filtered to STEP 1: {len(step_1_images)} image(s)")
    for img in step_1_images:
        print(f"  - {img['filename']} ({len(img['b64'])} chars)")


if __name__ == "__main__":
    main()
