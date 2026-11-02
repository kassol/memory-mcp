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
import { cleanRecordsSearch, parseRecordsSearch } from "@/lib/records-search";
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
  validateSearch: parseRecordsSearch,
  component: function Records() {
    const search = recordsRoute.useSearch();
    const navigate = recordsRoute.useNavigate();
    return (
      <RecordsPage
        search={search}
        onSearch={(next, options) => void navigate({ search: cleanRecordsSearch(next), replace: options?.replace ?? true })}
      />
    );
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
    return <SettingsPage tab={value} onTabChange={(next) => void navigate({ search: next === "parameters" ? {} : { tab: next } })} />;
  },
});

const docketRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/docket",
  validateSearch: (search: Record<string, unknown>): { kind?: string; case?: string } => {
    const out: { kind?: string; case?: string } = {};
    if (typeof search.kind === "string" && search.kind) out.kind = search.kind;
    if (typeof search.case === "string" && search.case) out.case = search.case;
    return out;
  },
  component: function Docket() {
    const { kind = null, case: chosen = null } = docketRoute.useSearch();
    const navigate = docketRoute.useNavigate();
    return (
      <DocketPage
        kind={kind}
        chosen={chosen}
        onChange={(patch) => {
          const next: { kind?: string; case?: string } = {};
          const nextKind = "kind" in patch ? patch.kind : kind;
          const nextCase = "case" in patch ? patch.case : chosen;
          if (nextKind) next.kind = nextKind;
          if (nextCase) next.case = nextCase;
          void navigate({ search: next, replace: true });
        }}
      />
    );
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
