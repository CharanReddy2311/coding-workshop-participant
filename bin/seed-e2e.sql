-- Idempotent demo seed for E2E / CI.
--
-- Safe to run repeatedly: reference data and top-level entities use
-- ON CONFLICT DO NOTHING, and the child records (deliverables, dependencies,
-- allocations, budget) are guarded so they are only inserted once. Apply the
-- schema first (backend/migration-service/schema.sql), then this file:
--
--     psql -f backend/migration-service/schema.sql
--     psql -f bin/seed-e2e.sql
--
-- Logins: admin@acme.example / ChangeMe!123  (ADMIN)
--         every other user   / Passw0rd!
\set DEMO_HASH '''pbkdf2_sha256$260000$7bc53e38faeb98ac2cd328e2d9d2e83a$ed057994ff62aec221366ed77fd6484cacf8d20c96e7cddf79b4ddb2bfe76723'''

-- Reference data (migration-service seeds these in the cloud; here for CI).
INSERT INTO departments (name) VALUES ('Engineering'), ('Product'), ('Operations'), ('Finance')
ON CONFLICT (name) DO NOTHING;

-- Bootstrap admin (ChangeMe!123).
INSERT INTO users (email, full_name, password_hash, role) VALUES
  ('admin@acme.example', 'Platform Administrator',
   'pbkdf2_sha256$260000$f9b5ad24bb7de2dfacae4ba81af2bac6$a314b41505f9b6fab139907e5ec84de129cb2f8bf4c98e325da7f1b6ec798eee',
   'ADMIN')
ON CONFLICT (email) DO NOTHING;

-- Demo users across every role (Passw0rd!), plus one inactive account.
INSERT INTO users (email, full_name, password_hash, role, department_id, is_active) VALUES
  ('grace.hopper@acme.example',      'Grace Hopper',      :DEMO_HASH, 'ADMIN',       (SELECT id FROM departments WHERE name='Engineering'), true),
  ('ada.lovelace@acme.example',      'Ada Lovelace',      :DEMO_HASH, 'MANAGER',     (SELECT id FROM departments WHERE name='Engineering'), true),
  ('alan.turing@acme.example',       'Alan Turing',       :DEMO_HASH, 'MANAGER',     (SELECT id FROM departments WHERE name='Product'),     true),
  ('katherine.johnson@acme.example', 'Katherine Johnson', :DEMO_HASH, 'MANAGER',     (SELECT id FROM departments WHERE name='Finance'),     true),
  ('margaret.hamilton@acme.example', 'Margaret Hamilton', :DEMO_HASH, 'CONTRIBUTOR', (SELECT id FROM departments WHERE name='Engineering'), true),
  ('dennis.ritchie@acme.example',    'Dennis Ritchie',    :DEMO_HASH, 'CONTRIBUTOR', (SELECT id FROM departments WHERE name='Product'),     true),
  ('linus.torvalds@acme.example',    'Linus Torvalds',    :DEMO_HASH, 'CONTRIBUTOR', (SELECT id FROM departments WHERE name='Operations'),  true),
  ('barbara.liskov@acme.example',    'Barbara Liskov',    :DEMO_HASH, 'VIEWER',      (SELECT id FROM departments WHERE name='Operations'),  true),
  ('katie.bouman@acme.example',      'Katie Bouman',      :DEMO_HASH, 'CONTRIBUTOR', (SELECT id FROM departments WHERE name='Engineering'), false)
ON CONFLICT (email) DO NOTHING;

INSERT INTO teams (name, description, department_id, manager_id, is_active) VALUES
  ('Platform Engineering', 'Core services and shared platform', (SELECT id FROM departments WHERE name='Engineering'), (SELECT id FROM users WHERE email='ada.lovelace@acme.example'),      true),
  ('Payments Squad',       'Billing and financial systems',     (SELECT id FROM departments WHERE name='Finance'),     (SELECT id FROM users WHERE email='katherine.johnson@acme.example'), true),
  ('Growth & Product',     'Customer-facing product surface',   (SELECT id FROM departments WHERE name='Product'),     (SELECT id FROM users WHERE email='alan.turing@acme.example'),       true)
ON CONFLICT (name) DO NOTHING;

