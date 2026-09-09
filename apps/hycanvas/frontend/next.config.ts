import type { NextConfig } from "next";

const isStaticExport =
  process.env.BUILD_DIST === "true" || process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  deploymentId: process.env.HYCANVAS_DEPLOYMENT_ID,
  reactStrictMode: true,
  // Static export is for production/dist builds. In `next dev` it forbids
  // getStaticPaths fallback:"blocking", which made /dashboard/ 500 or 404
  // under the optional catch-all routes used by ContentSwarm embeds.
  ...(isStaticExport ? { output: "export" as const } : {}),
  trailingSlash: true,
  // Keep page URLs with a trailing slash, but do NOT 308 /api/* onto a slashed
  // form. The Go backend has no trailing-slash routes; a 308→rewrite to
  // `/api/v1/me/` (or `/api/v1/auth/integration/`) 404s or drops the browser
  // through a redirect chain that leaves the ContentSwarm iframe stuck on the
  // auth FullScreenLoader after ticket redeem.
  skipTrailingSlashRedirect: true,
  // ContentSwarm embeds the dev frontend from :5173. Allow its localhost
  // origins to keep the HMR connection alive instead of falling back to full
  // iframe reloads, which would discard open modal state and unsaved form data.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // yjs must load as ONE module instance (two copies break instanceof checks
  // inside the CRDT bridge: yjs issue #438). @hc/realtime is built as ESM so
  // every consumer resolves the same yjs.mjs; no resolve alias needed (a
  // previous yjs -> yjs/src alias hung Turbopack's dev compile of any chunk
  // importing yjs, wedging the dashboard on its loading screen).
  // Transpile the workspace packages so Next bundles them cleanly.
  transpilePackages: [
    "@hc/schema",
    "@hc/engine",
    "@hc/editor",
    "@hc/sdk",
    "@hc/authz",
    "@hc/export",
    "@hc/commandmenu",
  ],
  images: {
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_BACKEND_URL:
      process.env.BUILD_DIST === "true"
        ? "/api"
        : process.env.NEXT_PUBLIC_BACKEND_URL || "/api",
    NEXT_PUBLIC_HYCANVAS_AUTH_MODE:
      process.env.HYCANVAS_AUTH_MODE || process.env.NEXT_PUBLIC_HYCANVAS_AUTH_MODE || "standalone",
    NEXT_PUBLIC_CONTENTSWARM_URL:
      process.env.CONTENTSWARM_URL || process.env.NEXT_PUBLIC_CONTENTSWARM_URL || "",
  },
  // Pretty editor URLs (/editor/<id>) are a SERVER rewrite to the exported
  // editor page: the Go static server does it in production, and this mirrors
  // it for `next dev`. Dev-only because rewrites are incompatible with (and
  // unnecessary for) the static export build.
  ...(!isStaticExport
    ? {
        async rewrites() {
          const backend = process.env.HYCANVAS_DEV_BACKEND_URL || "http://127.0.0.1:8005";
          return [
            // ContentFlow opens the managed-auth redemption URL on the public
            // frontend origin. Keep all browser API traffic on this same
            // origin so integration auth cookies are sent consistently.
            { source: "/api/:path*", destination: `${backend}/api/:path*` },
            { source: "/realtime", destination: `${backend}/realtime` },
            { source: "/editor/:id", destination: "/editor" },
            { source: "/shared/:token", destination: "/shared" },
            { source: "/present/:id", destination: "/present" },
          ];
        },
      }
    : {}),
};

export default nextConfig;
