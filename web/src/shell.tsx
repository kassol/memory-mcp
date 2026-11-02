// App shell: a porcelain sidebar (a sheet on phones), the command palette, and the signed-out view.
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { LogOut, Monitor, Moon, Search, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Fragment, useEffect, useState } from "react";

import { BrandMark } from "@/components/brand";
import { Button } from "@/components/ui/button";
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
                <BrandMark className="dark:bg-[#1e211f] dark:text-[#edebe5] dark:ring-1 dark:ring-[#2c302d]" />
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
            审阅
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <nav aria-label="页面">
              <SidebarMenu className="gap-0.5">
                {NAV.map((n, index) => {
                  const active = pathname === n.to;
                  return (
                    <Fragment key={n.to}>
                      {index === 3 ? (
                        <li className="px-2 pt-4 pb-1 text-[10px] font-medium tracking-[0.12em] text-muted-foreground group-data-[collapsible=icon]:hidden">
                          系统
                        </li>
                      ) : null}
                    <SidebarMenuItem>
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
                        <Link to={n.to} onClick={close} aria-current={active ? "page" : undefined}>
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
                    </Fragment>
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
      </SidebarFooter>
    </Sidebar>
  );
}

/** The session check is local and quick; a mark appears only when it takes noticeably long. */
function Splash() {
  return (
    <div className="grid min-h-svh place-items-center bg-background" aria-busy="true" aria-label="正在载入面板">
      <BrandMark className="size-10 rounded-[11px] text-[15px]" />
    </div>
  );
}

function SessionUnavailable({ error, retry }: { error: Error | null; retry: () => void }) {
  return (
    <div className="grid min-h-svh place-items-center bg-background p-6">
      <div className="flex max-w-sm flex-col items-center text-center">
        <BrandMark className="size-10 rounded-[11px] text-[15px]" />
        <p className="mt-4 text-sm font-medium">无法连接服务</p>
        <p className="mt-1 text-xs leading-5 break-words text-muted-foreground">
          {error?.message ?? "面板会话没有响应。"}
        </p>
        <Button variant="outline" size="sm" className="mt-4" onClick={retry}>
          重试
        </Button>
      </div>
    </div>
  );
}

export function Shell() {
  const { status, error, retry } = useSession();
  const findings = useFindings();
  const [palette, setPalette] = useState(false);
  const [waited, setWaited] = useState(false);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const signedIn = !!status?.signed_in && !status.bootstrap;

  useEffect(() => {
    const id = setTimeout(() => setWaited(true), 250);
    return () => clearTimeout(id);
  }, []);

  // The tab and the back history name the page, not just the product.
  useEffect(() => {
    if (!status) return;
    if (!signedIn) {
      document.title = "登录 · 记忆登记簿";
      return;
    }
    const page = NAV.find((n) => pathname === n.to);
    // Away from the queue, the tab itself carries the number waiting, so a pinned console still tells.
    const pending = findings.data?.total ?? 0;
    const prefix = pending > 0 && pathname !== "/docket" ? `(${pending}) ` : "";
    document.title = `${prefix}${page?.label ?? "页面不存在"} · 记忆登记簿`;
  }, [pathname, signedIn, status, findings.data?.total]);

  if (!status) return waited ? error ? <SessionUnavailable error={error} retry={retry} /> : <Splash /> : null;
  if (!signedIn) return <SignInPage />;

  return (
    <SidebarProvider className="h-full">
      <button
        type="button"
        onClick={() => document.getElementById("main-content")?.focus()}
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow"
      >
        跳到主要内容
      </button>
      <AppSidebar onPalette={() => setPalette(true)} />
      <SidebarInset id="main-content" tabIndex={-1} className="min-h-0 min-w-0 overflow-hidden focus:outline-none">
        <Outlet />
      </SidebarInset>
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </SidebarProvider>
  );
}
