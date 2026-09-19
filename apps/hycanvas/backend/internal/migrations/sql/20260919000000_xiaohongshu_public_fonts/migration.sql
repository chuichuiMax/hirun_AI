CREATE TABLE IF NOT EXISTS "public_fonts" (
    id UUID PRIMARY KEY,
    zone TEXT NOT NULL,
    family TEXT NOT NULL,
    style TEXT NOT NULL,
    weight INTEGER NOT NULL,
    format TEXT NOT NULL,
    "mime_type" TEXT NOT NULL,
    "storage_key" TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    "byte_size" BIGINT NOT NULL,
    variable BOOLEAN NOT NULL DEFAULT false,
    "uploaded_by_id" UUID REFERENCES "users"(id) ON DELETE SET NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "public_fonts_zone_sha256_key" UNIQUE (zone, sha256),
    CONSTRAINT "public_fonts_weight_check" CHECK (weight BETWEEN 1 AND 1000),
    CONSTRAINT "public_fonts_size_check" CHECK ("byte_size" > 0)
);

CREATE INDEX IF NOT EXISTS "public_fonts_zone_family_idx"
    ON "public_fonts" (zone, lower(family), weight, lower(style));
