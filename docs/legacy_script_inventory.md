# Important Scripts - APA from CAD

**Date**: 2026-06-08  
**Status**: Active Project  
**Purpose**: Reference guide for core scripts and their dependencies

---

## 🎯 Core Workflow Scripts (PRIMARY)

### 1. **run_experiments_sequence_gt.py** ⭐ CRITICAL
- **Role**: Experiment runner using **ground truth assembly sequences**
- **Use Case**: Running experiments where the assembly sequence is provided from ground truth (not LLM-generated)
- **Key Feature**: Replaces `generate_assembly_sequence` node with `generate_assembly_sequence_from_gt`
- **Imports from**: `agent.workflow`, `agent.config`, `agent.checkpoint_utils`
- **Output Structure**: `data/experiments/run_{TIMESTAMP}_seq_gt/`
- **Dependencies**:
  - Ground truth sequences in `data/ground_truth/assembly_sequence_ground_truth/`
  - Experiment configs in `configs/final_ffa_for_eval_noshit/`
- **Status**: ✅ Active - Used for ground truth validation

---

### 2. **run_ffa_only_experiments.py** ⭐ CRITICAL
- **Role**: Runs **FFA assessment only** on existing checkpoints
- **Use Case**: Re-running FFA assessment without re-processing entire workflow
- **Key Feature**: Loads data from checkpoints and only executes FFA evaluation node
- **Imports from**: `agent.workflow`, `agent.config_utils`
- **Configuration**:
  - `CHECKPOINT_PATH`: Source checkpoint directory
  - `EXPERIMENTS_TO_RUN`: List of experiments to process
  - `RUN_ROOT_DIR`: Output directory for FFA results
  - `FFA_CONFIG_SOURCE`: Config folder ("sequence_gt" or "ffa_only")
- **Output Structure**: `data/experiments/FFA_only_final_4ocp/run_{TIMESTAMP}_FFA_only/`
- **Status**: ✅ Active - Used for rapid FFA experimentation

---

### 3. **scripts/app_workflow_v2.py** ⭐ CRITICAL
- **Role**: **Interactive assembly analysis workflow** with multi-agent orchestration
- **Use Case**: Interactive UI-based analysis with user feedback loops
- **Architecture**:
  - Phase 1: Preprocessing (Stepparser)
  - Phase 2: Enrichment + sequence generation
  - Agent 2: Interactive sequence validation (user feedback loop)
  - Phase 4: Rendering + FFA assessment
  - Agent 3: FFA explanation + optional revision
- **Imports from**: `agent.workflow` nodes, session management
- **Output Structure**: `data/sessions/{timestamp}_{assembly_name}/`
- **Key Features**:
  - Multi-agent interaction (Agents 1, 2, 3)
  - Session-based state management
  - User feedback loops for sequence refinement
- **Status**: ✅ Active - Primary UI entry point

---

### 4. **scripts/run_experiments.py** ⭐ CRITICAL (PRIMARY)
- **Role**: **Primary experiment runner** orchestrating all workflow phases
- **Use Case**: Batch processing of assemblies with configurable experiment parameters
- **Key Features**:
  - Discovers experiments from `configs/experiments/`
  - Supports optional assembly override via `STEP_FILES_OVERRIDE`
  - Checkpoint support for resumable runs
  - Generates timestamped output folders
- **Imports from**: `agent.config`, `agent.workflow`, `agent.checkpoint_utils`
- **Output Structure**: `data/experiments/run_{TIMESTAMP}/`
- **Dependencies**:
  - Experiment configs: `configs/experiments/*.yaml`
  - STEP files: `data/processed/stepparser/`
- **Status**: ✅ Active - Foundation for all experiments

---

### 5. **app_workflow.py** (Legacy)
- **Role**: Legacy interactive annotation workflow
- **Status**: ⚠️ Deprecated - Use `scripts/app_workflow_v2.py` instead
- **Reason**: Replaced by v2 architecture with better state management

