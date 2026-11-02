import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { ThemeProvider } from "next-themes";

import { Toaster } from "@/components/ui/sonner";
import { useIsMobile } from "@/hooks/use-mobile";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeQueryClient } from "@/lib/query-client";
import { SessionProvider } from "@/lib/session";
import { makeRouter } from "@/router";

export function App({ router = makeRouter(), queryClient = makeQueryClient() }: { router?: ReturnType<typeof makeRouter>; queryClient?: QueryClient }) {
  const isMobile = useIsMobile();
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <SessionProvider>
            <RouterProvider router={router} />
            <Toaster position={isMobile ? "top-center" : "bottom-center"} />
          </SessionProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
