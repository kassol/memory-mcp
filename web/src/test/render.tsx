import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "@/app";
import { makeQueryClient } from "@/lib/query-client";
import { makeRouter } from "@/router";

import { reset } from "./server";

/** Render the whole console at `path`. Sign-in state comes from `db.session` / `db.password`. */
export async function renderAt(path: string) {
  const router = makeRouter(createMemoryHistory({ initialEntries: [path] }));
  const user = userEvent.setup();
  const view = render(<App router={router} queryClient={makeQueryClient()} />);
  await router.load();
  return { user, router, view };
}

export { reset, screen };
