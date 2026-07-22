-- ACME Project Tracker — database schema
--
-- Single source of truth for the database structure. Applied by
-- migration-service/function.py, which reads this file and executes it.
-- It is also directly runnable for inspection or manual setup:
--
--     psql -h localhost -U test -d test -f schema.sql
--
-- Every statement is idempotent, so applying it repeatedly is safe. That
-- matters because the migration Lambda may be invoked after every deploy.

-- gen_random_uuid() for primary keys.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Lets one GiST index mix a uuid column with a daterange, which is what makes
-- the over-allocation query fast rather than a full scan.
CREATE EXTENSION IF NOT EXISTS "btree_gist";


-- ---------------------------------------------------------------------------
-- Organisation
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS departments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          text NOT NULL UNIQUE,
    full_name      text NOT NULL,
    password_hash  text NOT NULL,
    role           text NOT NULL DEFAULT 'VIEWER'
                   CHECK (role IN ('VIEWER','CONTRIBUTOR','MANAGER','ADMIN')),
    department_id  uuid REFERENCES departments(id) ON DELETE SET NULL,
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------------
-- Projects
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS teams (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text NOT NULL UNIQUE,
    description    text,
    department_id  uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    manager_id     uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projects (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code            text NOT NULL UNIQUE,
    name            text NOT NULL,
    description     text,
    department_id   uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    manager_id      uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status          text NOT NULL DEFAULT 'PLANNING'
                    CHECK (status IN ('PLANNING','ACTIVE','ON_HOLD','COMPLETED','CANCELLED')),
    priority        text NOT NULL DEFAULT 'MEDIUM'
                    CHECK (priority IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    start_date      date NOT NULL,
    planned_end     date NOT NULL,
    actual_end      date,
    planned_budget  numeric(14,2) NOT NULL DEFAULT 0 CHECK (planned_budget >= 0),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT projects_dates_ordered CHECK (planned_end >= start_date)
);


-- ---------------------------------------------------------------------------
-- Deliverables
--
-- `weight` exists so completion can be weighted rather than a naive count.
-- Ten trivial tasks and one large one are not 50% done when five trivial ones
-- finish, and the at-risk calculation depends on that distinction.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS deliverables (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id          uuid REFERENCES users(id) ON DELETE SET NULL,
    name              text NOT NULL,
    description       text,
    status            text NOT NULL DEFAULT 'NOT_STARTED'
                      CHECK (status IN ('NOT_STARTED','IN_PROGRESS','BLOCKED','COMPLETED','CANCELLED')),
    percent_complete  integer NOT NULL DEFAULT 0
                      CHECK (percent_complete BETWEEN 0 AND 100),
    weight            numeric(6,2) NOT NULL DEFAULT 1 CHECK (weight > 0),
    due_date          date NOT NULL,
    completed_at      date,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- An edge table, not a parent_id column: a deliverable can block several others
-- and be blocked by several. The dependency chain is then a recursive CTE over
-- this table, which also yields the critical path.
CREATE TABLE IF NOT EXISTS deliverable_dependencies (
    predecessor_id  uuid NOT NULL REFERENCES deliverables(id) ON DELETE CASCADE,
    successor_id    uuid NOT NULL REFERENCES deliverables(id) ON DELETE CASCADE,
    dep_type        text NOT NULL DEFAULT 'FINISH_TO_START'
                    CHECK (dep_type IN ('FINISH_TO_START','START_TO_START','FINISH_TO_FINISH')),
    PRIMARY KEY (predecessor_id, successor_id),
    CONSTRAINT no_self_dependency CHECK (predecessor_id <> successor_id)
);


-- ---------------------------------------------------------------------------
-- Resource allocation
--
-- `period` is a daterange rather than two date columns. Over-allocation is then
-- an overlap query (`period && period`) instead of application-side interval
-- arithmetic, and the exclusion constraint below becomes possible if you later
-- want the database to reject conflicts outright rather than just report them.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS allocations (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id       uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role_on_project  text,
    allocation_pct   integer NOT NULL CHECK (allocation_pct BETWEEN 1 AND 100),
    period           daterange NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------------
-- Budget
--
-- Planned amounts and actual spend are separate tables so "consumed vs planned"
-- is a rollup rather than two numbers someone keeps in sync by hand.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS budget_items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    category        text NOT NULL,
    planned_amount  numeric(14,2) NOT NULL CHECK (planned_amount >= 0),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, category)
);

CREATE TABLE IF NOT EXISTS expenses (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_item_id  uuid NOT NULL REFERENCES budget_items(id) ON DELETE CASCADE,
    description     text,
    amount          numeric(14,2) NOT NULL CHECK (amount >= 0),
    incurred_on     date NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_teams_department  ON teams(department_id);
CREATE INDEX IF NOT EXISTS idx_teams_manager     ON teams(manager_id);
CREATE INDEX IF NOT EXISTS idx_teams_is_active   ON teams(is_active);

CREATE INDEX IF NOT EXISTS idx_projects_status      ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_department  ON projects(department_id);
CREATE INDEX IF NOT EXISTS idx_projects_manager     ON projects(manager_id);
CREATE INDEX IF NOT EXISTS idx_projects_planned_end ON projects(planned_end);

CREATE INDEX IF NOT EXISTS idx_deliverables_project ON deliverables(project_id);
CREATE INDEX IF NOT EXISTS idx_deliverables_owner   ON deliverables(owner_id);
CREATE INDEX IF NOT EXISTS idx_deliverables_due     ON deliverables(due_date);

CREATE INDEX IF NOT EXISTS idx_deps_successor       ON deliverable_dependencies(successor_id);

CREATE INDEX IF NOT EXISTS idx_allocations_project  ON allocations(project_id);
CREATE INDEX IF NOT EXISTS idx_expenses_budget_item ON expenses(budget_item_id);
CREATE INDEX IF NOT EXISTS idx_expenses_incurred_on ON expenses(incurred_on);

-- The overlap index. Answers "who is over-allocated in this window" without
-- scanning every allocation row.
CREATE INDEX IF NOT EXISTS idx_allocations_user_period
    ON allocations USING gist (user_id, period);


-- Added after the initial schema: audit trail for logins. Written as an
-- idempotent ALTER so an existing database picks it up on the next migration
-- run without a drop-and-recreate.
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at timestamptz;
