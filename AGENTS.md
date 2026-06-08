# Agent Instructions

- Never use, recommend, or tell the user to run `git clean` in this repository.
- This includes `git clean -fd`, `git clean -fdx`, dry-run/preview variants such as `git clean -n`, and any command sequence that invokes `git clean`.
- This repository may contain important untracked local assets and symlinked files that `git clean` can destroy.
- Prefer inspecting untracked files with `git status --short` and leave untracked files alone unless the user explicitly identifies a specific file to remove.
