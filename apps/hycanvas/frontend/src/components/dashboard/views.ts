// Dashboard sections addressable by URL: /dashboard/ plus /dashboard/<view>/.
// pages/dashboard/index.tsx covers home; pages/dashboard/[view].tsx covers the
// rest. This list is the single source of truth for the left rail and routes.
// Kept free of the (client-only) DashboardApp so pages can import it for
// getStaticPaths without pulling the whole dashboard into the page bundle.

export const dashboardViews = [
  "home",
  "favorites",
  "tasks",
  "templates",
  "members",
  "trash",
] as const;

export type DashboardView = (typeof dashboardViews)[number];

export const dashboardTitles: Record<DashboardView, string> = {
  home: "Your designs",
  favorites: "Favorites",
  tasks: "My tasks",
  templates: "Templates",
  members: "Members",
  trash: "Trash",
};

/** Route for a section; home lives at the bare /dashboard path. */
export function dashboardPath(view: DashboardView): string {
  return view === "home" ? "/dashboard/" : `/dashboard/${view}/`;
}
