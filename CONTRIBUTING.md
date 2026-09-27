# Contributing

Thanks for your interest in CodeSentinel. Issues and pull requests are welcome.

## Development setup

Follow [Setup](README.md#setup) in the README. You need Python 3.12+, Node 20+, and a free Gemini API key only for live agent runs — the test suites don't use the API.

## Before opening a pull request

```bash
# backend/
python scripts/verify_demo_repo.py   # demo repo + bug manifest still consistent
python -m pytest                     # agent loop + API tests (scripted LLM, no API key)

# frontend/
npm run lint
npm run build
```

CI runs the same checks on every push.

## Guidelines

- **Keep the reasoning-trace shape stable.** Every step is a `reasoning_steps` row (`plan`, `tool_call`, `result`, `reflection`); the dashboard, database and WebSocket all depend on it.
- **Never let the agent see the answers.** Planted-bug ground truth lives in `backend/eval/bugs.json`, outside anything the agent can read.
- **UI copy** is precise, plain, and honest about uncertainty. Shared strings live in `frontend/src/copy.js`.
- **Adding a planted bug:** add it to `demo-repo/`, add its `buggy`/`fixed` snippets to `bugs.json`, and check `verify_demo_repo.py` still reports `RESULT: OK`.
- Prefer small, focused pull requests with a clear description of the change and how you tested it.
