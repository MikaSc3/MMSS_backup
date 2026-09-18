# Archived Markdown Files Index

**Date**: 2026-06-08  
**Total Files**: 28 markdown files  
**Status**: Organized archive for reference

---

## 📋 Contents

These markdown files document completed work, historical decisions, technical specifications, and outdated information. They are preserved for reference and audit trail purposes.

---

## 🎯 Organization Strategy

Root directory now contains **only 5 essential files**:
- README.md (project overview)
- GETTING_STARTED.md (quick start)
- IMPORTANT_SCRIPTS.md (scripts reference)
- cleanup.md (cleanup audit)
- CLEANUP_COMPLETE.md (cleanup summary)

All other documentation is organized here for easy reference without cluttering the root.

---

## 📚 Technical Documentation (12 files)

Comprehensive guides for the app_workflow_v2 and experimental infrastructure:

### App Workflow v2 Documentation (4 files)
```
APP_WORKFLOW_V2_README.md
  └─ Interactive workflow (v2) user guide

APP_WORKFLOW_V2_INDEX.md
  └─ Complete v2 workflow index & structure

app_workflow_v2.md
  └─ v2 workflow technical documentation

NODE_IO_MAPPING_APP_WORKFLOW_V2.md
  └─ Node input/output mapping for v2
```

### Experiment & Data Documentation (4 files)
```
EXPERIMENT_GUIDE.md
  └─ How to run experiments with configurations

QUICK_REFERENCE.md
  └─ Assembly sequence & validation quick ref

WORKFLOW_DATA_IO_GUIDE.md
  └─ Data input/output format specifications

node_analysis_corrected.md
  └─ Detailed node analysis & specifications
```

### Framework & Feature Documentation (4 files)
```
HOWTOUSELANGGRAPH.md
  └─ LangGraph framework usage guide

AGENT3_FFA_EXPLAINER.md
  └─ Agent 3 FFA assessment implementation

INTERACTION_ANALYSIS_SPEC.md
  └─ Interaction analysis feature specification

markdown_audit.md
  └─ Complete markdown files audit & analysis
```

**Use Case**: Developer reference for architecture, configuration, and feature understanding.

---

## 📚 Completed Tasks (7 files)

Documentation of successfully completed milestones:

```
IMPLEMENTATION_COMPLETE.md
  └─ app_workflow_v2 completion status (2024-12-24)

DELIVERY_MANIFEST.md
  └─ v2 delivery checklist & validation (2024-12-24)

VALIDATION_CHECKLIST.md
  └─ v2 validation results (2024-12-24)

app_workflow_v2_implementation_blueprint.md
  └─ v2 implementation planning (2024-12-24)

MIGRATION_GUIDE.md (root)
  └─ Migration from v1→v2 & technical changes (2026-01-29)

evaluation_MIGRATION_GUIDE.md
  └─ Evaluation system migration (2026-01-29)

agent_JSON_SAVE_GUIDE.md
  └─ JSON save format specification (2026-01)
```

**Use Case**: Historical reference for understanding past implementation decisions.

---

## 🔍 Outdated/Deprecated (5 files)

Documentation that is no longer current or was not implemented:

```
PROMPT_AUDIT_SUMMARY.md
  └─ Prompt store audit (completed, not active)

OPTIMIZATION_RECOMMENDATIONS.md
  └─ Performance optimization suggestions (not implemented)

node_analysis.md
  └─ Old node analysis (superseded by node_analysis_corrected.md)

workflow_app.md
  └─ Legacy interactive workflow (v1, superseded by app_workflow_v2)

UI_SPEC.md
  └─ Old UI specification (v1, outdated)
```

**Use Case**: Reference for past analysis and decisions. Not currently used.

---

## ✅ TODO & Tracking (4 files)

Old planning and tracking documents:

```
ToDos.md
  └─ Generic TODO list (abandoned)

toDo1203.md
  └─ Dated TODO list (12.03, abandoned)

ToDos_CHECKPOINT_UPDATE.md
  └─ Checkpoint update tasks (completed)

todo_ffa_splitup.md
  └─ FFA splitup planning (abandoned)
```

**Use Case**: Historical record of past planning efforts.

---

## 🔄 Recovery

If you need any archived file:

### Copy technical docs back to root:
```bash
copy archived\md_archive\FILENAME.md .
```

### Copy back to original location:
```bash
# For evaluation files
copy archived\md_archive\evaluation_MIGRATION_GUIDE.md evaluation\MIGRATION_GUIDE.md

# For agent files
copy archived\md_archive\agent_JSON_SAVE_GUIDE.md agent\JSON_SAVE_GUIDE.md
```

