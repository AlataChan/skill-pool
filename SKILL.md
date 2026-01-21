---
name: skill-pool
description: A meta-skill that indexes, searches, and recommends Claude skills from both local directories and external registries like awesome-claude-skills. Use this skill when searching for skills by capability or keyword, listing available skills, matching user intent to appropriate skills, or discovering new skills from community repositories.
---

# Skill Pool

A comprehensive meta-skill for discovering, indexing, and selecting Claude skills from multiple sources including local installations and external community repositories.

## Key Features

- **Unified Search**: Search both local skills AND external registries (awesome-claude-skills) in one query
- **External Registry Support**: Automatically discovers skills from GitHub repositories
- **Pre-built Index**: Includes curated index of 45+ skills from awesome-claude-skills for instant search
- **Smart Recommendations**: Suggests the best skill for your task with confidence scores
- **Installation Commands**: Provides copy-paste commands to install external skills

## Quick Start

### Search for a Skill

```bash
# Search across all sources (local + external)
python scripts/unified_search.py "invoice organizer"

# Search local only
python scripts/unified_search.py "pdf creation" --local-only

# Search external only
python scripts/unified_search.py "git automation" --external-only
```

### Get a Specific Skill

```bash
python scripts/unified_search.py --get invoice-organizer
```

### Get a Recommendation

```bash
python scripts/unified_search.py --recommend "I need to organize my receipts"
```

### List All Sources

```bash
python scripts/unified_search.py --list-sources
```

## Supported Skill Sources

### Local Sources (checked first)
| Path | Scope |
|------|-------|
| `/mnt/skills/public/` | Anthropic-provided skills |
| `/mnt/skills/user/` | User-uploaded skills |
| `/mnt/skills/examples/` | Example skills |
| `~/.claude/skills/` | Personal/global skills |
| `.claude/skills/` | Project-specific skills |

### External Registries
| Registry | Description | URL |
|----------|-------------|-----|
| awesome-claude-skills | ComposioHQ's curated collection (6.6k+ stars) | https://github.com/ComposioHQ/awesome-claude-skills |
| anthropic-skills | Official Anthropic skills | https://github.com/anthropics/skills |

## Programmatic Usage

```python
from scripts.unified_search import UnifiedSkillSearch

search = UnifiedSkillSearch()

# Search all sources
results = search.search("invoice organizer")
print(results["local"])    # Local matches
print(results["external"]) # External matches

# Get specific skill
skill = search.get("invoice-organizer")
if not skill["installed"]:
    print(skill["install_command"])

# Get recommendation
rec = search.recommend("organize my PDF invoices")
print(f"Use: {rec['skill']} (confidence: {rec['confidence']})")
```

## External Registry Module

For direct external registry access:

```python
from scripts.external_registry import ExternalRegistry

registry = ExternalRegistry()
registry.load_index()

# Search external skills
results = registry.search("invoice")

# List all external skills
for skill in registry.list_skills():
    print(f"{skill.name}: {skill.description}")
```

## Installing External Skills

When a skill is found externally, the system provides installation commands:

```bash
# Example: Install invoice-organizer
curl -sL https://raw.githubusercontent.com/ComposioHQ/awesome-claude-skills/master/invoice-organizer/SKILL.md \
  -o ~/.claude/skills/invoice-organizer/SKILL.md --create-dirs
```

## Pre-built Index

The skill-pool includes a pre-built index (`references/awesome_claude_skills_index.json`) containing 45+ curated skills for instant offline search:

**Categories:**
- **Document Processing**: docx, pdf, pptx, xlsx, epub-parser, resume-builder
- **Development**: git-pushing, test-fixing, code-reviewer, api-tester, mcp-builder
- **Data Analysis**: csv-data-summarizer, metadata-extraction, postgres-query, sql-generator
- **Productivity**: invoice-organizer, file-organizer, calendar-manager, meeting-notes
- **Security**: computer-forensics, threat-hunting-with-sigma-rules, secret-management
- **Creative**: image-enhancer, imagen, artifacts-builder
- **Communication**: content-research-writer, email-writer, documentation-writer
- **Research**: gemini-deep-research, scientific-computing, materials-science

## Refreshing the Index

To fetch the latest skills from external registries:

```bash
python scripts/unified_search.py --refresh
```

Or programmatically:

```python
search = UnifiedSkillSearch()
count = search.refresh_external()
print(f"Indexed {count} external skills")
```

## Adding Custom Registries

```python
from scripts.external_registry import ExternalRegistry

registry = ExternalRegistry()
registry.add_registry(
    name="my-company-skills",
    owner="my-org",
    repo="claude-skills",
    branch="main",
    priority=5
)
registry.refresh()
```

## CLI Reference

```
unified_search.py [query] [options]

Arguments:
  query                 Search query

Options:
  --query, -q          Search query (alternative)
  --get, -g NAME       Get specific skill by name
  --recommend, -r TEXT Get recommendation for task
  --local-only, -l     Only search local skills
  --external-only, -e  Only search external skills
  --list-sources       List all skill sources
  --refresh            Refresh external registry cache
  --verbose, -v        Verbose output
  --json, -j           Output as JSON
  --top, -n N          Max results (default: 10)
```

## File Reference

| File | Purpose |
|------|---------|
| `scripts/unified_search.py` | Main entry point for skill search |
| `scripts/external_registry.py` | External registry fetching and search |
| `scripts/skill_registry.py` | Local skill registry (existing) |
| `scripts/scan_skills.py` | Directory scanner (existing) |
| `scripts/match_skill.py` | Query matching (existing) |
| `references/awesome_claude_skills_index.json` | Pre-built skill index |
| `references/catalog_schema.json` | JSON schema for catalogs |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| External skill not found | Run `--refresh` to update the index |
| Slow search | Use pre-built index (default) instead of live API |
| Rate limited by GitHub | Wait and use cached results |
| Can't install skill | Check URL is accessible, create directories manually |

## Why This Matters

Before this improvement, skill-pool could only find locally installed skills. Users asking for skills like "invoice-organizer" would get "not found" even though excellent community skills exist.

Now, skill-pool:
1. **First checks local** - instant results for installed skills
2. **Falls back to external** - finds community skills from awesome-claude-skills
3. **Provides installation** - gives commands to install found skills
4. **Works offline** - pre-built index enables search without network
