# Rules: PostgreSQL + Liquibase

**Profile Key:** `rules.postgres-liquibase`  
**Stack:** PostgreSQL + Liquibase (4.x+)  
**Type:** Database Migration Governance  
**Maturity:** Production  
**Scope:** Schema migrations, data migrations, rollback safety
**Addon class (binding):** required addon

---

## Profile Activation

**This profile is activated when:**
- Repository contains `db/changelog.xml` or `db/changelog.yaml`, OR
- Repository contains `liquibase.properties`, OR
- Explicitly requested via `SESSION_STATE.Profile=rules.postgres-liquibase`

**Applies to:**
- All changes executed via Liquibase: schema (DDL), data (DML), permissions, extensions, functions/procedures, indexes, constraints
- All environments: dev → staging → prod
- All PRs that touch `db/`, Liquibase changelogs, or migration SQL

**Non-goals:**
- This profile does not prescribe application-level ORM practices

---

## Required Repository Declarations (BINDING)

The target repository MUST declare the following in a machine-readable location (e.g., `db/config.yaml`, CI config, or README):

### PostgreSQL Version (REQUIRED)

**Declaration:**
```yaml
# db/config.yaml or .github/db-config.yaml
DB_TARGET_PG_MAJOR: 15  # Or 14, 13, etc.
DB_MIN_SUPPORTED_PG_MAJOR: 13  # Optional: minimum supported version
```

**OR in liquibase.properties:**
```properties
# Target PostgreSQL major version for safety rule evaluation
db.target.pg.major=15
db.min.supported.pg.major=13
```

**Policy:**
- If `DB_TARGET_PG_MAJOR` is not declared → **BLOCKED-MISSING-DB-VERSION**
- Safety rules (e.g., "PG <11 table rewrite") are evaluated against declared version
- Migrations targeting version ranges must document compatibility explicitly

**Rationale:** Prevents ambiguity in version-dependent safety rules. "Any version" makes safety rules non-auditable.

---

### Changelog Format (REQUIRED)

**Declaration:**
```yaml
# db/config.yaml
LIQUIBASE_FORMAT: XML  # Or: YAML, HYBRID
```

**Policy:**
- Repository MUST choose ONE format: `XML`, `YAML`, or `HYBRID`
- If `HYBRID`: Must define which changesets use which format (e.g., "XML for schema, YAML for data")
- CI MUST fail if multiple root changelogs exist without `HYBRID` declaration
- Format drift (mixing without policy) → **BLOCKED-FORMAT-UNDEFINED**

**Rationale:** Prevents uncontrolled format drift. Teams must make explicit choice.

---

## Integration with Governance Phases

**Note:** This section maps to the governance workflow defined in `master.md`. If your project does not use this workflow, treat this section as optional guidance.

### Phase 1.5: Business Rules Discovery

When this profile is active, the following DB-specific business rules are extracted:
- Data consistency constraints (from existing migrations)
- Schema invariants (NOT NULL, UNIQUE, CHECK constraints)
- Enum definitions and their usage patterns
- Critical table identification (based on constraints/indexes)
- Foreign key relationships and referential integrity rules

### Phase 2: Repository Discovery

**Profile detection triggers:**
1. Scan for `db/changelog.xml` or `db/changelog.yaml`
2. Scan for `liquibase.properties`
3. Scan for changesets in `db/changesets/`
4. Verify Liquibase version pinning (Docker tag, lockfile, or wrapper script)
5. Verify `DB_TARGET_PG_MAJOR` declaration

**Discovery artifacts:**
- Liquibase version in use
- Database target (PostgreSQL major version)
- Changelog format (XML/YAML/HYBRID)
- Existing changeset inventory (IDs, authors, rollback strategies)
- Risky patterns detected (runOnChange, runAlways, validCheckSum: ANY)

**Blockers at this phase:**
- Missing `DB_TARGET_PG_MAJOR` → **BLOCKED-MISSING-DB-VERSION**
- Missing format declaration → **BLOCKED-FORMAT-UNDEFINED**

### Phase 5.3: Implementation Quality Gate