---

## 🔧 Helper Scripts (SUPPORTING)

### 1. **scripts/create_checkpoint_from_run.py** 📦
- **Role**: Retroactively creates checkpoints from completed runs
- **Use Case**: Snapshot completed workflow results for resumable processing
- **Imports from**: `agent.checkpoint_utils`
- **Output**: `data/checkpoints/{timestamp}/{exp_name}/` when this manual helper is explicitly run
- **Linked to**: `scripts/run_experiments.py`, `run_ffa_only_experiments.py`
- **Status**: ✅ Active - Essential for checkpoint system

---

### 2. **prepare_ground_truth_from_run.py** 📋
- **Role**: Creates timestamped ground truth folders from completed runs
- **Use Case**: Preparation of training/validation data sets
- **Imports from**: `evaluation.ffa_str_to_enum`
- **Output**: 
  - `data/ground_truth/{timestamp}_PRE_assembly_sequence_ground_truth/`
  - `data/ground_truth/{timestamp}_PRE_ffa_ground_truth/`
- **Configuration**: `RUN_EXP_PATH` and `GROUND_TRUTH_BASE`
- **Linked to**: `run_evaluation.py`
- **Status**: ✅ Active - Essential for GT preparation

---

### 3. **run_evaluation.py** 📊
- **Role**: Post-run evaluation implementing comprehensive metrics
- **Use Case**: Evaluation of experiment results against ground truth
- **Metrics Implemented** (§1-§13):
  - Classification: Macro F1, Weighted F1, Balanced Accuracy, Confusion Matrix
  - Regression: MAE, RMSE, R², Spearman, Pearson
  - Soft Score
  - Cross-experiment comparison (generalization gap)
  - Statistical testing (Mann-Whitney-U, Welch's t-test, Cohen's d)
- **Ground Truth Datasets**:
  - Eval set: `data/ground_truth/ffa_ground_truth_evaluierungsdaten rev2/`
  - Test set: `data/ground_truth/ffa_ground_truth_testdatenMASTER/`
- **Configuration**: `RUN_DIR_TO_EVALUATE`
- **Output**: Metrics, plots, CSV files
- **Linked to**: `prepare_ground_truth_from_run.py`, evaluation results
- **Status**: ✅ Active - Critical for metrics validation

---

### 4. **scripts/run_stepparser.py** 🔄
- **Role**: Simple entry point for STEP file processing
- **Use Case**: Standalone CAD geometry analysis and rendering
- **Configuration**: Transparency, downscaling, color mode
- **Imports from**: `stepparser.processor.StepProcessor`
- **Output**: Renderings + metadata in `data/processed/stepparser/`
- **Status**: ✅ Active - Preprocessing stage

---

### 5. **scripts/run_assembly_sequence_generation.py** 🔄
- **Role**: Re-generates assembly sequences and renderings from existing data
- **Use Case**: Refining sequences without full workflow re-run
- **Linked to**: `scripts/run_experiments.py`
- **Status**: ⚠️ Utility - May be useful for re-generation

---

### 6-7. **run_ffa_evaluation.py** & **run_ffa_evaluation_v2.py** 📊
- **Role**: Specialized FFA evaluation (single vs. dual dataset)
- **Status**: ⚠️ Potentially redundant with `run_evaluation.py`

---

## 📚 Test Scripts (15 total)

| Script | Purpose | Status |
|--------|---------|--------|
| `test_*.py` | Component validation (workflow, prompts, images, etc.) | ⚠️ Development |

**Generally SAFE to archive** after component stability confirmed.

---

## 🐛 Debug Scripts (6 total)

| Script | Purpose | Status |
|--------|---------|--------|
| `check_*.py`, `debug_*.py`, `analyze_*.py` | Troubleshooting & verification | ⚠️ Development |
| `env_test.py`, `occ_test.py` | Environment validation | ⚠️ Development |

**Generally SAFE to archive** after system stability confirmed.

---

