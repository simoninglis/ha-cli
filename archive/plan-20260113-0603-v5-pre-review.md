# ha-cli Implementation Plan v5

**Created:** 2025-12-05
**Status:** Active Development
**Source:** Fresh Codex review 2025-12-05

---

## Executive Summary

This plan addresses security vulnerabilities, code quality issues, and new feature development identified during a comprehensive codebase review. Priority is given to fixing a YAML injection vulnerability and duplicate method definitions before proceeding with the new areas domain feature.

---

## Issue Summary

| # | Priority | Issue | File(s) | Effort |
|---|----------|-------|---------|--------|
| 31 | CRITICAL | Unsafe YAML Loading | utils.py, service.py, models.py + 4 more | Low |
| 32 | CRITICAL | Duplicate `get_automation_states()` | client.py | Low |
| 33 | IMPORTANT | Missing Exception Context Chains | client.py | Medium |
| 35 | IMPORTANT | Silent Exception Handlers | entities/service.py | Low |
| 37 | IMPORTANT | Undefined `EXIT_HA_ERROR` | Multiple files | Low |
| 36 | IMPORTANT | CLI Modules Lack Test Coverage | cli.py, audit/cli.py, automations/cli.py | High |
| 30 | IMPORTANT | Add `ha-cli areas` Domain | New domain | High |
| 34 | NICE-TO-HAVE | Ruff Configuration Deprecated Keys | pyproject.toml | Low |

---

## Phase 1: Critical Security & Bug Fixes

### Issue 31: Unsafe YAML Loading - Code Injection Vulnerability

**References:** docs/ISSUES.md #31

**Problem:**
Multiple files use `yaml.load()` instead of `yaml.safe_load()`, allowing arbitrary code execution when loading untrusted YAML.

**Solution:**
Replace all `yaml.load()` with `yaml.safe_load()`. For ruamel.yaml, ensure safe loading mode.

**Acceptance Criteria:**
- [x] All `yaml.load()` replaced with `yaml.safe_load()` (where round-trip not needed)
- [x] ruamel.yaml instances use safe loading or documented as safe (RoundTripConstructor)
- [x] Tests pass after changes
- [x] No YAML injection vectors remain

**Implementation:**
1. Update `ha_cli/common/utils.py:105`
2. Update `ha_cli/domains/dashboards/service.py:241`
3. Update `ha_cli/domains/automations/models.py:79`
4. Verify ruamel.yaml usage in `file_automation_manager.py` is safe
5. Update `ha_automation/cli.py:615`
6. Update test files
7. Run full test suite

---

### Issue 32: Duplicate `get_automation_states()` Method Definition

**References:** docs/ISSUES.md #32

**Problem:**
Method defined twice in `client.py` at lines 498 and 742, causing shadowing.

**Solution:**
Remove the duplicate definition and consolidate logic.

**Acceptance Criteria:**
- [x] Single `get_automation_states()` method exists
- [x] Method functionality preserved
- [x] All callers work correctly
- [x] Tests pass

**Implementation:**
1. Read both implementations to understand differences
2. Determine which implementation is correct/complete
3. Remove duplicate definition
4. Update any callers if needed
5. Run tests to verify

---

## Phase 2: Important Code Quality

### Issue 33: Missing Exception Context Chains (PEP 3134)

**References:** docs/ISSUES.md #33

**Problem:**
15+ exception handlers in `client.py` raise new exceptions without `from err`, losing debugging context.

**Solution:**
Add `from err` to all exception raises in except blocks.

**Acceptance Criteria:**
- [ ] All `raise` statements in `except` blocks use `from err` or `from None`
- [ ] Original exception context preserved
- [ ] ruff B904 violations resolved

**Implementation:**
1. Run `ruff check --select B904 ha_cli/common/client.py`
2. Fix each violation by adding `from err`
3. Verify with `ruff check`

---

### Issue 35: Silent Exception Handlers in Entity Service

**References:** docs/ISSUES.md #35

**Problem:**
Bare `except: pass` blocks at lines 620 and 745 silently swallow exceptions.

**Solution:**
Add logging to exception handlers.

**Acceptance Criteria:**
- [ ] No bare `except: pass` blocks remain
- [ ] Exceptions logged at debug level
- [ ] ruff S110 violations resolved

**Implementation:**
1. Add `logger.debug()` calls to both locations
2. Consider using specific exception types
3. Verify with `ruff check --select S110`

---