Before merging code that touches migrations:
1. Run `liquibase validate` → Must pass
2. Generate `updateSQL` plan → Must complete without error
3. Check against safety rules (locking, backfills, constraints) for declared PG version
4. Verify rollback strategy documented
5. Verify PR template completed (risk, backout, compatibility)
6. Verify BLOCKED states resolved (if any)

---

## Definitions

- **Migration / change**: A Liquibase changeset
- **Forward-only**: A change that cannot be safely rolled back in prod
- **Online migration**: A migration designed to avoid long locks and downtime
- **Release readiness**: A required CI gate; failing means **no merge** to `main`
- **N-1 compatibility**: DB and app can be deployed in any order (DB-first or app-first)

---

## Design Principles

1. **Fail-closed**: Ambiguity or missing metadata fails CI and blocks merge
2. **Deterministic**: Given the same repo state and pinned tool versions, generated SQL plans are stable
3. **Operationally safe by default**: Avoid heavy locks, table rewrites, and unbounded backfills
4. **Auditability**: Each migration documents rationale, risk, and rollback/backout strategy
5. **Compatibility**: Migrations must support at least **N-1 deploy order** (app and DB may roll out separately)
6. **Version-aware**: Safety rules are evaluated against declared PostgreSQL version

---

## Repository Conventions

### Directory layout (recommended)

```
db/
├── config.yaml                # REQUIRED: DB_TARGET_PG_MAJOR, LIQUIBASE_FORMAT
├── changelog.xml              # Root changelog (if FORMAT=XML)
├── changelog.yaml             # Root changelog (if FORMAT=YAML)
├── changesets/                # Individual changeset files
│   ├── 202602061215_AI-123_add_policy_table.xml
│   ├── 202602061216_AI-124_add_email_index.xml
│   └── ...
└── sql/                       # Optional: Large SQL blocks
    └── ...
```

### Liquibase version pinning (required)

- Liquibase MUST be pinned (Docker image tag, wrapper script, or lockfile)
- CI MUST use the pinned version
- Local dev MUST be able to reproduce with the same version

**Example: Docker**
```dockerfile
FROM liquibase/liquibase:4.25.1
```

**Example: liquibase.properties**
```properties
liquibase.version=4.25.1
```

### Environment config (required)

- All env-specific DB credentials and URLs are provided **only** via env vars / secret stores
- **No secrets in repo**
- **No inline passwords in changelogs**

**Example:**
```bash
LIQUIBASE_URL=jdbc:postgresql://localhost:5432/mydb
LIQUIBASE_USERNAME=myuser
LIQUIBASE_PASSWORD=<from secret store>
```

---

## Changeset Standards (Required)

### IDs and author (required)

- `id` MUST be globally unique and stable
- `author` MUST be an org identifier (e.g., username/team), not a personal email

**Recommended ID format:**
```
YYYYMMDDHHMM_<ticket>_<short_slug>
```

**Examples:**
- `202602061215_AI-123_add_policy_table`
- `202602061320_AI-124_backfill_user_emails`

### One intent per changeset (required)

A changeset should do exactly one logical thing:
- Add a column
- Add an index
- Add a constraint
- Data backfill step
- etc.

**Why:** Easier to review, rollback, and troubleshoot

### Comments (required)

Each changeset MUST contain a comment with the following structured information:

**Required fields:**
- **What:** What changes (table/column/index name)
- **Why:** Business/technical rationale
- **Risk:** Lock impact, performance impact, data risk
- **Rollback:** How to undo (or why forward-only)
- **Compatibility:** App version expectations

**Example:**
```xml
<changeSet id="202602061215_AI-123_add_user_email_idx" author="ben">
  <comment>
    What: Add index on users.email for faster lookups
    Why: Search by email is slow (>500ms on prod, 50M rows)
    Risk: Low (CONCURRENTLY, no table lock, ~2min execution on PG15)
    Rollback: DROP INDEX CONCURRENTLY idx_users_email
    Compatibility: App-first or DB-first (index is optional optimization)
  </comment>
  ...
</changeSet>
```

### Forbidden Liquibase features (default policy)

