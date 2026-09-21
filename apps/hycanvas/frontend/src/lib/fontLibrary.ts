import type { PublicFontFace } from "@hc/sdk";
import { fonts } from "./fontProvider";
import { oc } from "./sdk";

let loading: Promise<PublicFontFace[]> | null = null;
let loaded = false;

/** Load the Xiaohongshu-zone catalogue once per browser session. The response
 * contains metadata and stable URLs only; font bytes remain lazy. */
export function loadXiaohongshuFonts(force = false): Promise<PublicFontFace[]> {
  if (!force && loaded) return Promise.resolve([]);
  if (!force && loading) return loading;
  loading = oc.listPublicFonts("xiaohongshu").then((faces) => {
    fonts.setLibraryFonts(faces);
    loaded = true;
    return faces;
  }).finally(() => {
    loading = null;
  });
  return loading;
}

export function addXiaohongshuFont(face: PublicFontFace): void {
  fonts.addLibraryFont(face);
  loaded = true;
}
