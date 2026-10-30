# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML, CSS and plain JavaScript, served by the service itself under `/ui/`. No Node build step and no frontend dependencies (decided in the web console issue). Files ship inside the Python package.

## Users

One owner of a self-hosted memory service. Agents write and read memories through MCP; the owner opens the console to review what maintenance flagged and to fix or archive wrong memories. Mostly on a desktop browser in short review sessions; sometimes on a phone to read and act on a few items.

## Product Purpose

Keep long-term memories fresh and consistent. The console is where a person reviews findings (duplicates, internal contradictions, keys with more than one current version), corrects a memory with authoritative text, archives a wrong one, or dismisses a false positive. Success: the open findings list reaches zero without the owner reading memories one by one in a terminal.

## Operating Context

- Terms follow `GLOSSARY.md`: finding, check, internal contradiction, duplicate, multiple current, correction, archive.
- Memories are mostly Chinese, often long (up to about 1500 characters), with dates, version strings and identifiers.
- Access needs the service's existing Bearer token, entered once per browser session.

## Capabilities and Constraints

- Operations: browse and search current memories, view a memory's version history, correct, archive, review findings side by side, dismiss a finding.
- No creating memories, no bulk delete or merge, no hard delete, no graph or thread views.
- Memory text is untrusted input: render as text only, never as HTML.
- The repository is public: interface copy must not contain host names, personal names or forms of address.

## Brand Commitments

None. Interface language: Chinese.

## Product Principles

- The finding queue is the main job; everything else supports clearing it.
- A person's correction is authoritative and replaces the text exactly as written.
- Every destructive action shows what will change and asks for a reason where the record keeps one.
- Show the full memory text; truncation hides the very contradiction being reviewed.