The following are **forbidden** unless explicitly approved (see Approvals section):
- `runOnChange: true`
- `runAlways: true`
- `validCheckSum: ANY` (except in incident response with explicit approval)

**Rationale:** These weaken auditability and determinism

---

## PostgreSQL Safety Rules (Version-Aware)

**Safety rules are evaluated against `DB_TARGET_PG_MAJOR`.**

### Locking & table rewrites

**Avoid operations that rewrite whole tables or take long exclusive locks.**

**High risk / must be reviewed as "online migration":**

**PostgreSQL < 11:**
- Adding a column with a non-null default **REWRITES TABLE** → Use two-step pattern

**PostgreSQL 11+:**
- Adding a column with a non-null default is safe (no rewrite) IF default is constant
- Volatile defaults still rewrite table

**All versions:**
- `ALTER TYPE ...` / enum changes without safe ordering strategy
- `ALTER TABLE ... SET NOT NULL` on large tables without prior validation
- `ADD CONSTRAINT` without `NOT VALID` (when applicable) on large tables
- Any `UPDATE`/`DELETE` without a bounded predicate
- Adding columns to partitioned tables (may lock parent)

**Example version-aware policy:**
```xml
<changeSet id="..." author="...">
  <comment>
    What: Add users.status column with default 'active'
    PG Version: Target PG15 (no rewrite), Min PG13 (safe)
    Risk: Low on PG11+ (instant default), High on PG <11 (table rewrite)
    Policy: If PG <11 detected in prod → use two-step pattern
  </comment>
  <addColumn tableName="users">
    <column name="status" type="varchar(20)" defaultValue="active">
      <constraints nullable="false"/>
    </column>
  </addColumn>
</changeSet>
```

### Index creation

- Use `CREATE INDEX CONCURRENTLY` for large tables (prod/staging), unless proven safe otherwise
- If using `CONCURRENTLY`, ensure Liquibase is configured to avoid running inside a transaction for that changeset
  - Liquibase: `runInTransaction: false` for that changeset
- Adding unique constraints on large datasets must be preceded by a dedup/validation plan

**Example:**
```xml
<changeSet id="..." author="..." runInTransaction="false">
  <sql>
    CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
  </sql>
  <rollback>
    DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
  </rollback>
</changeSet>
```

### Constraints

**Prefer:**
1. `ADD CONSTRAINT ... NOT VALID`
2. Then `VALIDATE CONSTRAINT` in a separate changeset

**Why:** This reduces blocking time

**Example:**
```sql
-- Step 1: Add constraint NOT VALID (minimal lock)
ALTER TABLE users ADD CONSTRAINT users_email_not_null 
  CHECK (email IS NOT NULL) NOT VALID;

-- Step 2: Validate constraint (separate changeset, reads all rows)
ALTER TABLE users VALIDATE CONSTRAINT users_email_not_null;
```

### Extensions

- Enabling extensions requires explicit listing and rationale
- Extensions must be treated as production dependencies (versioning and rollback considered)

---

## Data Migrations / Backfills (Required)

### No unbounded backfills in a single transaction

Large DML must be chunked.

**CRITICAL:** PostgreSQL PL/pgSQL `DO` blocks do NOT support transaction control (`COMMIT`/`ROLLBACK`).

**Recommended approaches (in order of preference):**

#### Option 1: External Script (RECOMMENDED)

Run backfill outside database in application code or dedicated worker:

```python
# backfill_user_status.py
import psycopg2
import time

conn = psycopg2.connect(...)
cursor = conn.cursor()

batch_size = 10000
total_updated = 0

while True:
    cursor.execute("""
        UPDATE users
        SET user_status = 'active'
        WHERE user_status IS NULL
          AND id IN (
            SELECT id FROM users 
            WHERE user_status IS NULL 
            LIMIT %s
          )
    """, (batch_size,))
    
    affected = cursor.rowcount
    conn.commit()  # Commit each batch
    
    if affected == 0:
        break
    
    total_updated += affected
    print(f"Updated {affected} rows (total: {total_updated})")
    time.sleep(0.1)  # Rate limit

print(f"Backfill complete. Total: {total_updated}")
```