## ⚙️ Utility Scripts (5 total)

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/batch_render_from_sequences.py` | Batch rendering | ✅ May be useful |
| `consolidate_ffa_reports_from_experiments.py` | Report generation | ✅ May be useful |
| `run_file_preparation.py` | Folder structure setup | ⚠️ One-time use |
| `run_name_utils.py` | Color+Fruit naming | ⚠️ Optional |
| `rename_eval_folders.py` | Folder renaming | ⚠️ One-time use |

---

## 🧪 Experimental Scripts (4 total)

| Script | Purpose | Status |
|--------|---------|--------|
| `clean_automatable_from_jsons.py` | Data manipulation | ❌ Experimental |
| `Data_manipulation_automate.py` | Data manipulation | ❌ Experimental |
| `EXTRACT STATEMENTS.py` | Report analysis | ❌ Experimental |
| `llm_enrichment.py` | LLM module | ❌ Archived approach |

**SAFE to delete** - experimental/superseded implementations.

---

## 🔗 Dependency Graph

```
┌─────────────────────────────────────────────────────┐
│ scripts/run_experiments.py (PRIMARY ORCHESTRATOR)   │
├─────────────────────────────────────────────────────┤
│ ├─ agent/workflow.py (all workflow nodes)           │
│ ├─ agent/config.py (experiment config)              │
│ ├─ agent/checkpoint_utils.py (checkpointing)        │
│ └─ agent/config_utils.py (YAML discovery)           │
│                                                      │
│ ↓ Output: data/experiments/run_{TIMESTAMP}/         │
│                                                      │
│ ├─ scripts/create_checkpoint_from_run.py (snapshot) │
│ ├─ prepare_ground_truth_from_run.py (GT prep)       │
│ └─ run_evaluation.py (metrics)                      │
│                                                      │
│ Parallel: run_experiments_sequence_gt.py            │
│ Parallel: run_ffa_only_experiments.py               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ scripts/app_workflow_v2.py (INTERACTIVE WORKFLOW)   │
├─────────────────────────────────────────────────────┤
│ ├─ agent/workflow.py (phase orchestration)          │
│ ├─ Session management (data/sessions/)              │
│ ├─ Multi-agent interaction (Agent 1, 2, 3)         │
│ └─ User feedback loops                              │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ scripts/run_stepparser.py (PREPROCESSING)           │
├─────────────────────────────────────────────────────┤
│ └─ stepparser.processor (CAD parsing)               │
│    Output: data/processed/stepparser/               │
└─────────────────────────────────────────────────────┘
```

---

## 📋 Summary Table

| Script | Category | Status | Dependency | Keep? |
|--------|----------|--------|-----------|-------|
| scripts/run_experiments.py | main | ✅ Active | Core | **YES** |
| run_experiments_sequence_gt.py | main | ✅ Active | Core | **YES** |
| run_ffa_only_experiments.py | main | ✅ Active | Core | **YES** |
| scripts/app_workflow_v2.py | main | ✅ Active | Core | **YES** |
| app_workflow.py | main | ⚠️ Legacy | None | **NO** |
| scripts/run_stepparser.py | helper | ✅ Active | Prep | **YES** |
| scripts/create_checkpoint_from_run.py | helper | ✅ Active | Core | **YES** |
| prepare_ground_truth_from_run.py | helper | ✅ Active | Core | **YES** |
| run_evaluation.py | helper | ✅ Active | Core | **YES** |
| scripts/run_assembly_sequence_generation.py | helper | ⚠️ Utility | Optional | **MAYBE** |
| run_ffa_evaluation.py | helper | ⚠️ Redundant | Optional | **MAYBE** |
| run_ffa_evaluation_v2.py | helper | ⚠️ Redundant | Optional | **MAYBE** |
| run_ffa_only_seperate_calls.py | helper | ⚠️ Experimental | Optional | **MAYBE** |

---

**Next Step**: Review `cleanup.md` for full inventory and decide on deletions.