### Issue 37: Undefined Name `EXIT_HA_ERROR`

**References:** docs/ISSUES.md #37

**Problem:**
6 instances of undefined name causing potential runtime errors.

**Solution:**
Define constant in common module or replace with actual value.

**Acceptance Criteria:**
- [ ] All `EXIT_HA_ERROR` references resolved
- [ ] Constant defined centrally if needed
- [ ] No F821 ruff errors

**Implementation:**
1. Run `ruff check --select F821` to find all occurrences
2. Determine appropriate value (likely `2` based on CLI conventions)
3. Define in `ha_cli/common/cli_utils.py` or replace inline
4. Update all references
5. Verify with ruff

---

### Issue 36: CLI Modules Lack Test Coverage

**References:** docs/ISSUES.md #36

**Problem:**
CLI entry points have 0% test coverage, risking undetected bugs.

**Solution:**
Add integration tests using typer's CliRunner.

**Acceptance Criteria:**
- [ ] CLI tests added for main entry points
- [ ] Tests cover happy path and error cases
- [ ] Coverage for CLI modules > 50%

**Implementation:**
1. Create `tests/test_cli.py` for main CLI
2. Create `tests/audit/test_cli.py` for audit commands
3. Create `tests/automations/test_cli.py` for automation commands
4. Use `CliRunner` to invoke commands
5. Mock external dependencies (HAClient)
6. Test error handling paths

---

## Phase 3: New Features

### Issue 30: Add `ha-cli areas` Domain for Area and Registry Metadata

**References:** docs/ISSUES.md #30

**Problem:**
No way to query or audit Home Assistant area/registry metadata. 99.3% of entities lack area assignments.

**Solution:**
Implement new `areas` domain with list, show, and audit capabilities.

**Acceptance Criteria:**
- [x] `ha-cli areas list` shows all areas with entity/device counts
- [x] `ha-cli areas show` displays full area details
- [x] `ha-cli areas audit` identifies naming issues and empty areas
- [x] All commands support `--porcelain` for structured JSON output
- [x] Unit tests for new functionality

**Implementation:**
1. ✅ Create `ha_cli/domains/areas/` directory structure
2. ✅ Implement models (`Area`, `AreaWithCounts`, `Device`, `Floor`, `Label`, `EntityRegistryEntry`)
3. ✅ Implement service with WebSocket calls to registry APIs
4. ✅ Implement CLI commands (list, show, floors, labels, audit, version)
5. ✅ Add audit command to areas domain (not audit domain - keeps areas self-contained)
6. ✅ Add porcelain output support
7. ✅ Write unit tests (38 tests)
8. Documentation updated via implementation

---

## Phase 4: Nice-to-Haves

### Issue 34: Ruff Configuration Uses Deprecated Top-Level Keys

**References:** docs/ISSUES.md #34

**Problem:**
Deprecation warnings on every ruff run due to outdated config format.

**Solution:**
Move config to `[tool.ruff.lint]` section.

**Acceptance Criteria:**
- [ ] No deprecation warnings from ruff
- [ ] Linting behavior unchanged

**Implementation:**
1. Edit `pyproject.toml`
2. Move `select`, `ignore`, `per-file-ignores` to `[tool.ruff.lint]`
3. Verify no warnings with `ruff check`

---

## Quality Gates

Before marking plan complete:
1. Tests pass: `poetry run pytest`
2. Linting clean: `poetry run ruff check ha_cli/`
3. No critical ruff errors: `poetry run ruff check --select F821,B904,S110`
4. Coverage maintained: `poetry run pytest --cov=ha_cli`

---

## Execution Order

Implementation sequence considering dependencies:

1. ✅ **Issue 31** - Fix YAML security vulnerability (Phase 1) - CRITICAL
2. ✅ **Issue 32** - Remove duplicate method (Phase 1) - CRITICAL
3. **Issue 37** - Fix undefined EXIT_HA_ERROR (Phase 2) - blocks other work
4. **Issue 35** - Fix silent exception handlers (Phase 2)
5. **Issue 33** - Add exception context chains (Phase 2)
6. **Issue 34** - Update ruff config (Phase 4) - quick win
7. **Issue 36** - Add CLI test coverage (Phase 2)
8. ✅ **Issue 30** - Implement areas domain (Phase 3) - COMPLETED

---

## References

- docs/ISSUES.md - Canonical issue tracker
- archive/ - Previous plan versions
- docs/entity-naming-conventions.md - Naming standards for area audit