### Quick search:
```bash
dir archived\md_archive\*.md | findstr "SEARCH_TERM"
```

---

## 📊 Statistics

| Category | Files | Content Type |
|----------|-------|--------------|
| Technical Documentation | 12 | Guides, specs, analysis |
| Completed Tasks | 7 | Historical milestones |
| Outdated/Deprecated | 5 | Superseded/not used |
| TODO & Tracking | 4 | Abandoned planning |
| **TOTAL** | **28** | **Complete archive** |

---

## 📝 Root Directory (5 Essential Files)

```
✓ README.md                  - Project overview & quick start
✓ GETTING_STARTED.md         - Complete onboarding guide
✓ IMPORTANT_SCRIPTS.md       - Core scripts reference (11 essential scripts)
✓ cleanup.md                 - Python scripts cleanup audit
✓ CLEANUP_COMPLETE.md        - Full cleanup summary
```

**Principle**: Only files needed for first-time users or immediate project overview.

---

## 📝 Notes

- **Purpose**: Reduce root directory clutter while preserving all documentation
- **Searchability**: Use `archived/md_archive/` for historical & technical reference
- **Recovery**: 100% reversible - copy files back if needed
- **Deletion**: No files were deleted, only archived for organization
- **Total Cleanup**: From 78 files → 16 files in root (80% reduction in clutter)

---

**Created**: 2026-06-08  
**Last Updated**: 2026-06-08 (moved 12 additional technical docs)  
**As part of**: Project cleanup & organization initiative


Documentation of successfully completed milestones:

```
IMPLEMENTATION_COMPLETE.md
  └─ app_workflow_v2 completion status (2024-12-24)

DELIVERY_MANIFEST.md
  └─ v2 delivery checklist & validation (2024-12-24)

VALIDATION_CHECKLIST.md
  └─ v2 validation results (2024-12-24)

app_workflow_v2_implementation_blueprint.md
  └─ v2 implementation planning (2024-12-24)

MIGRATION_GUIDE.md (root)
  └─ Migration from v1→v2 & technical changes (2026-01-29)

evaluation_MIGRATION_GUIDE.md
  └─ Evaluation system migration (2026-01-29)

agent_JSON_SAVE_GUIDE.md
  └─ JSON save format specification (2026-01)
```

**Use Case**: Historical reference for understanding past implementation decisions.

---

## 🔍 Outdated/Deprecated (5 files)

Documentation that is no longer current or was not implemented:

```
PROMPT_AUDIT_SUMMARY.md
  └─ Prompt store audit (completed, not active)

OPTIMIZATION_RECOMMENDATIONS.md
  └─ Performance optimization suggestions (not implemented)

node_analysis.md
  └─ Old node analysis (superseded by node_analysis_corrected.md)

workflow_app.md
  └─ Legacy interactive workflow (v1, superseded by app_workflow_v2)

UI_SPEC.md
  └─ Old UI specification (v1, outdated)
```

**Use Case**: Reference for past analysis and decisions. Not currently used.

---

## ✅ TODO & Tracking (4 files)

Old planning and tracking documents:

```
ToDos.md
  └─ Generic TODO list (abandoned)

toDo1203.md
  └─ Dated TODO list (12.03, abandoned)

ToDos_CHECKPOINT_UPDATE.md
  └─ Checkpoint update tasks (completed)

todo_ffa_splitup.md
  └─ FFA splitup planning (abandoned)
```

**Use Case**: Historical record of past planning efforts.

---

## 🔄 Recovery

If you need any archived file:

### Copy back to root:
```bash
copy archived\md_archive\FILENAME.md .
```

### Copy back to original location:
```bash
# For evaluation files
copy archived\md_archive\evaluation_MIGRATION_GUIDE.md evaluation\MIGRATION_GUIDE.md

# For agent files
copy archived\md_archive\agent_JSON_SAVE_GUIDE.md agent\JSON_SAVE_GUIDE.md
```

---

## 📊 Statistics

| Category | Files | Total Size |
|----------|-------|-----------|
| Completed Tasks | 7 | ~80 KB |
| Outdated/Deprecated | 5 | ~60 KB |
| TODO & Tracking | 4 | ~25 KB |
| **TOTAL** | **16** | **~165 KB** |

---

## 📝 Notes

- **Purpose**: Reduce root directory clutter while preserving all documentation
- **Searchability**: Use `archived/md_archive/` for historical reference
- **Recovery**: 100% reversible - copy files back if needed
- **Deletion**: No files were deleted, only archived for organization

---

**Created**: 2026-06-08  
**As part of**: Project cleanup & organization initiative
