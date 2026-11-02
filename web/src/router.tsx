// Routes. Hash history keeps every page under the one static /ui/ index file.
import {
  createHashHistory,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";

import { RouteLoading } from "@/components/page";
import { NotFound, RouteError } from "@/components/route-states";
import { Shell } from "@/shell";

const OverviewPage = lazyRouteComponent(() => import("@/pages/overview"), "OverviewPage");
const DocketPage = lazyRouteComponent(() => import("@/pages/docket"), "DocketPage");
const RecordsPage = lazyRouteComponent(() => import("@/pages/records"), "RecordsPage");
const MaintenancePage = lazyRouteComponent(() => import("@/pages/maintenance"), "MaintenancePage");
const SettingsPage = lazyRouteComponent(() => import("@/pages/settings"), "SettingsPage");

const rootRoute = createRootRoute({ component: Shell });

const recordsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/records",
  validateSearch: (search: Record<string, unknown>): { memory?: string } =>
    typeof search.memory === "string" && search.memory ? { memory: search.memory } : {},
  component: function Records() {
    const { memory } = recordsRoute.useSearch();
    const navigate = recordsRoute.useNavigate();
    return <RecordsPage memory={memory ?? null} onMemory={(id) => void navigate({ search: id ? { memory: id } : {} })} />;
  },
});

const SETTINGS_TABS = ["parameters", "providers", "roles", "tokens", "startup", "security"];

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  validateSearch: (search: Record<string, unknown>): { tab?: string } =>
    typeof search.tab === "string" && search.tab ? { tab: search.tab } : {},
  component: function Settings() {
    const { tab } = settingsRoute.useSearch();
    const navigate = settingsRoute.useNavigate();
    const value = tab && SETTINGS_TABS.includes(tab) ? tab : "parameters";
    return <SettingsPage key={value} tab={value} onTabChange={(next) => void navigate({ search: { tab: next } })} />;
  },
});

const docketRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/docket",
  validateSearch: (search: Record<string, unknown>): { kind?: string } =>
    typeof search.kind === "string" && search.kind ? { kind: search.kind } : {},
  component: function Docket() {
    const { kind } = docketRoute.useSearch();
    return <DocketPage key={kind ?? "all"} initialKind={kind ?? null} />;
  },
});

const routes = [
  createRoute({ getParentRoute: () => rootRoute, path: "/", beforeLoad: () => { throw redirect({ to: "/docket" }); } }),
  createRoute({ getParentRoute: () => rootRoute, path: "/overview", component: OverviewPage }),
  docketRoute,
  recordsRoute,
  createRoute({ getParentRoute: () => rootRoute, path: "/maintenance", component: MaintenancePage }),
  settingsRoute,
];

const routeTree = rootRoute.addChildren([...routes]);

export function makeRouter(history: RouterHistory = createHashHistory()) {
  return createRouter({
    routeTree,
    history,
    defaultPreload: "intent",
    defaultPendingComponent: RouteLoading,
    defaultPendingMs: 150,
    defaultErrorComponent: RouteError,
    defaultNotFoundComponent: NotFound,
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof makeRouter>;
  }
}
