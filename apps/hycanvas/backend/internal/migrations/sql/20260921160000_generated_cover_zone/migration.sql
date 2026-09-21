-- Content-production instantiations are stored as designs but must not appear
-- in the Xiaohongshu template library. Keep a distinct zone marker so home
-- listings can skip them without reading snapshot blobs.
ALTER TABLE "designs" DROP CONSTRAINT IF EXISTS "designs_template_zone_check";

ALTER TABLE "designs"
    ADD CONSTRAINT "designs_template_zone_check"
    CHECK ("template_zone" IS NULL OR "template_zone" IN ('xiaohongshu', 'contentswarm-cover'));
