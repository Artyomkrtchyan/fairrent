# Working with the repository

Repository: https://github.com/Artyomkrtchyan/fairrent

## First-time setup

Install Git and authenticate with GitHub using your own account. Accept the repository invitation before cloning.

```bash
git clone https://github.com/Artyomkrtchyan/fairrent.git
cd fairrent
git config user.name "Your Name"
git config user.email "your-github-email@example.com"
```

Use your GitHub email or GitHub-provided no-reply address. Follow the component README for environment setup.

## Start a task

Choose an assigned issue whose dependencies are complete. Move it to In Progress and create a short-lived branch from the latest main.

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/A03-listing-pipeline
```

Use your task's code and topic in the branch name. Prefixes: feat/, fix/, docs/, chore/. Keep each branch focused on one task.

## Commit and push

Review your changes and run the checks relevant to your component. Stage only intended files.

```bash
git status
git diff
git add data_pipeline/
git diff --cached
git commit -m "feat: normalize rental listing prices"
git push -u origin feat/A03-listing-pipeline
```

Replace the path and branch with your own. Never commit .env files, AWS keys, raw personal data, or large model artifacts.

After the first push, later updates use:

```bash
git add data_pipeline/
git commit -m "fix: handle missing listing area"
git push
```

## Open a pull request

1. Open the repository on GitHub and select Compare & pull request.
2. Set base to main and compare to your task branch.
3. Describe the change, checks performed, and any contract changes. Add `Closes #123` using the actual issue number.
4. Request a review from another teammate and move the issue to Review.
5. Address feedback, push updates to the same branch, and wait for checks and review.
6. Use Squash and merge after approval. Confirm the issue is closed and move it to Done if the board did not update automatically.

Task codes such as A03 are planning identifiers; `Closes #...` must use the GitHub issue number.

## Bring main into an active branch

Commit your current work first, then:

```bash
git fetch origin
git switch feat/A03-listing-pipeline
git merge origin/main
```

If conflicts occur, inspect each conflicting file, resolve the intended final content with the affected teammate, remove conflict markers, run checks, and finish the merge:

```bash
git add path/to/resolved-file
git commit
git push
```

To abandon an unfinished merge and return to its starting state, use `git merge --abort`. Avoid force-pushing shared branches or resetting another person's work.

## After a merge

```bash
git switch main
git pull --ff-only origin main
git branch -d feat/A03-listing-pipeline
```

Start the next task from this updated main.

## Team coordination

- Confirm data/API changes with consumers before changing the contract.
- Link blocking tasks in the issue; do not mark blocked work Ready.
- Include tests and documentation with the implementation.
- Report integration problems in the relevant issue with reproducible steps.
- Keep incomplete work on task branches so main remains usable.

## Pull-request checks

See [C07 CI checks and review gate](C07-continuous-integration.md) for the four
component checks, image tag conventions, failure-test evidence and the current
private-repository plan limitation on enforced main protection.
