import type { GetStaticProps } from "next";
import { DashboardRoutePage } from "@/components/dashboard/DashboardRoutePage";

// Bare /dashboard/ must be a real index page. Turbopack's optional catch-all
// often fails to materialize the empty-param root, which 404'd ContentSwarm embeds.
export const getStaticProps: GetStaticProps = async () => ({ props: {} });

export default function DashboardHomePage() {
  return <DashboardRoutePage view="home" />;
}