**Liquibase changeset references script:**
```xml
<changeSet id="202602061219_AI-125_backfill_user_status" author="ben">
  <comment>
    What: Backfill user_status (NULL → 'active')
    How: Run scripts/backfill_user_status.py after migration
    Risk: Medium (external script, batched)
    Rollback: FORWARD-ONLY (data overwritten)
    Compatibility: App must handle NULL and 'active'
  </comment>
  <sql>
    -- Placeholder: Actual backfill via external script
    -- Run: python scripts/backfill_user_status.py
    SELECT 1; -- No-op in migration
  </sql>
  <rollback>
    <!-- FORWARD-ONLY -->
  </rollback>
</changeSet>
```

---

#### Option 2: PROCEDURE with CALL (PostgreSQL 11+)

For PostgreSQL 11+, use `PROCEDURE` with explicit transaction control:

```sql
CREATE OR REPLACE PROCEDURE backfill_user_status()
LANGUAGE plpgsql
AS $$
DECLARE
  batch_size INTEGER := 10000;
  affected INTEGER;
  total_updated INTEGER := 0;
BEGIN
  LOOP
    UPDATE users
    SET user_status = 'active'
    WHERE user_status IS NULL
      AND id IN (
        SELECT id FROM users 
        WHERE user_status IS NULL 
        LIMIT batch_size
      );
    
    GET DIAGNOSTICS affected = ROW_COUNT;
    EXIT WHEN affected = 0;
    
    total_updated := total_updated + affected;
    RAISE NOTICE 'Updated % rows (total: %)', affected, total_updated;
    
    COMMIT;  -- Transaction control in PROCEDURE
    PERFORM pg_sleep(0.1);
  END LOOP;
  
  RAISE NOTICE 'Backfill complete. Total: %', total_updated;
END;
$$;

-- Execute
CALL backfill_user_status();
```

**Liquibase changeset:**
```xml
<changeSet id="..." author="...">
  <comment>
    What: Backfill user_status via PROCEDURE (PG11+ only)
    Risk: Medium (batched, transaction control in procedure)
    Rollback: FORWARD-ONLY
    PG Version: Requires PG11+ for PROCEDURE with transaction control
  </comment>
  <sql>
    CREATE OR REPLACE PROCEDURE backfill_user_status() ...;
    CALL backfill_user_status();
    DROP PROCEDURE backfill_user_status();
  </sql>
</changeSet>
```

---

#### Option 3: Repeated Small Changesets (Less Elegant)

Create multiple changesets, each updating a bounded range:

```xml
<!-- Batch 1 -->
<changeSet id="202602061219_AI-125_backfill_batch1" author="ben">
  <sql>
    UPDATE users SET user_status = 'active' 
    WHERE user_status IS NULL AND id BETWEEN 1 AND 10000;
  </sql>
</changeSet>

<!-- Batch 2 -->
<changeSet id="202602061220_AI-125_backfill_batch2" author="ben">
  <sql>
    UPDATE users SET user_status = 'active' 
    WHERE user_status IS NULL AND id BETWEEN 10001 AND 20000;
  </sql>
</changeSet>

<!-- Etc. -->
```

**Pros:** Deterministic, trackable in Liquibase
**Cons:** Verbose, requires knowing row count upfront

---

### Two-phase pattern (recommended)

For changes requiring data backfill:
1. Add nullable column / new structure
2. Backfill in controlled steps (external script or procedure)
3. Add constraints / not-null after validation
4. Cleanup old column/structure in later release

### Idempotence & re-runs

Data migrations should be safe to re-run or designed to fail clearly without partial corruption

**Example:**
```sql
-- Idempotent: Only update if not already set
UPDATE users 
SET user_status = 'active' 
WHERE user_status IS NULL 
  AND created_at < '2026-01-01';
```

---

## Rollback / Backout Policy

### Default: Rollback required

Every changeset MUST provide one of:
- A valid Liquibase rollback block, OR
- A documented **backout strategy** if rollback is unsafe

**Example with rollback:**
```xml
<changeSet id="..." author="...">
  <addColumn tableName="users">
    <column name="email" type="varchar(255)"/>
  </addColumn>
  <rollback>
    <dropColumn tableName="users" columnName="email"/>
  </rollback>
</changeSet>
```

