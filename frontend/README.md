# Coding Workshop - Frontend Code

## Overview

This folder contains React frontend application with hello world example.

## Prerequisites

- React - JavaScript library for building user interfaces
- React Router - Client-side routing for React
- Material UI - Comprehensive UI component library

## Structure

```
coding-workshop-participant/
├── frontend/              # React frontend
│   ├── public/              # Public assets
│   ├── src/                 # Source code
│   │   ├── pages/             # Page components
│   │   ├── components/        # Reusable components
│   │   ├── services/          # API client
│   │   └── App.js             # Main app
│   ├── .env.sample          # React environment variables
│   ├── eslint.config.js     # ESLint JS tool configuration
│   ├── index.html           # Landing page
│   ├── package.json         # App metadata with dependencies
│   ├── README.md            # Frontend guide (YOU ARE HERE)
│   └── vite.config.js       # Vite build tool configuration
├── ...
```

## Usage

### Local Development

To run your application locally:

```sh
./bin/start-dev.sh
```

To view your application, open the browser and navigate to `http://localhost:3000`.

### Cloud Deployment

To deploy your frontend to AWS:

```sh
./bin/deploy-frontend.sh
```

To view your application, open the browser and navigate to CloudFront URL.

## Testing

### Unit & component tests (Vitest + React Testing Library)

```sh
npm test              # run once
npm run test:coverage # run with a coverage report
```

### End-to-end (E2E) tests (Playwright)

E2E tests drive a real browser through the critical user workflows — sign-in,
the dashboard, project CRUD, and the resource over-allocation guard — against
the running application.

```sh
npm run test:e2e
```

The suite is **self-contained**: `playwright.config.js` starts both servers and
seeds the database automatically, so nothing needs to be running first.

* **`webServer`** boots the frontend (Vite, port 3000) and the backend
  (`bin/local-dev-server.py`, port 3001). If those servers are already running
  locally, they are reused; in CI (`CI=1`) they are started fresh and torn down
  when the run finishes.
* **`globalSetup`** (`e2e/global-setup.js`) applies the schema
  (`backend/migration-service/schema.sql`) and the idempotent demo seed
  (`bin/seed-e2e.sql`) so the tests always have a known dataset — including an
  over-allocated person and an over-budget project. Set `E2E_SKIP_DB_SETUP=1`
  if the database is provisioned by a separate step.

**Prerequisites**

1. **PostgreSQL** reachable via the standard variables (defaults shown):

   | Variable | Default |
   | --- | --- |
   | `POSTGRES_HOST` | `localhost` |
   | `POSTGRES_PORT` | `5432` |
   | `POSTGRES_USER` | `test` |
   | `POSTGRES_PASS` | `test` |
   | `POSTGRES_NAME` | `test` |

   `psql` must be on `PATH` (used by `globalSetup`).
2. **Python backend dependencies** available to `python3` so the auto-started
   backend can import them: `pip install pg8000 PyJWT`.
3. **The Playwright browser**, installed once: `npx playwright install chromium`.

**Test logins** (seeded): `admin@acme.example` / `ChangeMe!123` (ADMIN); every
other seeded user uses `Passw0rd!`.

**CI example**

```sh
# with a Postgres service available on localhost:5432
cd frontend
npm ci
npx playwright install --with-deps chromium
pip install pg8000 PyJWT
CI=1 npm run test:e2e
```

## Clean Up

To remove all deployed resources (including frontend):

```sh
./bin/cleanup-environment.sh
```

**Warning**: This removes all infra resources. Cannot be undone.
