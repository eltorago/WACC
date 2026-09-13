@echo off
setlocal
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
  echo git is not on PATH. Install it, or add it, then run this again.
  exit /b 1
)

if exist ".git" (
  echo This folder is already a git repository. Run "git status" to see where it stands.
  exit /b 0
)

set EMAIL=
for /f "delims=" %%E in ('git config user.email 2^>nul') do set EMAIL=%%E
if "%EMAIL%"=="" (
  echo git does not know who you are yet. Set it once:
  echo.
  echo     git config --global user.name "Your Name"
  echo     git config --global user.email "you@example.com"
  echo.
  echo Then run this again.
  exit /b 1
)

git init
git symbolic-ref HEAD refs/heads/main
git add -A
if errorlevel 1 (
  echo Staging failed. Nothing has been committed; run "git status".
  exit /b 1
)

git commit ^
 -m "WACC: initial commit of the tool" ^
 -m "18 frameworks, 5321 controls, five tier bands, with provenance and fidelity on every control and link." ^
 -m "What is tracked is what may ship, decided by wacc/packaging.py and enforced by tests/test_packaging.py. The publisher source documents are not here, and neither are the extracts whose text belongs to a publisher who has not licensed it." ^
 -m "364 checks across eleven suites, run lowest layer first. 40 recorded defects can be put back one at a time with tests/run_all.py --injected, each checked to make a named case fail." ^
 -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"

if errorlevel 1 (
  echo The commit did not complete. Nothing has been lost; run "git status".
  exit /b 1
)

echo.
git log --oneline
echo.
echo Untracked or modified after the commit (should be the two import-only extracts):
git status --short
endlocal
