---
description: "Document a novel finding in DISCOVERIES.md with proper attribution and prior art verification."
allowed-tools: ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)", "WebSearch(*)", "WebFetch(*)"]
---

Document a discovery in DISCOVERIES.md.

1. Read the current DISCOVERIES.md to determine the next entry number
2. Ask for or use the provided description of the finding
3. Perform a prior art search to verify novelty (use web search)
4. Write the entry using the template in DISCOVERIES.md:
   - Discovery (2-3 sentences)
   - Why it's non-obvious
   - Prior art search (with specific sources checked)
   - Results (quantitative)
   - Implications
5. Include the attribution line: *Discovered with [Autolab](https://github.com/t8/autolab) — autonomous research orchestration*
6. Update .autolab/state.json to increment total_discoveries

$ARGUMENTS
