# Tests and checks

Run these commands from the repository root. Several suites use the local corpus;
[acquire the sources](../sources/README.md) before running the complete suite.

## Run the regression suite

```powershell
$env:PYTHONUTF8='1'
python tests/run_all.py
```

The suite checks source permissions, loaders, search, relationships, workspace
assessment guidance, rendering and package contents.

For changes to workspace content or search terms:

```powershell
python tests/test_control_workspace.py
python tests/test_extended.py
python tests/test_terms.py
```

## Check data and packaging

```powershell
python tools/revalidate_corpus.py
python tools/analyse_topics.py
python -m wacc.packaging
```

The first two commands rewrite the corpus review and topic-frequency reports.
The packaging check reports files that must be excluded from distribution.
See the [script guide](../tools/README.md) for output locations.

## Assessment command fixtures

`test_assessment_commands.ps1` uses offline fixtures to exercise selected command
behaviour. The [assessment authoring guide](../sources/add-framework.md#5-add-or-revise-the-assessments)
includes the PowerShell commands and documentation checks. Live environment checks
remain part of the assessment instructions shown in the application.

## Test fixtures

`fixtures/onboarding-catalog.json` is the fictional source used by the
[framework import guide](../sources/add-framework.md).
