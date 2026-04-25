---
name: Code Review
description: A comprehensive framework for performing systematic, high-quality code reviews, ensuring code meets standards for functionality, readability, security, and performance. Supports git-based change review and full-file review workflows.
---

# Code Review Skill

This skill provides a systematic, repeatable approach to performing code reviews for the **Image Viewer** project — a PyQt6-based desktop application written in Python.

As an AI Agent, use this skill whenever:
- The user asks for a "code review" or "review code"
- The user asks to "check git changes", "review latest commit", or "check what changed"
- The user asks to review a specific file or module

---

## Project Context

| Item | Detail |
|------|--------|
| Language | Python 3.10+ |
| Framework | PyQt6, Pillow, numpy |
| Build Tool | PyInstaller (via `build.py`) |
| Test Framework | pytest, pytest-qt |
| Linter | flake8 |
| CI/CD | GitHub Actions (`python-app.yml`) |
| Package Layout | `image_viewer/` (core, ui, utils sub-packages) |
| Config | Instance-based `Config` class, loaded from `config.json` |

### Key Architectural Patterns
- **MVC-like separation**: `core/` (model & logic), `ui/` (view & widgets), `utils/` (decorators, helpers)
- **Worker threads**: Background tasks in `core/workers.py` using Qt threading
- **Theme system**: QSS-based theming via `ui/theme_manager.py` and `dark_theme.qss`
- **Resource management**: Centralized in `core/resource_manager.py`
- **Config-driven**: All tunable parameters live in `Config` with JSON override support

---

## Core Principles

1. **Understand the "Why"**: Before diving into the code, understand the requirements, context, and purpose of the changes.
2. **Be Constructive and Clear**: Provide actionable feedback. Instead of just pointing out a problem, suggest a specific solution or alternative approach.
3. **Prioritize**: Distinguish critical bugs from minor stylistic nitpicks.
4. **Holistic View**: Consider how the changes impact the rest of the application, not just the modified files.
5. **Respect the Project Language**: This project uses Traditional Chinese (繁體中文) in comments, docstrings, UI strings, and commit messages. Produce review reports in Traditional Chinese by default unless the user requests otherwise.

---

## Review Workflows

### Workflow A: Git-Based Change Review (Most Common)

Use this when the user says "review latest changes", "check git", etc.

#### Step 1 — Identify Changes

```bash
# Check recent commits
git log --oneline -10

# Show diff of latest commit
git diff HEAD~1 HEAD

# Or show uncommitted changes
git diff
git diff --cached    # staged changes

# For multi-commit review
git diff <base-commit>..<target-commit>
```

#### Step 2 — Gather Changed Files

```bash
# List only changed file names
git diff --name-only HEAD~1 HEAD

# With change stats
git diff --stat HEAD~1 HEAD
```

#### Step 3 — Review Each File

For each changed file, use `view_file` to read the full context around changes. Do NOT review diffs in isolation — always understand the surrounding code.

#### Step 4 — Run Automated Checks

```bash
# Lint check (same as CI)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Run tests
python -m pytest
```

#### Step 5 — Compile Report

Use the **Reporting Format** below.

---

### Workflow B: Full File / Module Review

Use this when the user says "review this file", "review the ui module", etc.

1. Use `list_dir` to understand the scope of the module.
2. Use `view_file` to read every file in the module.
3. Run lint and tests.
4. Apply all **Review Dimensions** below.
5. Compile report.

---

### Workflow C: Pull Request Review

Use this when the user says "review PR", "review pull request", etc.

1. Identify the PR branch: `git branch -a`
2. Diff against main: `git diff main...<branch>`
3. Check commit messages for clarity.
4. Follow steps 3–5 from Workflow A.

---

## Review Dimensions (Checklist)

When reviewing code, systematically evaluate the following areas. Check every applicable item.

### 1. Functionality & Logic
- [ ] Does the code fulfill the intended requirements?
- [ ] Are there logical errors or unhandled edge cases?
- [ ] Are errors and exceptions caught and handled gracefully?
- [ ] Does the code handle `None`, empty collections, and boundary values?
- [ ] For image processing: are large images, corrupt files, and unsupported formats handled?

### 2. Architecture & Design
- [ ] Does the code follow the existing MVC-like separation (`core/`, `ui/`, `utils/`)?
- [ ] Is business logic kept out of UI code?
- [ ] Are new configurable values added to `Config` instead of being hardcoded?
- [ ] Does the code use appropriate Qt signals/slots patterns?
- [ ] Are worker threads used for long-running operations (not blocking the UI thread)?
- [ ] Is the code modular, cohesive, and loosely coupled?

### 3. Readability & Maintainability
- [ ] Are variables, functions, and classes named clearly and descriptively?
- [ ] Is the code easy to read (no overly clever one-liners)?
- [ ] Are comments in Traditional Chinese and explain *why*, not *what*?
- [ ] Are there "magic numbers" that should be `Config` constants?
- [ ] Are f-strings or logging used consistently (not print statements)?

