-- A user may hide a built-in template without deleting the shared seed. The
-- templates service reads this table for every catalog request, so it must be
-- present even when no seed has been hidden yet.
CREATE TABLE "hidden_seed_templates" (
    "template_id" TEXT NOT NULL,
    "hidden_by" UUID NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT "hidden_seed_templates_pkey" PRIMARY KEY ("template_id"),
    CONSTRAINT "hidden_seed_templates_hidden_by_fkey"
        FOREIGN KEY ("hidden_by") REFERENCES "users"("id")
        ON DELETE CASCADE ON UPDATE CASCADE
);
