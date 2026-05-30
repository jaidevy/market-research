# Generated manually to rebuild stale SQLite foreign keys.

from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("messaging", "0003_repair_run_foreign_keys"),
        ("runs", "0001_initial"),
        ("agents", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=r'''
PRAGMA foreign_keys=OFF;

DROP TABLE IF EXISTS "messaging_channelconversation_new";
CREATE TABLE "messaging_channelconversation_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "created_at" datetime NOT NULL,
    "updated_at" datetime NOT NULL,
    "external_user_id" varchar(120) NOT NULL,
    "active_run_id" bigint NULL REFERENCES "runs_unifiedrun" ("id") DEFERRABLE INITIALLY DEFERRED,
    "target_agent_id" bigint NOT NULL REFERENCES "agents_agent" ("id") DEFERRABLE INITIALLY DEFERRED,
    "external_channel" varchar(24) NOT NULL
);
INSERT INTO "messaging_channelconversation_new" (
    "id", "created_at", "updated_at", "external_user_id", "active_run_id", "target_agent_id", "external_channel"
)
SELECT
    old."id", old."created_at", old."updated_at", old."external_user_id",
    CASE WHEN run."id" IS NULL THEN NULL ELSE old."active_run_id" END,
    old."target_agent_id", old."external_channel"
FROM "messaging_channelconversation" old
INNER JOIN "agents_agent" agent ON agent."id" = old."target_agent_id"
LEFT JOIN "runs_unifiedrun" run ON run."id" = old."active_run_id";
DROP TABLE "messaging_channelconversation";
ALTER TABLE "messaging_channelconversation_new" RENAME TO "messaging_channelconversation";
CREATE INDEX "messaging_channelconversation_target_agent_id_a9914aed" ON "messaging_channelconversation" ("target_agent_id");
CREATE INDEX "messaging_channelconversation_active_run_id_499e4c42" ON "messaging_channelconversation" ("active_run_id");

DROP TABLE IF EXISTS "messaging_interagentmessage_new";
CREATE TABLE "messaging_interagentmessage_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "created_at" datetime NOT NULL,
    "updated_at" datetime NOT NULL,
    "message_id" varchar(120) NOT NULL UNIQUE,
    "channel" varchar(40) NOT NULL,
    "status" varchar(24) NOT NULL,
    "payload" text NOT NULL,
    "retry_count" integer NOT NULL,
    "from_agent_id" bigint NULL REFERENCES "agents_agent" ("id") DEFERRABLE INITIALLY DEFERRED,
    "run_id" bigint NOT NULL REFERENCES "runs_unifiedrun" ("id") DEFERRABLE INITIALLY DEFERRED,
    "to_agent_id" bigint NULL REFERENCES "agents_agent" ("id") DEFERRABLE INITIALLY DEFERRED
);
INSERT INTO "messaging_interagentmessage_new" (
    "id", "created_at", "updated_at", "message_id", "channel", "status", "payload", "retry_count",
    "from_agent_id", "run_id", "to_agent_id"
)
SELECT
    old."id", old."created_at", old."updated_at", old."message_id", old."channel", old."status", old."payload", old."retry_count",
    CASE WHEN from_agent."id" IS NULL THEN NULL ELSE old."from_agent_id" END,
    old."run_id",
    CASE WHEN to_agent."id" IS NULL THEN NULL ELSE old."to_agent_id" END
FROM "messaging_interagentmessage" old
INNER JOIN "runs_unifiedrun" run ON run."id" = old."run_id"
LEFT JOIN "agents_agent" from_agent ON from_agent."id" = old."from_agent_id"
LEFT JOIN "agents_agent" to_agent ON to_agent."id" = old."to_agent_id";
DROP TABLE "messaging_interagentmessage";
ALTER TABLE "messaging_interagentmessage_new" RENAME TO "messaging_interagentmessage";
CREATE INDEX "messaging_interagentmessage_to_agent_id_f1377ac1" ON "messaging_interagentmessage" ("to_agent_id");
CREATE INDEX "messaging_interagentmessage_run_id_328e5ed6" ON "messaging_interagentmessage" ("run_id");
CREATE INDEX "messaging_interagentmessage_from_agent_id_cd4055c3" ON "messaging_interagentmessage" ("from_agent_id");

DROP TABLE IF EXISTS "messaging_approvalticket_new";
CREATE TABLE "messaging_approvalticket_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "created_at" datetime NOT NULL,
    "updated_at" datetime NOT NULL,
    "ticket_key" varchar(120) NOT NULL UNIQUE,
    "status" varchar(24) NOT NULL,
    "summary" text NOT NULL,
    "reviewer" varchar(120) NOT NULL,
    "comment" text NOT NULL,
    "decided_at" datetime NULL,
    "requested_by_id" bigint NULL REFERENCES "agents_agent" ("id") DEFERRABLE INITIALLY DEFERRED,
    "run_id" bigint NOT NULL REFERENCES "runs_unifiedrun" ("id") DEFERRABLE INITIALLY DEFERRED
);
INSERT INTO "messaging_approvalticket_new" (
    "id", "created_at", "updated_at", "ticket_key", "status", "summary", "reviewer", "comment",
    "decided_at", "requested_by_id", "run_id"
)
SELECT
    old."id", old."created_at", old."updated_at", old."ticket_key", old."status", old."summary", old."reviewer", old."comment",
    old."decided_at",
    CASE WHEN agent."id" IS NULL THEN NULL ELSE old."requested_by_id" END,
    old."run_id"
FROM "messaging_approvalticket" old
INNER JOIN "runs_unifiedrun" run ON run."id" = old."run_id"
LEFT JOIN "agents_agent" agent ON agent."id" = old."requested_by_id";
DROP TABLE "messaging_approvalticket";
ALTER TABLE "messaging_approvalticket_new" RENAME TO "messaging_approvalticket";
CREATE INDEX "messaging_approvalticket_run_id_7551eee8" ON "messaging_approvalticket" ("run_id");
CREATE INDEX "messaging_approvalticket_requested_by_id_b611b306" ON "messaging_approvalticket" ("requested_by_id");

PRAGMA foreign_keys=ON;
''',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
