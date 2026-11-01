// Routes. Hash history keeps every page under the one static /ui/ index file.
import {
  createHashHistory,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";

import { DocketPage } from "@/pages/docket";
import { MaintenancePage } from "@/pages/maintenance";
import { OverviewPage } from "@/pages/overview";
import { RecordsPage } from "@/pages/records";
import { SettingsPage } from "@/pages/settings";
import { Shell } from "@/shell";

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

const routes = [
  createRoute({ getParentRoute: () => rootRoute, path: "/", beforeLoad: () => { throw redirect({ to: "/docket" }); } }),
  createRoute({ getParentRoute: () => rootRoute, path: "/overview", component: OverviewPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/docket", component: DocketPage }),
  recordsRoute,
  createRoute({ getParentRoute: () => rootRoute, path: "/maintenance", component: MaintenancePage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/settings", component: SettingsPage }),
];

const routeTree = rootRoute.addChildren([...routes]);

export function makeRouter(history: RouterHistory = createHashHistory()) {
  return createRouter({ routeTree, history, defaultPreload: false });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof makeRouter>;
  }
}