### Forward-only allowed (exception)

Forward-only changes are allowed only if:
- The changeset clearly states "FORWARD-ONLY" in comment
- Backout strategy is defined (e.g., feature flag, compatibility shim, restore procedure)
- Explicit approval is obtained (see Approvals section)

---

## Compatibility & Deployment (Required)

### N-1 compatibility

Migrations must support:
- DB updated before app (DB-first), and
- App updated before DB (app-first),

unless the change is explicitly "lockstep" and approved

**Example: Compatible pattern**
```
1. Add new column (nullable)        → Both old/new app work
2. Deploy app (dual-write)          → Writes to both columns
3. Backfill old data               → Data migrated
4. Deploy app (read from new)       → Reads from new column
5. Drop old column (later release) → Old column removed
```

### Dangerous lockstep changes (require approval)

**Examples:**
- Dropping columns/tables used by current app
- Renaming without compatibility views/synonyms
- Tightening constraints without validating existing data

---

## Observability & Verification (Required)

For risky changes, include:
- Pre-check queries (row counts, null checks, duplicates)
- Post-check queries (constraints valid, index present, expected invariants)

**Recommended:** Add a `verify.sql` artifact or embed verification steps in PR description

---

## CI Gates (Release Readiness) — Required

### Deterministic Environment (BINDING)

CI MUST set the following for deterministic plan generation:

```yaml
env:
  TZ: UTC
  LC_ALL: C
  LANG: C.UTF-8
```

**Liquibase logging:**
```bash
liquibase --log-level=WARNING updateSQL
```

**Rationale:** Prevents timezone/locale-related flakes in SQL plan outputs

---

### Mandatory checks for PRs touching migrations

1. **`liquibase validate`** must pass
2. **Deterministic plan:** `liquibase updateSQL` output must be generated in CI
   - Upload as artifact for review
   - Optional: Diff against previous plan for transparency
3. **If a Postgres service is available in CI:**
   - Apply migrations to a fresh DB (`liquibase update`)
   - Run smoke queries / invariants
4. **Structural policy lint** (REQUIRED - see below)

---

### Structural Policy Lint (Replaces grep)

**DO NOT use simple `grep` for policy validation.** Parse changelogs structurally.

**NOTE (BINDING):** The example linter below assumes `LIQUIBASE_FORMAT=XML` and a root changelog at `db/changelog.xml`.
For `LIQUIBASE_FORMAT=YAML` or `HYBRID`, provide an equivalent structural parser and enforce the same policy checks.

**Example Python linter (XML):**

```python
# lint_migrations.py
from lxml import etree
import sys

def lint_changelog(changelog_path):
    tree = etree.parse(changelog_path)
    root = tree.getroot()
    
    errors = []
    
    for changeset in root.findall('.//{*}changeSet'):
        cs_id = changeset.get('id')
        author = changeset.get('author')
        
        # Check 1: Forbidden attributes
        if changeset.get('runOnChange') == 'true':
            errors.append(f"{cs_id}: runOnChange=true is forbidden")
        
        if changeset.get('runAlways') == 'true':
            errors.append(f"{cs_id}: runAlways=true is forbidden")
        
        # Check 2: CONCURRENTLY requires runInTransaction=false
        sql = changeset.findtext('.//{*}sql', default='')
        if 'CONCURRENTLY' in sql.upper():
            if changeset.get('runInTransaction') != 'false':
                errors.append(f"{cs_id}: CONCURRENTLY without runInTransaction=false")
        
        # Check 3: Comment must include required fields
        comment = changeset.findtext('.//{*}comment', default='')
        required_fields = ['What:', 'Risk:', 'Rollback:', 'Compatibility:']
        for field in required_fields:
            if field not in comment:
                errors.append(f"{cs_id}: Missing '{field}' in comment")
        
        # Check 4: Rollback or FORWARD-ONLY
        rollback = changeset.find('.//{*}rollback')
        if rollback is None and 'FORWARD-ONLY' not in comment:
            errors.append(f"{cs_id}: No rollback and not marked FORWARD-ONLY")
    
    return errors

if __name__ == '__main__':
    errors = lint_changelog('db/changelog.xml')
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        sys.exit(1)
    else:
        print("✅ All checks passed")
```

