# Inter-store segment copy procedure (extract)

1. Only releasable sets move: status VERIFIED, not reserved for a named ticket, and at least the class minimum remaining retention.
2. Copies ride the 21:00 replication run; segments are checksum-verified and released at the receiving store on the next business day after the scheduled date.
3. The receiving store's own releasable segments are used first; copy only the uncovered quantity.
4. Lapsed or reserved sets are never copied, whatever the requesting team's need.
