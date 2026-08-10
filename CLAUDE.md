# Working preferences

- Be very honest. Tell me something I need to know even if I don't want to hear it.
- Push back when something seems wrong — don't just agree with mistakes.
- Ask questions if something is not clear and you need to make a choice. Don't choose randomly — it's something important to what we're doing.
- When you show me a potential error or miss, start your response with the ❗️ emoji.
- **ALWAYS** start replies with a STARTER_CHARACTER + space (default: 🔮). Stack emojis when necessary, don't replace them.

# Coding standards

- **SOLID where it genuinely reduces coupling**, not as a goal in itself. Don't introduce interfaces, dependency injection, or inheritance hierarchies just to tick a box — only when they remove real pain.
- **Self-documenting names.** Variables, functions, types, and modules should read as prose. If you're about to write a comment that explains *what* a line does, rename the thing instead.
- **Comments explain *why*, not *what*.** Reserve them for non-obvious decisions, workarounds, edge cases, references to specs/issues, and business rules that the code alone can't express. Never paraphrase the next line.
- **YAGNI.** No speculative abstractions, config knobs, or "just-in-case" validation for requirements that don't exist yet. Build for what's asked; refactor when the second or third real use case arrives.
- **DRY, but wait for the rule of three.** Two similar blocks are duplication; three are a pattern. Premature deduplication couples things that only look alike.
- **Small, single-purpose functions.** If a function's name needs an "and", split it. If it doesn't fit on a screen, consider splitting it.
- **Prefer composition over inheritance.** Reach for inheritance only for true is-a relationships.
- **Validate at the system boundary** (user input, HTTP, filesystem, third-party APIs). Trust internal callers — don't defensively re-check types the type system already guarantees.
- **No magic numbers or strings.** Name them as constants with the meaning embedded in the name.
- **Match the conventions of the file you're editing** — formatting, naming, imports, patterns. Consistency beats personal preference.
- **Tests describe behavior, not implementation.** Assert on observable outcomes, not on internals the caller doesn't care about.
- **Type everything the language lets you type.** Full type hints in Python, no implicit `any` in TypeScript.

# Git & branching

- **Target PRs at `develop`, not `main`.** `Bump Version` (`.github/workflows/bump-version.yml`) only triggers on `pull_request: closed` events whose base branch is `develop`; a PR opened against `main` never fires it and the version won't bump. `main` only receives the automated `chore/release-*` PR from `Prepare Release`.
- **Never name your own branches with the `chore/bump-version-*`, `chore/release-*`, or `chore/sync-*-to-develop` prefixes.** These are reserved for CI — `Bump Version` and `Prepare Release` create and push branches with those exact names (e.g. `chore/bump-version-1.4.0-beta.1`). A collision makes the workflow's `git checkout -b` or `git push origin` step fail.
- **Apply at most one `bump:major` / `bump:minor` / `bump:patch` label to the PR** when the change warrants a real version bump. `Bump Version` reads that label to pick the bump type; with no label it just increments the beta counter (e.g. `-beta.1` → `-beta.2`).
- Everyday branch names (`feature/...`, `fix/...`, etc.) are otherwise unconstrained — the workflow only looks at the PR's base branch and labels, not the head branch name.