**GitHub Actions integration:**
```yaml
- name: Structural Policy Lint
  run: python scripts/lint_migrations.py
```

---

### Tag builds (real releases)

For tag builds (`refs/tags/v*`):
- The versioned changelog section must contain at least one bullet
- Build artifacts must be reproducible

---

## Approvals & Review Process (Lead/Staff Standard)

### Required reviewers

At least one reviewer with DB ownership (Staff/Lead or on-call DBA role) for:
- Online migrations
- Forward-only changes
- Large backfills
- Any operation touching critical tables

### PR template requirements (must be present)

- **Risk level:** Low / Medium / High
- **Expected lock impact and mitigation**
- **Rollback/backout plan**
- **Verification steps** (pre/post queries)
- **Deployment order and compatibility statement**
- **PostgreSQL version target** (from `DB_TARGET_PG_MAJOR`)

---

## Operational Playbook (Required for High Risk)

For high-risk changes, attach:
- **Execution window recommendation** (e.g., "Run during low-traffic hours 2-4am UTC")
- **Monitoring plan** (locks, replication lag, error budget)
- **Abort conditions** (e.g., "Abort if lock held >30s")
- **Incident runbook reference** (pager, escalation)

---

## BLOCKED States (Database-Specific)

### BLOCKED-MISSING-DB-VERSION

**Trigger:** `DB_TARGET_PG_MAJOR` not declared in repository

**Resume pointer:** Phase 2 — Repository Discovery

**Required input:** Add `DB_TARGET_PG_MAJOR` declaration to `db/config.yaml` or equivalent

**Recovery steps:**
1. Determine target PostgreSQL major version(s)
2. Add to `db/config.yaml`: `DB_TARGET_PG_MAJOR: 15`
3. Re-run discovery

---

### BLOCKED-FORMAT-UNDEFINED

**Trigger:** Multiple changelog formats detected without `LIQUIBASE_FORMAT` declaration

**Resume pointer:** Phase 2 — Repository Discovery

**Required input:** Declare format choice in `db/config.yaml`

**Recovery steps:**
1. Choose format: XML, YAML, or HYBRID
2. Add to `db/config.yaml`: `LIQUIBASE_FORMAT: XML`
3. If HYBRID: Document which changesets use which format
4. Remove duplicate root changelogs if necessary

---

### BLOCKED-MIGRATION-UNSAFE

**Trigger:** Migration violates safety rules for declared PostgreSQL version

**Resume pointer:** Phase 5.3 — Implementation Quality Gate

**Required input:** 
- Revised migration with safe pattern, OR
- Explicit approval + operational playbook for risky migration

**Recovery steps:**
1. Identify violated rule (CI output shows which check failed)
2. Evaluate against `DB_TARGET_PG_MAJOR` (e.g., PG15 vs PG10)
3. Refactor migration OR get approval
4. If approved: Add operational playbook
5. Re-run CI gates

---

### BLOCKED-MIGRATION-NO-ROLLBACK

**Trigger:** Changeset has no rollback strategy and is not explicitly marked FORWARD-ONLY

**Resume pointer:** Phase 5.3 — Implementation Quality Gate

**Required input:** 
- Add rollback block to changeset, OR
- Document backout strategy + mark FORWARD-ONLY + get approval

**Recovery steps:**
1. Review if rollback is technically possible
2. If yes: Add `<rollback>` block
3. If no: Document why + backout plan + mark FORWARD-ONLY
4. Get Staff/Lead approval

---

### BLOCKED-MIGRATION-COMPATIBILITY

**Trigger:** Migration breaks N-1 compatibility without approval

**Resume pointer:** Phase 5.3 — Implementation Quality Gate

**Required input:** 
- Refactor to maintain compatibility, OR
- Explicit lockstep approval + deployment coordination plan

**Recovery steps:**
1. Identify breaking change
2. Refactor to multi-step compatible approach
3. Or: Get lockstep approval + document deployment order
4. Re-validate

