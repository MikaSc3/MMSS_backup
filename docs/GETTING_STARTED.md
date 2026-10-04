# Getting started

## Environment

The CAD workflow requires a Python environment with pythonOCC. The environment
used during development is:

```text
C:\Users\Mika\miniforge3\envs\apa-occ\python.exe
```

Install the repository as an editable package when setting up a new
environment:

```powershell
python -m pip install -e ".[llm,user-agent,ui,cad-rendering]"
```

Provider credentials and endpoints are read from the repository `.env` files
by `assembly_automation.workflows.runtime.environment`. Do not put credentials
in YAML configuration or source files.

## Product UI

```powershell
python run_app.py
```

The UI creates a disposable draft session at startup. Upload a STEP file and
optional context documents in **Data upload**, then start processing. Existing
sessions under `data/sessions` can be resumed from the session selector.

## Terminal workflow

```powershell
python run_workflow.py
```

Useful options:

```text
--input-dir PATH       directory containing STEP/STP files
--step-file PATH       run one explicit file
--config PATH          settings file; defaults to configs/appsettingsv3.yaml
--output-root PATH     parent directory for new sessions
--session-root PATH    resume into an explicit session directory
--context TEXT         additional workflow context
--constraints TEXT     assembly-sequence constraints
--auto                 select the first input and approve the first sequence
```

## Focused developer scripts

Scripts under `scripts/` exercise individual product components. The most
useful are:

```powershell
python scripts/test_stepparser.py
python scripts/test_assembly_analysis.py
python scripts/test_monopart_analysis.py
python scripts/test_user_facing_agent.py
python scripts/create_sequence_overview.py --help
```

## Tests

```powershell
python -m pytest tests
```

CAD tests need the pythonOCC environment. LLM unit tests use test doubles and
do not make provider calls unless a script explicitly performs a live run.

## Historical and research code

Research evaluation lives in `research/evaluation`, experiment settings in
`research/configs`, and legacy experiment runners in `research/scripts`.
Superseded UI prototypes and their old numbered launchers are retained under
`archived/`. The previous detailed workflow guide remains in
`docs/legacy_workflow_guide.md`.
