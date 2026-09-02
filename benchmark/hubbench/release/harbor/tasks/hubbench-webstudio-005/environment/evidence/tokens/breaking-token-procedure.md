# Breaking token version procedure (extract)

1. A proposed version flagged breaking may be published only when every active consumer outside the change is migrated to it or pinned to the current version.
2. The consumer count comes from the live registry; DEPRECATED and MIGRATED rows are excluded, as are the consumers on the change's own page, which take the new version.
3. A pin names the token, the held version, the change request, and the exact number of consumers it holds; the registry rejects a count above the active off-page consumers.
4. Agency migrations register in the component library the next business day after delivery.

---
Evidence-room mount: webstudio-005 / WEB-0005.