---

## Common Patterns (Recommended)

### Safe constraint rollout

```sql
-- Step 1: Add constraint NOT VALID
ALTER TABLE users ADD CONSTRAINT users_email_not_null 
  CHECK (email IS NOT NULL) NOT VALID;

-- Step 2: Validate constraint (separate changeset)
ALTER TABLE users VALIDATE CONSTRAINT users_email_not_null;

-- Step 3: Enforce at column level (later release)
ALTER TABLE users ALTER COLUMN email SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_email_not_null;
```

### Safe column deprecation

```
1. Add new column (nullable)
2. Deploy app (dual-write to both columns)
3. Backfill old → new (external script)
4. Deploy app (read from new column)
5. Drop old column (later release, approved)
```

---

## Examples

### ✅ GOOD: Safe index creation (CONCURRENTLY)

```xml
<changeSet id="202602061215_AI-123_add_user_email_idx" author="ben" runInTransaction="false">
  <comment>
    What: Add index on users.email for faster lookups
    Why: Email search >500ms on 50M rows
    Risk: Low (CONCURRENTLY, no lock, ~2min on PG15)
    Rollback: DROP INDEX CONCURRENTLY idx_users_email
    Compatibility: App-first or DB-first (optional optimization)
    PG Version: Target PG15
  </comment>
  <sql>
    CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
  </sql>
  <rollback>
    DROP INDEX CONCURRENTLY IF EXISTS idx_users_email;
  </rollback>
</changeSet>
```

---

### ✅ GOOD: External backfill script (RECOMMENDED)

```xml
<changeSet id="202602061219_AI-125_backfill_user_status" author="ben">
  <comment>
    What: Backfill user_status (NULL → 'active') via external script
    How: scripts/backfill_user_status.py (batched, 10k rows/batch)
    Risk: Medium (external, long-running, but batched with rate limit)
    Rollback: FORWARD-ONLY (data overwritten, restore from backup if needed)
    Compatibility: App must handle NULL and 'active' during backfill
    Execution: Run script after migration deployment
    PG Version: Target PG15
  </comment>
  <sql>
    -- No-op: Backfill via external script
    -- Execute: python scripts/backfill_user_status.py
    SELECT 1;
  </sql>
  <rollback>
    <!-- FORWARD-ONLY: Cannot undo data changes -->
  </rollback>
</changeSet>
```

---

## Required Tooling & Commands

### Local Development

**Validate migrations:**
```bash
TZ=UTC LC_ALL=C liquibase --changeLogFile=db/changelog.xml validate
```

**Generate SQL plan (deterministic):**
```bash
TZ=UTC LC_ALL=C liquibase \
  --changeLogFile=db/changelog.xml \
  --log-level=WARNING \
  updateSQL
```

**Apply migrations:**
```bash
liquibase --changeLogFile=db/changelog.xml update
```

**Rollback last changeset:**
```bash
liquibase --changeLogFile=db/changelog.xml rollbackCount 1
```

---

### CI/CD Integration

```yaml
name: Liquibase Validate

on:
  pull_request:
    paths:
      - 'db/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    
    env:
      TZ: UTC
      LC_ALL: C
      LANG: C.UTF-8
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test
        options: >-
          --health-cmd pg_isready
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install lint deps
        run: python -m pip install --upgrade pip pyyaml

      - name: Verify DB Version Declaration
        run: |
          python - <<'PY'
          import sys, yaml
          from pathlib import Path
          p = Path("db/config.yaml")
          if not p.exists():
              print("ERROR: db/config.yaml missing")
              sys.exit(1)
          cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
          if "DB_TARGET_PG_MAJOR" not in cfg:
              print("ERROR: DB_TARGET_PG_MAJOR not declared")
              sys.exit(1)
          print("OK: DB_TARGET_PG_MAJOR =", cfg["DB_TARGET_PG_MAJOR"])
          PY

      
      - name: Liquibase Validate
        run: |
          liquibase --changeLogFile=db/changelog.xml \
            --url=jdbc:postgresql://localhost:5432/test \
            --username=postgres \
            --password=postgres \
            validate
      
      - name: Generate SQL Plan (Deterministic)
        run: |
          liquibase --changeLogFile=db/changelog.xml \
            --url=jdbc:postgresql://localhost:5432/test \
            --username=postgres \
            --password=postgres \
            --log-level=WARNING \
            updateSQL > migration-plan.sql
      
      - name: Upload SQL Plan
        uses: actions/upload-artifact@v4
        with:
          name: migration-plan
          path: migration-plan.sql
      
      - name: Apply Migrations (Test)
        run: |
          liquibase --changeLogFile=db/changelog.xml \
            --url=jdbc:postgresql://localhost:5432/test \
            --username=postgres \
            --password=postgres \
            update
      
      - name: Structural Policy Lint
        run: python scripts/lint_migrations.py
```

