# Aetherdesk-Call-Center — one-shot repo cleanup
# Run from repo root: .\cleanup.ps1
# After it completes, delete this file and push again.

Set-Location $PSScriptRoot

Write-Host "Step 1: Runtime artifacts" -ForegroundColor Cyan
$artifacts = @(
  'server-error.log','server.err','server.log','server_log.txt',
  'debug_screenshot.png','debug_dashboard.txt','debug_ui_text.txt',
  'security_validation_results.json','test_call_record.txt'
)
foreach ($f in $artifacts) { if (Test-Path $f) { git rm --force $f } }

Write-Host "Step 2: Debug scripts" -ForegroundColor Cyan
$debug = @('debug_api.py','debug_inline.py','debug_start.py','debug_tenant.py','debug_ui.py')
foreach ($f in $debug) { if (Test-Path $f) { git rm --force $f } }

Write-Host "Step 3: Duplicate launcher scripts" -ForegroundColor Cyan
$launchers = @(
  'clean_start.py','fresh_start.py','simple_start.py','quick_start.py',
  'start_all.py','start_api.py','start_ui.py','start_visible.py',
  'start_debug.py','start_desktop.py','start_and_test.py','open_visible.py',
  'final_run.py','full_restart.py','launch.py','launch_clean.py',
  'launch.bat','run_call_center.bat','run_dev.bat','start_call_center.bat',
  'start_api_cmd.cmd','start_with_gemma.ps1','start.sh',
  'run_call_center.py','run_simple.py','run_server.py','serve.py'
)
foreach ($f in $launchers) { if (Test-Path $f) { git rm --force $f } }

Write-Host "Step 4: Root-level test files" -ForegroundColor Cyan
$tests = @(
  'e2e_test.py','full_e2e_test.py','run_e2e_full.py','run_e2e_browser.py',
  'run_full_e2e.py','run_tests.py','run_bug_audit_tests.py',
  'quick_test.py','restart_test.py','restart_and_test.py',
  'playwright_setup.py','visible_test.py','ui_explore.py',
  'test_auth.py','test_endpoints.py'
)
foreach ($f in $tests) { if (Test-Path $f) { git rm --force $f } }

Write-Host "Step 5: Fix/check/verify scripts -> scripts/" -ForegroundColor Cyan
$toMove = @('fix_db.py','fix_indent.py')
foreach ($f in $toMove) {
  if (Test-Path $f) {
    Copy-Item $f "scripts\$f" -Force
    git add "scripts\$f"
    git rm --force $f
  }
}
$checks = @('check.py','check_server.py','check_servers.py','verify.py','verify_and_launch.py')
foreach ($f in $checks) { if (Test-Path $f) { git rm --force $f } }

Write-Host "Step 6: Duplicate docs" -ForegroundColor Cyan
$docs = @('BUILD_SUMMARY.md','AUDIT.md','AUDIT_REPORT.md','PROJECT_OVERVIEW.md')
foreach ($f in $docs) { if (Test-Path $f) { git rm --force $f } }

Write-Host "Step 7: Consolidate Dockerfiles" -ForegroundColor Cyan
if (Test-Path 'Dockerfile.optimized') {
  Copy-Item 'Dockerfile.optimized' 'Dockerfile' -Force
  git add 'Dockerfile'
  git rm --force 'Dockerfile.api' 'Dockerfile.optimized'
}

Write-Host "Step 8: Harden .gitignore" -ForegroundColor Cyan
$ignoreAppend = @"

# Runtime logs
*.log
*.err
server_log.txt

# Debug artifacts
debug_*.txt
debug_*.png
security_validation_results.json
test_call_record.txt

# Debug scripts
debug_*.py

# Databases
*.db
*.db-shm
*.db-wal
.coverage
htmlcov/

# Downloads & binaries
.downloads/
*.zip
*.tar.gz

# Scratch
scratch/
"@
Add-Content .gitignore $ignoreAppend
git add .gitignore

Write-Host "Step 9: Commit" -ForegroundColor Cyan
git commit -m "chore: remove 40+ debug/launcher/test/doc artifacts, consolidate Dockerfile, harden .gitignore"

Write-Host "Step 10: Push" -ForegroundColor Cyan
git push origin main

Write-Host "Done! Delete cleanup.ps1 and push one more time." -ForegroundColor Green
