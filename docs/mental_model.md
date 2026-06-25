

# solver

## graph

binary continuous sparse row (CSR)

### layout

```c
uint32_t canonical_offsets[N + 1];
uint8_t  canonical_bytes[canonical_bytes_len];

uint32_t out_offsets[N + 1];
WaU24    out_neighbors[L];

uint32_t in_offsets[N + 1];
WaU24    in_neighbors[L];
```

### size

- Our current canonical graph count is N = 7,146,840 pages and L = 695,099,364 directed links.
- log2(N) ~= 22.77, so you need 23 bits to represent a node id.
- That is why u24 wastes exactly 1 bit per stored neighbor id.

Exact raw size math for our current format:
- canonical title offsets: 4 * (N + 1) = 28,587,364 bytes
- canonical title bytes: 143,730,678 bytes
- out offsets: 4 * (N + 1) = 28,587,364 bytes
- out neighbors: 3 * L = 2,085,298,092 bytes
- in offsets: 4 * (N + 1) = 28,587,364 bytes
- in neighbors: 3 * L = 2,085,298,092 bytes
- header: 80 bytes
Total:
- 4,400,089,034 bytes
- about 4.10 GiB

### usage

#### only map from id to title (insane space savings)

binary search for title -> id

A really important nuance: we are not storing both page -> id and id -> page as separate maps.
We only store one canonical title table:
- id -> title is direct by offset lookup
- title -> id is binary search because ids are assigned in lexicographic title order 

log_2(7M) = 22.7389234914 -> 23 memory reads worst case.
_however_ we only need to do this for two pages: 'start' and 'target'.
- if we want we could cache target since it will be used repeatedly

## solve

```mermaid

```

### worker

- solver.bin via mmap is shared by the OS anyway
- target-session caches are mutable, so they are only naturally shared inside one process
- so the best first production shape is probably:
  - one solver process per machine
  - one shared graph
  - one shared target-session cache map
  - a small internal worker pool only if concurrency demands it

## cache

