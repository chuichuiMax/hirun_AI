import type { GetStaticPaths, GetStaticProps } from "next";
import { DashboardRoutePage } from "@/components/dashboard/DashboardRoutePage";
import { dashboardViews, type DashboardView } from "@/components/dashboard/views";

interface DashboardViewPageProps {
  view: DashboardView;
}

const nestedViews = dashboardViews.filter((v) => v !== "home");

export const getStaticPaths: GetStaticPaths = async () => ({
  paths: nestedViews.map((view) => ({ params: { view } })),
  fallback: process.env.NODE_ENV === "development" ? "blocking" : false,
});

export const getStaticProps: GetStaticProps<DashboardViewPageProps> = async ({ params }) => {
  const view = String(params?.view || "");
  if (!(nestedViews as readonly string[]).includes(view)) {
    return { notFound: true };
  }
  return { props: { view: view as DashboardView } };
};

export default function DashboardViewPage({ view }: DashboardViewPageProps) {
  return <DashboardRoutePage view={view} />;
}
