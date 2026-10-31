import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "@/app";
import { makeQueryClient } from "@/lib/query-client";
import { makeRouter } from "@/router";

import { reset, TOKEN } from "./server";

/** Render the whole console at `path`; signed in unless `signedIn` is false. */
export async function renderAt(path: string, { signedIn = true } = {}) {
  if (signedIn) sessionStorage.setItem("memory-mcp.access-token", TOKEN);
  const router = makeRouter(createMemoryHistory({ initialEntries: [path] }));
  const user = userEvent.setup();
  const view = render(<App router={router} queryClient={makeQueryClient()} />);
  await router.load();
  return { user, router, view };
}

export { reset, screen };
