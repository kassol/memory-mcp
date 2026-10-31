// App shell: shadcn Sidebar (a sheet on phones), command palette, and the signed-out view.
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { BookMarked, LogOut, Monitor, Moon, Search, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useState } from "react";

import { CommandPalette } from "@/components/command-palette";
import { Kbd } from "@/components/ui/kbd";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  useSidebar,
} from "@/components/ui/sidebar";
import { useFindings } from "@/lib/queries";
import { useSession } from "@/lib/session";
import { NAV } from "@/nav";
import { SignInPage } from "@/pages/sign-in";

const THEMES = [
  { value: "system", label: "跟随系统", icon: Monitor },
  { value: "light", label: "浅色", icon: Sun },
  { value: "dark", label: "深色", icon: Moon },
] as const;

function ThemeItem() {
  const { theme = "system", setTheme } = useTheme();
  const current = THEMES.find((t) => t.value === theme) ?? THEMES[0];
  const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];
  return (
    <SidebarMenuItem>
      <SidebarMenuButton onClick={() => setTheme(next.value)} tooltip={`外观：${current.label}`}>
        <current.icon />
        <span>外观：{current.label}</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

function AppSidebar({ onPalette }: { onPalette: () => void }) {
  const findings = useFindings();
  const { signOut } = useSession();
  const { isMobile, setOpenMobile } = useSidebar();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const close = () => isMobile && setOpenMobile(false);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link to="/docket" onClick={close}>
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <BookMarked className="size-4" />
                </div>
                <div className="grid flex-1 text-left leading-tight">
                  <span className="truncate font-medium">记忆登记簿</span>
                  <span className="truncate text-xs text-muted-foreground">Memory MCP</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="跳转或检索"
                  onClick={() => {
                    close();
                    onPalette();
                  }}
                >
                  <Search />
                  <span>跳转或检索</span>
                  <Kbd className="ml-auto group-data-[collapsible=icon]:hidden">⌘K</Kbd>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupContent>
            <nav aria-label="页面">
            <SidebarMenu>
              {NAV.map((n) => (
                <SidebarMenuItem key={n.to}>
                  <SidebarMenuButton asChild isActive={pathname === n.to} tooltip={n.label}>
                    <Link to={n.to} onClick={close}>
                      <n.icon />
                      <span>{n.label}</span>
                    </Link>
                  </SidebarMenuButton>
                  {n.to === "/docket" && findings.data && <SidebarMenuBadge>{findings.data.total}</SidebarMenuBadge>}
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <ThemeItem />
          <SidebarMenuItem>
            <SidebarMenuButton onClick={() => void signOut()} tooltip="退出">
              <LogOut />
              <span>退出</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

export function Shell() {
  const { status } = useSession();
  const [palette, setPalette] = useState(false);

  if (!status) return null;
  if (!status.signed_in || status.bootstrap) return <SignInPage />;

  return (
    <SidebarProvider className="h-full">
      <AppSidebar onPalette={() => setPalette(true)} />
      <SidebarInset className="min-h-0 min-w-0 overflow-hidden">
        <Outlet />
      </SidebarInset>
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </SidebarProvider>
  );
}
