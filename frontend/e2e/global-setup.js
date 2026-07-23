import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(dirname, '..', '..')

// Same variables the Lambdas use; sensible local defaults so a developer with
// the standard localhost Postgres needs no configuration.
const PG_ENV = {
  PGHOST: process.env.POSTGRES_HOST || 'localhost',
  PGPORT: process.env.POSTGRES_PORT || '5432',
  PGUSER: process.env.POSTGRES_USER || 'test',
  PGPASSWORD: process.env.POSTGRES_PASS || 'test',
  PGDATABASE: process.env.POSTGRES_NAME || 'test',
}

/**
 * Runs once before the E2E suite. Applies the schema and the idempotent demo
 * seed so the tests have a known dataset (admin login, an over-allocated
 * person, an over-budget project) regardless of the database's starting state.
 *
 * Set E2E_SKIP_DB_SETUP=1 to skip this (e.g. when the DB is provisioned by a
 * separate CI step).
 */
export default async function globalSetup() {
  if (process.env.E2E_SKIP_DB_SETUP === '1') {
    console.log('[e2e] E2E_SKIP_DB_SETUP=1 — skipping schema/seed')
    return
  }

  const env = { ...process.env, ...PG_ENV }
  const psql = (file) =>
    execFileSync('psql', ['-v', 'ON_ERROR_STOP=1', '-q', '-f', file], { env, stdio: 'inherit' })

  try {
    psql(path.join(REPO_ROOT, 'backend', 'migration-service', 'schema.sql'))
    psql(path.join(REPO_ROOT, 'bin', 'seed-e2e.sql'))
    console.log('[e2e] schema applied and database seeded')
  } catch (err) {
    console.error(
      '[e2e] Failed to migrate/seed the database. Ensure PostgreSQL is reachable ' +
        '(POSTGRES_HOST/PORT/USER/PASS/NAME) and `psql` is on PATH.',
    )
    throw err
  }
}
