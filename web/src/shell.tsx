// App shell: a porcelain sidebar (a sheet on phones), the command palette, and the signed-out view.
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { LogOut, Monitor, Moon, Search, Sun } from "lucide-react";
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
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
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
      <SidebarMenuButton
        onClick={() => setTheme(next.value)}
        tooltip={`外观：${current.label}`}
        className="h-8 rounded-lg text-[13px] text-muted-foreground"
      >
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
    <Sidebar collapsible="icon" className="border-r-0">
      <SidebarHeader className="px-3 pt-4 pb-1">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild className="h-11 rounded-xl px-1.5 hover:bg-transparent">
              <Link to="/docket" onClick={close}>
                <span className="relative grid size-8 shrink-0 place-items-center rounded-[9px] bg-foreground text-[13px] font-semibold text-background dark:bg-[#1e211f] dark:text-[#edebe5] dark:ring-1 dark:ring-[#2c302d]">
                  记
                  <span className="absolute right-1 bottom-1 size-1.5 rounded-full bg-primary" />
                </span>
                <span className="grid flex-1 gap-0 text-left leading-tight">
                  <span className="truncate text-[13px] font-semibold tracking-[-0.01em]">记忆登记簿</span>
                  <span className="truncate text-[9px] tracking-[0.12em] text-muted-foreground">MEMORY REGISTRY</span>
                </span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent className="gap-0 px-2">
        <SidebarGroup className="p-0 pt-3">
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="跳转或检索"
                  onClick={() => {
                    close();
                    onPalette();
                  }}
                  className="h-9 rounded-lg text-[13px] text-muted-foreground hover:bg-sidebar-accent"
                >
                  <Search />
                  <span>跳转或检索</span>
                  <Kbd className="ml-auto border-0 bg-sidebar-accent text-[10px] group-data-[collapsible=icon]:hidden">⌘K</Kbd>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup className="p-0 pt-5">
          <SidebarGroupLabel className="px-2 text-[10px] font-medium tracking-[0.12em] text-muted-foreground">
            工作台
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <nav aria-label="页面">
              <SidebarMenu className="gap-0.5">
                {NAV.map((n) => {
                  const active = pathname === n.to;
                  return (
                    <SidebarMenuItem key={n.to}>
                      <SidebarMenuButton
                        asChild
                        isActive={active}
                        tooltip={n.label}
                        className={cn(
                          "h-9 rounded-lg text-[13px] text-muted-foreground transition-colors",
                          "hover:bg-sidebar-accent hover:text-sidebar-foreground",
                          "data-[active=true]:bg-card data-[active=true]:font-medium data-[active=true]:text-foreground",
                          "data-[active=true]:shadow-[0_1px_2px_rgba(23,24,26,0.06)]",
                          "data-[active=true]:[&_svg]:text-primary",
                          "dark:data-[active=true]:bg-[#1e211f] dark:data-[active=true]:shadow-none",
                        )}
                      >
                        <Link to={n.to} onClick={close}>
                          <n.icon />
                          <span>{n.label}</span>
                        </Link>
                      </SidebarMenuButton>
                      {n.to === "/docket" && findings.data && findings.data.total > 0 ? (
                        <SidebarMenuBadge className="right-2 h-5 min-w-5 rounded-full bg-primary/10 px-1.5 text-[10px] font-medium text-primary peer-data-[active=true]/menu-button:bg-primary/15">
                          {findings.data.total}
                        </SidebarMenuBadge>
                      ) : null}
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="px-2 pb-3">
        <SidebarMenu className="gap-0.5">
          <ThemeItem />
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => void signOut()}
              tooltip="退出"
              className="h-8 rounded-lg text-[13px] text-muted-foreground"
            >
              <LogOut />
              <span>退出</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <p className="px-2 pt-2 text-[10px] text-muted-foreground group-data-[collapsible=icon]:hidden">
          长期记忆 · 人工裁定
        </p>
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
