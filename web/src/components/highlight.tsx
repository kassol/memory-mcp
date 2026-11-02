// Highlight the search terms inside memory text. The text is untrusted, so every part stays a
// React text node; nothing is injected as HTML.
import { Fragment } from "react";

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function Highlight({ text, query }: { text: string; query: string }) {
  const terms = query.trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return <>{text}</>;

  const pattern = new RegExp(`(${terms.map(escape).join("|")})`, "gi");
  const parts = text.split(pattern);
  if (parts.length === 1) return <>{text}</>;

  const matched = new Set(terms.map((term) => term.toLowerCase()));
  return (
    <>
      {parts.map((part, index) =>
        matched.has(part.toLowerCase()) ? (
          <mark key={index} className="rounded-[2px] bg-primary/15 px-0.5 text-foreground">
            {part}
          </mark>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  );
}
