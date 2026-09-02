# Subset release procedure (extract)

1. A subset release carries only entries that are REVIEWED in the CMS and carry no blocking reason.
2. Entries bound to an unpinned breaking token or component version, or to an asset without an eligible grant, are blocked until the pin, migration, or countersign lands.
3. The release declares the exact entry count; the CMS rejects a count above the shippable entries.
4. Draft entries are not reviewed and never ship.

---
Evidence-room mount: webstudio-008 / WEB-0008.
