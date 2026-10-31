import { Archive, Gauge, Inbox, Settings, Wrench, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: "/overview" | "/docket" | "/records" | "/maintenance" | "/settings";
  label: string;
  icon: LucideIcon;
}

export const NAV: NavItem[] = [
  { to: "/overview", label: "概览", icon: Gauge },
  { to: "/docket", label: "待审", icon: Inbox },
  { to: "/records", label: "档案", icon: Archive },
  { to: "/maintenance", label: "维护", icon: Wrench },
  { to: "/settings", label: "设置", icon: Settings },
];