### 4. Performance
- [ ] Are there inefficient loops over large image data?
- [ ] Is `Pillow` used correctly (lazy loading, appropriate resampling filters)?
- [ ] Are thumbnail operations using draft mode and intermediate sizing (as per `Config`)?
- [ ] Is memory managed correctly? Are large images released after processing?
- [ ] Could expensive operations benefit from caching or background workers?
- [ ] Is `psutil` memory monitoring respected (threshold checks)?

### 5. Security & Robustness
- [ ] Is file I/O wrapped in try/except with sensible fallbacks?
- [ ] Are file paths validated before use?
- [ ] Is no sensitive data logged or hardcoded?
- [ ] Are archive operations (7z) safely handling untrusted content?
- [ ] Is `MAX_IMAGE_FILE_SIZE` enforced to prevent OOM?

### 6. Testing
- [ ] Are there unit tests for new/changed functionality?
- [ ] Do tests cover happy paths, edge cases, and error conditions?
- [ ] Are Qt-dependent tests using `pytest-qt` fixtures?
- [ ] Do tests run successfully with `QT_QPA_PLATFORM=offscreen`?

### 7. Compatibility & Build
- [ ] Does the code work with Python 3.10+?
- [ ] Does it handle both source-run and PyInstaller-bundled modes (`sys._MEIPASS`)?
- [ ] Are new dependencies added to `requirements.txt` (or `requirements-optional.txt`)?
- [ ] Does the CI pipeline (`python-app.yml`) need updating?
- [ ] Is Pillow version compatibility handled (e.g., `Resampling` vs legacy constants)?

### 8. Git Hygiene
- [ ] Are commit messages clear and descriptive?
- [ ] Are changes logically grouped (not mixing unrelated changes)?
- [ ] Are temporary/debug files excluded (check `.gitignore`)?

---

## Reporting Format

Present your code review using this structure. Write in **Traditional Chinese** by default.

```markdown
## 📋 Code Review 摘要

*對本次變更的整體評價與概述。*

### 審查範圍
- **審查方式**: [Git Diff / 檔案審查 / PR Review]
- **變更範圍**: [涉及的檔案與模組列表]
- **Commit**: [相關的 commit hash(es)]

---

### 🛑 嚴重問題 (必須修正)
*Bug、安全漏洞、或嚴重的架構問題，必須在合併前修正。*
- **[檔案名:行號]** — 問題描述。
  - **建議修正**: 具體的修復方案。

### ⚠️ 中等問題 (建議修正)
*效能問題、錯誤處理不足、缺少測試、或顯著的可讀性問題。*
- **[檔案/元件]** — 問題描述。
  - **建議修正**: 具體的改善方案。

### 📝 小建議 / 風格建議 (可選修正)
*風格不一致、可重構的地方、命名建議等。*
- **[檔案]** — 建議內容。

### ✅ 正面回饋
*值得肯定的好設計、乾淨實作、完善的測試等。*

---

### 📊 自動化檢查結果
- **flake8**: [通過/有警告 — 簡述]
- **pytest**: [通過/失敗 — 簡述]
```

---

## Severity Definitions

| Severity | Icon | Criteria | Action |
|----------|------|----------|--------|
| Critical | 🛑 | Bugs, data loss, security issues, crashes | Must fix before merge |
| Medium | ⚠️ | Performance, missing error handling, no tests | Should fix soon |
| Minor | 📝 | Style, naming, documentation, minor refactor | Nice to have |
| Positive | ✅ | Good patterns, clean code, thorough tests | Acknowledge and encourage |

---

## Example Usage

### Example 1: Reviewing a git change

> **🛑 嚴重問題 — `core/image_model.py` 第 87 行**
> 載入圖片時未檢查 `MAX_IMAGE_FILE_SIZE`，大檔案可能導致記憶體耗盡 (OOM)。
> **建議修正**: 在開啟檔案前加入大小檢查：
> ```python
> file_size = os.path.getsize(file_path)
> if file_size > self.config.MAX_IMAGE_FILE_SIZE:
>     raise ValueError(f"檔案過大: {file_size} bytes")
> ```

### Example 2: Architecture feedback

> **⚠️ 中等問題 — `core/editor_window.py`**
> 此檔案已達 46KB / ~1200 行，建議將圖片編輯邏輯拆分到獨立模組 (如 `core/edit_commands.py`)，
> 提升可維護性與可測試性。

### Example 3: Positive feedback

> **✅ 正面回饋 — `config.py`**
> Config 類別設計良好：支援預設值、JSON 覆蓋、型別保證 (`_ensure_tuples`)、及驗證 (`validate`)。
> 這是很好的配置管理模式。
