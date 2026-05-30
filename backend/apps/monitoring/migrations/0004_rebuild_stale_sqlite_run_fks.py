# Generated manually to rebuild stale SQLite foreign keys.

from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("monitoring", "0003_repair_run_foreign_keys"),
        ("runs", "0001_initial"),
        ("agents", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=r'''
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS "monitoring_runtimeevent_new";
CREATE TABLE "monitoring_runtimeevent_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "created_at" datetime NOT NULL,
    "updated_at" datetime NOT NULL,
    "level" varchar(16) NOT NULL,
    "event_type" varchar(48) NOT NULL,
    "message" text NOT NULL,
    "context" text NOT NULL,
    "run_id" bigint NOT NULL REFERENCES "runs_unifiedrun" ("id") DEFERRABLE INITIALLY DEFERRED
);
INSERT INTO "monitoring_runtimeevent_new" (
    "id", "created_at", "updated_at", "level", "event_type", "message", "context", "run_id"
)
SELECT old."id", old."created_at", old."updated_at", old."level", old."event_type", old."message", old."context", old."run_id"
FROM "monitoring_runtimeevent" old
INNER JOIN "runs_unifiedrun" run ON run."id" = old."run_id";
DROP TABLE "monitoring_runtimeevent";
ALTER TABLE "monitoring_runtimeevent_new" RENAME TO "monitoring_runtimeevent";
CREATE INDEX "monitoring_runtimeevent_run_id_3fb61e3d" ON "monitoring_runtimeevent" ("run_id");

DROP TABLE IF EXISTS "monitoring_tokencostledger_new";
CREATE TABLE "monitoring_tokencostledger_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "created_at" datetime NOT NULL,
    "updated_at" datetime NOT NULL,
    "step_key" varchar(80) NOT NULL,
    "input_tokens" integer NOT NULL,
    "output_tokens" integer NOT NULL,
    "estimated_cost_usd" decimal NOT NULL,
    "is_estimated" bool NOT NULL,
    "agent_id" bigint NULL REFERENCES "agents_agent" ("id") DEFERRABLE INITIALLY DEFERRED,
    "run_id" bigint NOT NULL REFERENCES "runs_unifiedrun" ("id") DEFERRABLE INITIALLY DEFERRED,
    "model_name" varchar(80) NOT NULL
);
INSERT INTO "monitoring_tokencostledger_new" (
    "id", "created_at", "updated_at", "step_key", "input_tokens", "output_tokens",
    "estimated_cost_usd", "is_estimated", "agent_id", "run_id", "model_name"
)
SELECT
    old."id", old."created_at", old."updated_at", old."step_key", old."input_tokens", old."output_tokens",
    old."estimated_cost_usd", old."is_estimated",
    CASE WHEN agent."id" IS NULL THEN NULL ELSE old."agent_id" END,
    old."run_id", old."model_name"
FROM "monitoring_tokencostledger" old
INNER JOIN "runs_unifiedrun" run ON run."id" = old."run_id"
LEFT JOIN "agents_agent" agent ON agent."id" = old."agent_id";
DROP TABLE "monitoring_tokencostledger";
ALTER TABLE "monitoring_tokencostledger_new" RENAME TO "monitoring_tokencostledger";
CREATE INDEX "monitoring_tokencostledger_run_id_e2638ed1" ON "monitoring_tokencostledger" ("run_id");
CREATE INDEX "monitoring_tokencostledger_agent_id_74f183ef" ON "monitoring_tokencostledger" ("agent_id");

PRAGMA foreign_keys=ON;
''',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