INSERT INTO projects (code, name, description, department_id, manager_id, status, priority, start_date, planned_end, actual_end, planned_budget) VALUES
  ('PR01','Expense Tracker',    'Self-service expense capture and reporting', (SELECT id FROM departments WHERE name='Finance'),     (SELECT id FROM users WHERE email='katherine.johnson@acme.example'), 'ACTIVE',    'HIGH',     '2026-01-15','2026-09-30', NULL,         120000),
  ('PR02','Customer Portal',    'Unified self-service customer portal',       (SELECT id FROM departments WHERE name='Product'),     (SELECT id FROM users WHERE email='alan.turing@acme.example'),       'ACTIVE',    'CRITICAL', '2026-03-01','2026-06-30', NULL,         200000),
  ('PR03','Data Lakehouse',     'Medallion data platform for analytics',      (SELECT id FROM departments WHERE name='Engineering'), (SELECT id FROM users WHERE email='ada.lovelace@acme.example'),      'PLANNING',  'MEDIUM',   '2026-08-01','2027-02-28', NULL,         300000),
  ('PR04','Mobile App Revamp',  'Rebuild of the native mobile experience',    (SELECT id FROM departments WHERE name='Product'),     (SELECT id FROM users WHERE email='alan.turing@acme.example'),       'ON_HOLD',   'LOW',      '2026-02-01','2026-12-31', NULL,         80000),
  ('PR05','Payroll Migration',  'Migrate payroll to the new finance stack',   (SELECT id FROM departments WHERE name='Finance'),     (SELECT id FROM users WHERE email='katherine.johnson@acme.example'), 'COMPLETED', 'HIGH',     '2025-09-01','2026-03-31', '2026-03-20', 150000),
  ('PR06','Legacy Decommission','Retire the legacy on-prem billing system',   (SELECT id FROM departments WHERE name='Operations'),  (SELECT id FROM users WHERE email='alan.turing@acme.example'),       'CANCELLED', 'MEDIUM',   '2026-01-01','2026-05-01', '2026-04-15', 50000)
ON CONFLICT (code) DO NOTHING;

