---
description: "Search literature and prior art for a research topic. Usage: /literature <query> or /literature verify-novelty <finding>"
allowed-tools: ["Bash(*)", "Read(*)", "Write(*)", "WebSearch(*)", "WebFetch(*)"]
---

Perform a literature search for the Autolab research project.

If the argument starts with "verify-novelty":
- Take the finding description that follows
- Search for prior art: academic papers, GitHub repos, blog posts, official documentation
- Report what was found and whether the finding appears novel
- Format the output as a "Prior art search" section suitable for DISCOVERIES.md

If the argument starts with "suggest-approaches":
- Take the research question that follows
- Search for alternative approaches, techniques, and methods
- Report what could be tried that hasn't been attempted yet
- Focus on actionable approaches, not general background

Otherwise:
- Treat the argument as a general research query
- Search the web for relevant papers, implementations, and discussions
- Summarize findings with citations
- Highlight what's relevant to the current research directive in autolab.yaml

$ARGUMENTS