---

## Troubleshooting

### Migration fails with "Lock timeout"

**Cause:** Long-running transaction blocking migration

**Solution:**
1. Identify blocking queries:
   ```sql
   SELECT pid, usename, state, query 
   FROM pg_stat_activity 
   WHERE state = 'active';
   ```
2. Terminate blocker (if safe)
3. Retry migration

---

### "Constraint already exists" error

**Cause:** Partial migration applied

**Solution (INCIDENT-ONLY):**

**Preferred:** Use Liquibase's built-in sync commands:
```bash
# Mark changeset as executed without running
liquibase changelogSync

# Or mark specific changeset as executed
liquibase markNextChangesetRan
```

**Last resort (REQUIRES APPROVAL + INCIDENT TICKET):**

Manual insertion into `databasechangelog` is **DANGEROUS** and should only be done:
- During active incident response
- With explicit approval from Staff/Lead
- With documented incident ticket
- When Liquibase sync commands cannot be used

**If you must manually insert (with extreme caution):**
1. Get approval + create incident ticket
2. Calculate correct MD5 checksum
3. Verify `orderexecuted` sequence
4. Insert with full metadata
5. Document in incident report

**WARNING:** Incorrect MD5sum or orderexecuted will cause cascading failures. Use Liquibase's built-in commands whenever possible.

---

## Exceptions

Exceptions must be:
- **Explicit**: Clearly documented in changeset comment
- **Time-bounded**: Temporary deviation with removal plan
- **Documented**: In PR + `docs/exceptions/*.md`
- **Approved**: Staff/Lead sign-off

**Example:**
```xml
<changeSet id="..." author="..." validCheckSum="ANY">
  <comment>
    EXCEPTION: validCheckSum=ANY (INCIDENT-ONLY)
    Reason: Emergency hotfix #incident-123
    Approval: Staff @alice (2026-02-06)
    Removal plan: Issue #456 normalize changeset
    Expiry: 2026-02-20
  </comment>
  ...
</changeSet>
```

---

## References

### Official Documentation
- [Liquibase Best Practices](https://docs.liquibase.com/concepts/bestpractices.html)
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [PostgreSQL CREATE INDEX CONCURRENTLY](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY)
- [PostgreSQL Procedures (PG11+)](https://www.postgresql.org/docs/current/sql-createprocedure.html)

### Internal Standards
- See `master.md` for governance workflow (if applicable)
- See `rules.md` for code quality standards (if applicable)

### Related Profiles
- `rules.backend-java.md` — Application layer
- `rules.md` — Test and quality requirements

---

## Profile Compliance Statement

By merging a PR that touches DB migrations, approvers accept operational responsibility for:
- Migration safety for declared PostgreSQL version
- Plan validation (CI gates passed)
- Rollback/backout strategy review and documentation
- Change auditability and reproducibility
- Compatibility verification with existing application versions
- Resolution of all BLOCKED states

Approvers who merge migrations without meeting these criteria accept accountability for operational incidents resulting from the change.

---

**END OF RULESET**

---

## Shared Principal Governance Contracts (Binding)

This rulebook uses shared advisory governance contracts:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior:

- When this rulebook is active in execution/review phases, load these as advisory governance contracts.
- Record when loaded:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`
- If one of these shared rulebooks is unavailable, emit WARN + recovery, mark affected claims as
  `not-verified`, and continue conservatively.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

