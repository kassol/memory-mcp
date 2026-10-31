// App shell: sidebar navigation (drawer on phones), command palette, and the signed-out view.
import { Link, Outlet } from "@tanstack/react-router";
import { LogOut, Menu, Search } from "lucide-react";
import { useState } from "react";

import { CommandPalette } from "@/components/command-palette";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useFindings } from "@/lib/queries";
import { useSession } from "@/lib/session";
import { NAV } from "@/nav";
import { SignInPage } from "@/pages/sign-in";

function Mark() {
  return <span aria-hidden className="h-[1.125rem] w-3 shrink-0 rounded-[1px] border-2 border-t-[5px] border-ink" />;
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const findings = useFindings();
  return (
    <nav aria-label="页面" className="grid gap-0.5">
      {NAV.map((n) => (
        <Link
          key={n.to}
          to={n.to}
          onClick={onNavigate}
          className="flex items-center gap-2.5 rounded-[6px] px-2.5 py-2 text-ink-2 hover:bg-ground hover:text-ink aria-[current=page]:bg-wash aria-[current=page]:font-semibold aria-[current=page]:text-ink"
        >
          <n.icon aria-hidden className="size-4" />
          {n.label}
          {n.to === "/docket" && findings.data && (
            <span className="ml-auto font-mono text-xs leading-none font-semibold text-ink-3 tabular-nums in-aria-[current=page]:text-blue">
              {findings.data.total}
            </span>
          )}
        </Link>
      ))}
    </nav>
  );
}

export function Shell() {
  const { signedIn, signOut } = useSession();
  const [palette, setPalette] = useState(false);
  const [menu, setMenu] = useState(false);

  const paletteButton = (
    <button
      type="button"
      onClick={() => setPalette(true)}
      className="flex w-full items-center gap-2 rounded-[6px] border border-rule-strong bg-sheet px-2.5 py-1.5 text-sm text-ink-3 hover:border-ink-3"
    >
      <Search aria-hidden className="size-4" />
      <span className="mr-auto">跳转或检索</span>
      <kbd>⌘K</kbd>
    </button>
  );

  if (!signedIn) {
    return (
      <div className="flex h-full flex-col">
        <header className="flex h-13 flex-none items-center gap-3 border-b border-rule-strong bg-sheet px-5">
          <Mark />
          <h1 className="m-0 text-base font-[650] tracking-[0.02em]">记忆登记簿</h1>
        </header>
        <SignInPage />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col md:flex-row">
      <header className="flex h-13 flex-none items-center gap-3 border-b border-rule-strong bg-sheet px-3 md:hidden">
        <Button variant="quiet" size="icon" aria-label="打开导航" onClick={() => setMenu(true)}>
          <Menu aria-hidden />
        </Button>
        <Mark />
        <span className="text-[0.9375rem] font-[650] tracking-[0.02em]">记忆登记簿</span>
        <Button variant="quiet" size="icon" className="ml-auto" aria-label="跳转或检索" onClick={() => setPalette(true)}>
          <Search aria-hidden />
        </Button>
      </header>
      <Sheet open={menu} onOpenChange={setMenu}>
        <SheetContent side="left" className="w-72 gap-0 border-rule-strong bg-sheet p-3">
          <SheetHeader className="flex-row items-center gap-3 px-2 pt-1 pb-4">
            <Mark />
            <SheetTitle className="text-base font-[650]">记忆登记簿</SheetTitle>
            <SheetDescription className="sr-only">页面导航</SheetDescription>
          </SheetHeader>
          <NavLinks onNavigate={() => setMenu(false)} />
          <Button variant="quiet" className="mt-auto justify-start" onClick={signOut}>
            <LogOut aria-hidden />
            退出
          </Button>
        </SheetContent>
      </Sheet>
      <aside className="hidden w-56 flex-none flex-col gap-4 border-r border-rule-strong bg-sheet p-3 md:flex">
        <div className="flex items-center gap-3 px-2 pt-1.5">
          <Mark />
          <span className="text-base font-[650] tracking-[0.02em]">记忆登记簿</span>
        </div>
        {paletteButton}
        <NavLinks />
        <Button variant="quiet" className="mt-auto justify-start" onClick={signOut}>
          <LogOut aria-hidden />
          退出
        </Button>
      </aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <Outlet />
      </main>
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}
