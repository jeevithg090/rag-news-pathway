# Onboarding questionnaire

React + Vite app that asks a new reader nine short questions (topics, reading depth, formats,
regions, …) and saves the answers through `POST /api/onboarding`. The chosen categories seed the
reader's personalisation profile.

```bash
npm install
npm run dev      # http://localhost:3000, proxies /api to the backend on :8000
npm run lint
npm run build    # outputs dist/, served by FastAPI at /onboarding/
```

See the [project README](../../README.md) for the full setup.
