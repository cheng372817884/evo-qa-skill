# Domains — Industry-Specific Knowledge

This directory is reserved for **industry/domain-specific** QA knowledge.

When using Evo QA with a specific industry (e.g., fintech, healthcare, e-commerce, insurance, etc.), you can add domain knowledge here as Markdown files organized by domain name.

### Structure

```
domains/
├── README.md              # this file
├── <domain-name>/
│   ├── glossary.md        # domain-specific terminology
│   ├── quirks.md          # known UI/automation quirks
│   ├── navigation-map.md  # structural selectors and navigation patterns
│   └── examples/          # reference code snippets
```

### How it works

- The `by_domain` knowledge loading strategy (configured in `SKILL.md`) automatically picks up files from this directory when a matching domain is detected.
- Entries are indexed by `references/knowledge/_index.md` for efficient retrieval.
- Domain knowledge follows the same lifecycle as universal heuristics: `active → stale → deprecated → archived`.

### Getting started

To add knowledge for your domain:

1. Create a new directory: `mkdir -p domains/<your-domain>`
2. Write your knowledge files (Markdown with YAML frontmatter)
3. Run the index builder to register entries

---

*This directory ships empty — populate it with your project's domain knowledge.*
