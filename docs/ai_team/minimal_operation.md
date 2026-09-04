# Fairies AI Team — Minimal Operation

## Purpose

Use the AI development team for small Fairies tasks while keeping final Git decisions under human control.

## Daily rule

- Fairies development is the main work.
- Environment improvement is limited to one item and about one hour per day.
- Fix problems that occurred in actual use.
- Move theoretical improvements to the backlog.

## Start a task

1. Define one small task with measurable acceptance criteria.
2. Create one task directory containing:
   - `task-brief.json`
   - `approval.json`
3. Confirm that all assigned worktrees are clean.
4. Run the following command:

    pwsh -File C:\Users\sakag\other\fairies-integration\scripts\ai_team\Start-FairiesTask.ps1 `
        -TaskDirectory <task-directory>

## Success check

Confirm:

- `stage` is `COMPLETE`.
- `reason_code` is `NONE`.
- The implementation Agent succeeded.
- Test/Review returned `APPROVE`.
- Only authorized files changed.
- No Agent staged or committed changes.

`READY_FOR_PHASE3C` is the legacy schema name for an approved result. It does not start another phase.

## Human completion

1. Read the changed files.
2. Read the Agent and Test/Review reports.
3. Run the relevant test manually.
4. Stage only the approved files.
5. Commit from the assigned Agent worktree.
6. Integrate the approved commit into `agent/integration`.
7. Test again in Integration.
8. Fast-forward `main` and push.

## Failure

When the result is `BLOCKED`:

1. Stop.
2. Read `result-manifest.json` and the Agent status files.
3. Confirm that Git state is safe.
4. Fix only the problem required to resume the task.
5. Timebox one problem to about one hour.