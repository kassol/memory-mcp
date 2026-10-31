import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";

import { Toaster } from "@/components/ui/sonner";
import { makeQueryClient } from "@/lib/query-client";
import { SessionProvider } from "@/lib/session";
import { makeRouter } from "@/router";

export function App({ router = makeRouter(), queryClient = makeQueryClient() }: { router?: ReturnType<typeof makeRouter>; queryClient?: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <RouterProvider router={router} />
        <Toaster position="bottom-center" />
      </SessionProvider>
    </QueryClientProvider>
  );
}
