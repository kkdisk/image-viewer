---
name: Code Review
description: A comprehensive framework for performing systematic, high-quality code reviews, ensuring code meets standards for functionality, readability, security, and performance.
---

# Code Review Skill

This skill provides a systematic approach to performing code reviews. As an AI Agent, use this skill to analyze code changes, identify potential issues, and provide constructive feedback to the user.

## Core Principles

1. **Understand the "Why"**: Before diving into the code, understand the requirements, context, and purpose of the changes.
2. **Be Constructive and Clear**: Provide actionable feedback. Instead of just pointing out a problem, suggest a specific solution or alternative approach.
3. **Prioritize**: Distinguish critical bugs from minor stylistic nitpicks.
4. **Holistic View**: Consider how the changes impact the rest of the application, not just the modified files.

## Review Dimensions (The Checklist)

When reviewing code, systematically evaluate the following areas:

### 1. Functionality & Logic
- Does the code fulfill the intended requirements?
- Are there any logical errors or edge cases that haven't been handled?
- Are errors and exceptions caught and handled gracefully?

### 2. Architecture & Design
- Does the code follow the existing architectural patterns of the project?
- Is the code modular, cohesive, and loosely coupled?
- Are appropriate data structures and algorithms used?

### 3. Readability & Maintainability
- Are variables, functions, and classes named clearly and descriptively?
- Is the code easy to read and understand (avoiding overly clever or complex one-liners)?
- Are comments used effectively to explain *why* something is done, rather than *what* is done?
- Are there any "magic numbers" or hardcoded values that should be constants?

### 4. Performance
- Are there any inefficient loops, unnecessary database queries, or excessive network calls?
- Is memory managed correctly? Are there potential memory leaks?
- Can expensive operations be cached or optimized?

### 5. Security
- Is input from users or external systems validated and sanitized?
- Are there any vulnerabilities to common attacks (e.g., SQL injection, XSS, CSRF)?
- Is sensitive data (passwords, API keys, PII) handled securely and not logged?

### 6. Testing
- Are there unit tests for the new functionality?
- Do the tests cover happy paths, edge cases, and error conditions?
- Are there integration tests if components interact?

## Execution Process

When requested to perform a code review, follow these steps:

1. **Gather Context**: Ask the user for the goal of the code, or review any linked issues/requirements.
2. **Analyze Changes**: Use tools like `view_file` to read the files mentioned by the user. If reviewing a whole project, use `grep_search` and `list_dir` to understand the structure before diving deep.
3. **Draft Findings**: Keep a running list of observations categorized by severity.
4. **Compile Report**: Create a structured summary using the reporting format described below.

## Reporting Format

Present your code review to the user using this markdown structure:

```markdown
## Code Review Summary
*A brief summary of your overall impression of the code and the implemented changes.*

### 🛑 Critical Issues (Must Fix)
*Bugs, security vulnerabilities, or major architectural flaws that block the code from being acceptable.*
- [File:Line] - Issue description. **Suggestion**: Proposed fix.

### ⚠️ Medium Priority (Should Fix)
*Performance concerns, poor error handling, missing tests, or significant readability issues.*
- [File/Component] - Issue description. **Suggestion**: Proposed fix.

### 📝 Minor / Nitpicks (Consider Fixing)
*Stylistic inconsistencies, minor refactoring opportunities, typo fixes, or naming suggestions.*
- [File] - Suggestion.

### ✅ Positive Feedback
*Acknowledge what was done well! Good design choices, clean implementations, or thorough testing.*
```

## Example Usage

When reviewing a function, you might provide feedback like:

> **🛑 Critical Issue in `utils/auth.py` line 45**
> `password == user.password` is vulnerable to timing attacks and doesn't appear to be checking a hashed password.
> **Suggestion**: Use a secure hashing library comparison function, such as `secrets.compare_digest` or `bcrypt.checkpw`.
