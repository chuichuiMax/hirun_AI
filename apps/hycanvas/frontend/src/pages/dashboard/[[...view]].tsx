import Head from "next/head";
import dynamic from "next/dynamic";
import type { GetStaticPaths, GetStaticProps } from "next";
import { RequireAuth } from "@/components/RequireAuth";
import {
  dashboardTitles,
  dashboardViews,
  type DashboardView,
} from "@/components/dashboard/views";
import { tr } from "@/lib/i18n";

// Client-only: depends on auth state, localStorage, and live API calls.
const DashboardApp = dynamic(() => import("@/components/dashboard/DashboardApp").then((m) => m.DashboardApp), {
  ssr: false,
  loading: () => <div className="grid min-h-screen place-items-center text-sm text-neutral-500">{tr("page.loading")}</div>,
});

interface DashboardPageProps {
  view: DashboardView;
}

// One exported static page per dashboard section, so every section has a real
// URL: deep-linkable, refresh-safe, and back/forward-friendly. All of them
// render this same page component, so client-side navigation between sections
// keeps the mounted DashboardApp (and its loaded data) alive.
export const getStaticPaths: GetStaticPaths = async () => ({
  // Prefer [] over false: with trailingSlash + Turbopack `next dev`, the bare
  // /dashboard/ root is only reliably generated from an empty catch-all array.
  paths: dashboardViews.map((v) => ({ params: { view: v === "home" ? [] : [v] } })),
  // Production static export still requires fallback:false. Turbopack's pages
  // router often skips materializing these optional catch-all paths in `next
  // dev`, which sent ContentFlow's post-login /dashboard/ embed to the 404 page.
  fallback: process.env.NODE_ENV === "development" ? "blocking" : false,
});

export const getStaticProps: GetStaticProps<DashboardPageProps> = async ({ params }) => {
  const slug = Array.isArray(params?.view) ? params.view[0] : "home";
  return { props: { view: slug as DashboardView } };
};

export default function DashboardPage({ view }: DashboardPageProps) {
  return (
    <>
      <Head>
        <title>{`${dashboardTitles[view]} · HyCanvas`}</title>
      </Head>
      <RequireAuth>
        <DashboardApp view={view} />
      </RequireAuth>
    </>
  );
}