-- Child records: only seeded once (guarded on an empty deliverables table).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM deliverables) THEN
    INSERT INTO deliverables (project_id, owner_id, name, description, status, percent_complete, weight, due_date, completed_at) VALUES
      ((SELECT id FROM projects WHERE code='PR01'), (SELECT id FROM users WHERE email='margaret.hamilton@acme.example'), 'Requirements & Design', 'Scope, wireframes, and data model', 'COMPLETED',   100, 2, '2026-02-28', '2026-02-25'),
      ((SELECT id FROM projects WHERE code='PR01'), (SELECT id FROM users WHERE email='dennis.ritchie@acme.example'),    'API Backend',           'CRUD services and validation',     'IN_PROGRESS',  60, 3, '2026-06-30', NULL),
      ((SELECT id FROM projects WHERE code='PR01'), (SELECT id FROM users WHERE email='margaret.hamilton@acme.example'), 'Frontend UI',           'React screens and dashboards',     'IN_PROGRESS',  40, 3, '2026-07-31', NULL),
      ((SELECT id FROM projects WHERE code='PR01'), (SELECT id FROM users WHERE email='katie.bouman@acme.example'),      'UAT & Launch',          'User acceptance and go-live',      'NOT_STARTED',   0, 2, '2026-09-15', NULL),
      ((SELECT id FROM projects WHERE code='PR02'), (SELECT id FROM users WHERE email='dennis.ritchie@acme.example'),    'Portal MVP',            'Minimum viable portal',            'BLOCKED',      30, 3, '2026-06-15', NULL),
      ((SELECT id FROM projects WHERE code='PR02'), (SELECT id FROM users WHERE email='linus.torvalds@acme.example'),    'Auth Integration',      'SSO and session handling',         'IN_PROGRESS',  50, 2, '2026-06-30', NULL),
      ((SELECT id FROM projects WHERE code='PR04'), (SELECT id FROM users WHERE email='margaret.hamilton@acme.example'), 'Design Spike',          'Explore new navigation model',     'COMPLETED',   100, 1, '2026-03-31', '2026-03-28'),
      ((SELECT id FROM projects WHERE code='PR04'), NULL,                                                                 'Prototype',             'Clickable prototype',              'CANCELLED',     0, 1, '2026-05-31', NULL),
      ((SELECT id FROM projects WHERE code='PR05'), (SELECT id FROM users WHERE email='linus.torvalds@acme.example'),    'Data Migration',        'Move payroll records',             'COMPLETED',   100, 3, '2026-02-28', '2026-02-20'),
      ((SELECT id FROM projects WHERE code='PR05'), (SELECT id FROM users WHERE email='katherine.johnson@acme.example'), 'Cutover',               'Switch to new system',             'COMPLETED',   100, 2, '2026-03-15', '2026-03-18');

    INSERT INTO deliverable_dependencies (predecessor_id, successor_id, dep_type) VALUES
      ((SELECT id FROM deliverables WHERE name='Requirements & Design' AND project_id=(SELECT id FROM projects WHERE code='PR01')),
       (SELECT id FROM deliverables WHERE name='API Backend'           AND project_id=(SELECT id FROM projects WHERE code='PR01')), 'FINISH_TO_START'),
      ((SELECT id FROM deliverables WHERE name='API Backend'           AND project_id=(SELECT id FROM projects WHERE code='PR01')),
       (SELECT id FROM deliverables WHERE name='Frontend UI'           AND project_id=(SELECT id FROM projects WHERE code='PR01')), 'FINISH_TO_START'),
      ((SELECT id FROM deliverables WHERE name='Frontend UI'           AND project_id=(SELECT id FROM projects WHERE code='PR01')),
       (SELECT id FROM deliverables WHERE name='UAT & Launch'          AND project_id=(SELECT id FROM projects WHERE code='PR01')), 'FINISH_TO_START'),
      ((SELECT id FROM deliverables WHERE name='Auth Integration'      AND project_id=(SELECT id FROM projects WHERE code='PR02')),
       (SELECT id FROM deliverables WHERE name='Portal MVP'            AND project_id=(SELECT id FROM projects WHERE code='PR02')), 'FINISH_TO_START');

    -- Margaret & Dennis land at exactly 100%; Katherine is intentionally over
    -- (130%) so the dashboard over-allocation alert has something to show.
    INSERT INTO allocations (user_id, project_id, role_on_project, allocation_pct, period) VALUES
      ((SELECT id FROM users WHERE email='margaret.hamilton@acme.example'), (SELECT id FROM projects WHERE code='PR01'), 'Frontend Lead',  60, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='margaret.hamilton@acme.example'), (SELECT id FROM projects WHERE code='PR04'), 'Design',         40, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='dennis.ritchie@acme.example'),    (SELECT id FROM projects WHERE code='PR01'), 'Backend Dev',    50, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='dennis.ritchie@acme.example'),    (SELECT id FROM projects WHERE code='PR02'), 'Backend Dev',    50, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='linus.torvalds@acme.example'),    (SELECT id FROM projects WHERE code='PR02'), 'Platform',       40, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='katie.bouman@acme.example'),      (SELECT id FROM projects WHERE code='PR01'), 'QA',             30, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='ada.lovelace@acme.example'),      (SELECT id FROM projects WHERE code='PR03'), 'Architect',      25, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='alan.turing@acme.example'),       (SELECT id FROM projects WHERE code='PR02'), 'Product Owner',  30, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='katherine.johnson@acme.example'), (SELECT id FROM projects WHERE code='PR01'), 'Sponsor',        70, daterange('2026-06-01','2026-12-31','[]')),
      ((SELECT id FROM users WHERE email='katherine.johnson@acme.example'), (SELECT id FROM projects WHERE code='PR05'), 'Sponsor',        60, daterange('2026-06-01','2026-12-31','[]'));

    INSERT INTO budget_items (project_id, category, planned_amount) VALUES
      ((SELECT id FROM projects WHERE code='PR01'), 'Labor',       70000),
      ((SELECT id FROM projects WHERE code='PR01'), 'Cloud',       25000),
      ((SELECT id FROM projects WHERE code='PR01'), 'Licenses',    15000),
      ((SELECT id FROM projects WHERE code='PR02'), 'Labor',      120000),
      ((SELECT id FROM projects WHERE code='PR02'), 'Vendor',      60000),
      ((SELECT id FROM projects WHERE code='PR05'), 'Labor',       90000),
      ((SELECT id FROM projects WHERE code='PR05'), 'Contractors', 40000);

    -- PR02 deliberately over budget (210k of 200k) to light up the widget.
    INSERT INTO expenses (budget_item_id, description, amount, incurred_on) VALUES
      ((SELECT id FROM budget_items WHERE category='Labor'       AND project_id=(SELECT id FROM projects WHERE code='PR01')), 'Q1 engineering', 40000, '2026-03-10'),
      ((SELECT id FROM budget_items WHERE category='Labor'       AND project_id=(SELECT id FROM projects WHERE code='PR01')), 'Q2 engineering', 15000, '2026-05-12'),
      ((SELECT id FROM budget_items WHERE category='Cloud'       AND project_id=(SELECT id FROM projects WHERE code='PR01')), 'AWS usage',      12000, '2026-04-01'),
      ((SELECT id FROM budget_items WHERE category='Licenses'    AND project_id=(SELECT id FROM projects WHERE code='PR01')), 'Tooling',         8000, '2026-02-20'),
      ((SELECT id FROM budget_items WHERE category='Labor'       AND project_id=(SELECT id FROM projects WHERE code='PR02')), 'Build team',    130000, '2026-05-01'),
      ((SELECT id FROM budget_items WHERE category='Vendor'      AND project_id=(SELECT id FROM projects WHERE code='PR02')), 'Design agency',  80000, '2026-06-10'),
      ((SELECT id FROM budget_items WHERE category='Labor'       AND project_id=(SELECT id FROM projects WHERE code='PR05')), 'Migration team', 88000, '2026-01-15'),
      ((SELECT id FROM budget_items WHERE category='Contractors' AND project_id=(SELECT id FROM projects WHERE code='PR05')), 'Specialists',    39000, '2026-02-10');
  END IF;
END $$;
