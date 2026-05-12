# Errors

Command failures and integration errors.

---

## [ERR-20260511-001] automation_memory_path

**Logged**: 2026-05-11T17:56:00+08:00
**Priority**: low
**Status**: pending
**Area**: config

### Summary
PowerShell session did not expose CODEX_HOME while writing automation memory.

### Error
```text
Join-Path : Cannot bind argument to parameter 'Path' because it is null.
```

### Context
- Command attempted to expand `$env:CODEX_HOME\automations\automation-2\memory.md`.
- The automation prompt provided the intended path, but the shell environment variable was unset.
- Fallback path used: `C:\Users\28349\.codex\automations\automation-2\memory.md`.

### Suggested Fix
Use `C:\Users\28349\.codex` as the fallback Codex home when `$env:CODEX_HOME` is empty in local automation runs.

### Metadata
- Reproducible: unknown
- Related Files: C:\Users\28349\.codex\automations\automation-2\memory.md

---

## [ERR-20260512-001] Automation memory path env missing

**Logged**: 2026-05-12T13:04:44+08:00
**Priority**: low
**Status**: resolved
**Command**: Write automation memory using $env:CODEX_HOME
**Error**: $env:CODEX_HOME was null in this PowerShell environment, so Join-Path failed before writing memory.
**Resolution**: Retried with fallback C:\Users\28349\.codex and successfully wrote C:\Users\28349\.codex\automations\automation-2\memory.md.

