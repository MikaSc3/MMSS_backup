# Archived Scripts

**Date**: 2026-06-08  
**Total Files**: 33 scripts archived  
**Status**: Non-essential scripts moved for cleanup

---

## 📋 Contents

This folder contains scripts that are no longer part of the active workflow. They are organized by type for reference.

---

## 🧪 Test Scripts (15 files)

Development and component validation tests. These were useful during development but are not required for production workflow.

```
test_assembly_sequence_debug.py
test_asv_validation.py
test_ffa_assessment.py
test_ffa_post_processing.py
test_expand_subassemblies.py
test_image_loading.py
test_keyword_matching.py
test_merge_enriched.py
test_prompt_creation.py
test_section_view_renderer.py
test_structured_outputs.py
test_workflow_compile.py
test_quick_wins.py
test_chamfer_fix.py
test_yaml_parse.py
```

**Why archived**: These are development artifacts for component testing. The actual workflow is validated through `run_evaluation.py` and ground truth comparison.

---

## 🐛 Debug Scripts (7 files)

Troubleshooting and verification utilities for during development. Not needed for normal operation.

```
check_assemblies.py              # Find missing FFA files
debug_checkpoint_structure.py    # Verify checkpoint structure
debug_paths.py                   # Verify directory structure
analyze_section_entropy_diff.py  # Analyze section view entropy
env_test.py                      # Test environment dependencies
occ_test.py                      # 3D visualization test
```

**Why archived**: These are one-time troubleshooting scripts. Use `run_evaluation.py` for systematic validation instead.

---

## ⚙️ Experimental Scripts (4 files)

Non-standard approaches and data manipulation utilities. Superseded by production workflow.

```
clean_automatable_from_jsons.py  # Remove automatable field
Data_manipulation_automate.py    # Set automatable field
EXTRACT STATEMENTS.py             # Extract tagged statements (non-standard)
llm_enrichment.py                # Legacy LLM module (superseded by agent/Workflow_enrich_data.py)
```

**Why archived**: Experimental implementations that are not part of the core workflow.

---

## 🗑️ Redundant/One-Time Scripts (7 files)

### Redundant Evaluation Scripts (3 files)
```
run_ffa_evaluation.py        # Single-dataset FFA eval (redundant with run_evaluation.py)
run_ffa_evaluation_v2.py     # Dual-dataset FFA eval (redundant with run_evaluation.py)
run_ffa_only_seperate_calls.py  # FFA with separate calls (obsolete variant)
```

**Why archived**: Use `run_evaluation.py` instead. It provides comprehensive metrics with proper statistical handling.

---

### One-Time Utilities (2 files)
```
run_file_preparation.py      # Create folder structure (one-time setup)
rename_eval_folders.py       # Rename folders with Color+Fruit (cosmetic, one-time)
```

**Why archived**: One-time setup scripts. Can be reproduced manually if needed.

---

### Data Utilities (2 files)
```
check_ffa_sequence_alignment.py       # Verify FFA ↔ sequence GT alignment
consolidate_ffa_reports_from_experiments.py  # Orchestrate report generation
```

**Why archived**: Not actively used in production workflow.

---

## 📽️ Legacy Workflow (1 file)

```
app_workflow.py              # Legacy interactive workflow (v1)
```

**Why archived**: Superseded by `app_workflow_v2.py` with improved state management and multi-agent orchestration.

---

## ✅ Active Production Scripts (NOT in archived/)

The following scripts remain in root and are essential:

```
# Core Experiment Runners
run_experiments.py                       # Primary orchestrator
run_experiments_sequence_gt.py           # Ground truth sequences
run_ffa_only_experiments.py              # FFA assessment only

# Interactive Workflows
app_workflow_v2.py                       # Interactive multi-agent (v2)

# Helpers
create_checkpoint_from_run.py            # Checkpoint creation
prepare_ground_truth_from_run.py         # GT preparation
run_evaluation.py                        # Evaluation metrics
run_stepparser.py                        # CAD parsing
run_assembly_sequence_generation.py      # Sequence re-generation
run_name_utils.py                        # Run naming utility
batch_render_from_sequences.py           # Batch rendering

# Environment
env_py312occstep2asm.yaml               # Active conda environment
```

---

## 🔄 Recovery

If you need any archived script:
1. Copy the file from `archived/` back to root
2. Run it as normal

Example:
```bash
copy archived\test_workflow_compile.py .
python test_workflow_compile.py
```

---

## 📊 Storage Stats

| Category | Files | Size | Status |
|----------|-------|------|--------|
| Tests | 15 | ~50KB | Development |
| Debug | 7 | ~30KB | Troubleshooting |
| Experimental | 4 | ~20KB | Non-standard |
| Redundant | 3 | ~15KB | Use run_evaluation.py instead |
| One-time | 2 | ~10KB | Manual if needed |
| Data Utils | 2 | ~8KB | Optional |
| Legacy | 1 | ~5KB | Use app_workflow_v2.py instead |
| **TOTAL** | **33** | **~140KB** | **ARCHIVED** |

---

**This cleanup improves project clarity by separating active workflow from development artifacts.**
