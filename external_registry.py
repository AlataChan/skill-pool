#!/usr/bin/env python3
"""
External Registry - Fetch and search skills from remote sources.

Supports:
- GitHub repositories (like awesome-claude-skills)
- Raw skill indexes (JSON)
- GitHub API directory listing

Usage:
    from external_registry import ExternalRegistry
    
    registry = ExternalRegistry()
    results = registry.search("invoice organizer")
    skill = registry.get("invoice-organizer")
"""

import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


# ============================================================================
# CURATED REGISTRY SOURCES
# ============================================================================

KNOWN_REGISTRIES = [
    {
        "name": "awesome-claude-skills",
        "description": "ComposioHQ's curated list of awesome Claude Skills",
        "type": "github",
        "owner": "ComposioHQ",
        "repo": "awesome-claude-skills",
        "branch": "master",
        "url": "https://github.com/ComposioHQ/awesome-claude-skills",
        "priority": 1,
    },
    {
        "name": "anthropic-skills",
        "description": "Official Anthropic skills repository",
        "type": "github",
        "owner": "anthropics",
        "repo": "skills",
        "branch": "main",
        "url": "https://github.com/anthropics/skills",
        "priority": 2,
    },
]


@dataclass
class RemoteSkill:
    """Represents a skill from an external registry."""
    name: str
    description: str
    source: str
    url: str
    category: str = "general"
    keywords: List[str] = None
    readme_url: str = ""
    skill_md_url: str = ""
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
    
    def to_dict(self) -> dict:
        return asdict(self)


class ExternalRegistry:
    """Registry for discovering and searching skills from external sources."""
    
    def __init__(self, cache_dir: str = None):
        """Initialize external registry with optional cache directory."""
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".claude" / "skill-cache"
        self.skills: Dict[str, RemoteSkill] = {}
        self.registries = KNOWN_REGISTRIES.copy()
        self._index_loaded = False
        
    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _fetch_url(self, url: str, timeout: int = 10) -> Optional[str]:
        """Fetch content from URL."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Claude-Skill-Pool/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode('utf-8')
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"Warning: Failed to fetch {url}: {e}")
            return None
    
    def _parse_github_tree(self, owner: str, repo: str, branch: str = "master") -> List[str]:
        """Get list of directories from GitHub repo (potential skills)."""
        # Use GitHub API to list repo contents
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents?ref={branch}"
        content = self._fetch_url(api_url)
        
        if not content:
            return []
        
        try:
            items = json.loads(content)
            # Return directory names (potential skill folders)
            return [item["name"] for item in items if item["type"] == "dir" and not item["name"].startswith(".")]
        except (json.JSONDecodeError, KeyError):
            return []
    
    def _fetch_skill_md(self, owner: str, repo: str, skill_name: str, branch: str = "master") -> Optional[str]:
        """Fetch SKILL.md content from GitHub."""
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{skill_name}/SKILL.md"
        return self._fetch_url(raw_url)
    
    def _parse_skill_frontmatter(self, content: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse name and description from SKILL.md frontmatter."""
        if not content.startswith('---'):
            return None, None
        
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None, None
        
        frontmatter = parts[1].strip()
        
        name = None
        description = None
        
        for line in frontmatter.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                
                if key == 'name':
                    name = value
                elif key == 'description':
                    description = value
        
        return name, description
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        stopwords = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
            'and', 'but', 'if', 'or', 'this', 'that', 'use', 'using',
            'claude', 'skill', 'skills', 'can', 'your', 'you'
        }
        
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())
        keywords = []
        seen = set()
        
        for word in words:
            if word not in stopwords and word not in seen:
                seen.add(word)
                keywords.append(word)
                if len(keywords) >= 15:
                    break
        
        return keywords
    
    def _categorize(self, name: str, description: str) -> str:
        """Categorize skill based on name and description."""
        text = (name + ' ' + description).lower()
        
        categories = {
            'document-processing': ['docx', 'pdf', 'pptx', 'xlsx', 'document', 'spreadsheet', 'word', 'excel'],
            'development': ['code', 'git', 'debug', 'test', 'build', 'deploy', 'api', 'mcp', 'plugin'],
            'data-analysis': ['data', 'csv', 'analyze', 'chart', 'visualization', 'query', 'database'],
            'creative': ['design', 'image', 'art', 'canvas', 'gif', 'video', 'theme', 'brand'],
            'communication': ['email', 'slack', 'meeting', 'write', 'content', 'comms'],
            'productivity': ['organize', 'file', 'invoice', 'calendar', 'task', 'workflow', 'automate'],
            'research': ['research', 'search', 'web', 'scrape', 'extract'],
            'security': ['security', 'forensic', 'threat', 'vulnerability', 'audit'],
        }
        
        for category, keywords in categories.items():
            if any(kw in text for kw in keywords):
                return category
        
        return 'general'
    
    def load_index(self, force_refresh: bool = False) -> int:
        """Load or refresh the skill index from all registries."""
        self._ensure_cache_dir()
        
        cache_file = self.cache_dir / "external_index.json"
        
        # Check cache
        if not force_refresh and cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
                cache_time = datetime.fromisoformat(cache_data.get("updated", "2000-01-01T00:00:00Z").replace('Z', '+00:00'))
                
                # Cache valid for 24 hours
                if (datetime.now(timezone.utc) - cache_time).total_seconds() < 86400:
                    for skill_data in cache_data.get("skills", []):
                        skill = RemoteSkill(**skill_data)
                        self.skills[skill.name] = skill
                    self._index_loaded = True
                    return len(self.skills)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        
        # Try loading from bundled index first (fast, offline)
        bundled_loaded = self._load_bundled_index()
        
        # Try to refresh from registries (may fail if network blocked)
        if force_refresh or not bundled_loaded:
            for registry in sorted(self.registries, key=lambda r: r.get("priority", 99)):
                if registry["type"] == "github":
                    self._index_github_registry(registry)
        
        # Save cache if we got any skills
        if self.skills:
            self._save_cache(cache_file)
        
        self._index_loaded = True
        return len(self.skills)
    
    def _load_bundled_index(self) -> bool:
        """Load skills from bundled index file (for offline use)."""
        # Try multiple possible locations for the bundled index
        possible_paths = [
            Path(__file__).parent.parent / "references" / "awesome_claude_skills_index.json",
            Path(__file__).parent / "awesome_claude_skills_index.json",
            Path.home() / ".claude" / "skill-cache" / "awesome_claude_skills_index.json",
        ]
        
        for index_path in possible_paths:
            if index_path.exists():
                try:
                    index_data = json.loads(index_path.read_text())
                    for skill_data in index_data.get("skills", []):
                        # Handle both dict and dataclass formats
                        if isinstance(skill_data, dict):
                            skill = RemoteSkill(
                                name=skill_data.get("name", ""),
                                description=skill_data.get("description", ""),
                                source=skill_data.get("source", "awesome-claude-skills"),
                                url=skill_data.get("url", ""),
                                category=skill_data.get("category", "general"),
                                keywords=skill_data.get("keywords", []),
                                skill_md_url=skill_data.get("skill_md_url", ""),
                            )
                            self.skills[skill.name] = skill
                    return True
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Warning: Failed to load bundled index from {index_path}: {e}")
                    continue
        
        return False
    
    def _index_github_registry(self, registry: dict) -> int:
        """Index skills from a GitHub registry."""
        owner = registry["owner"]
        repo = registry["repo"]
        branch = registry.get("branch", "master")
        base_url = registry["url"]
        
        directories = self._parse_github_tree(owner, repo, branch)
        indexed = 0
        
        for dir_name in directories:
            # Skip common non-skill directories
            if dir_name in ['docs', 'examples', 'tests', '.github', 'scripts', 'assets']:
                continue
            
            # Try to fetch SKILL.md
            skill_content = self._fetch_skill_md(owner, repo, dir_name, branch)
            
            if skill_content:
                name, description = self._parse_skill_frontmatter(skill_content)
                
                if name:
                    skill = RemoteSkill(
                        name=name,
                        description=description or f"Skill from {registry['name']}",
                        source=registry["name"],
                        url=f"{base_url}/tree/{branch}/{dir_name}",
                        category=self._categorize(name, description or ""),
                        keywords=self._extract_keywords(f"{name} {description or ''}"),
                        skill_md_url=f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{dir_name}/SKILL.md"
                    )
                    
                    # Don't overwrite if already exists from higher priority source
                    if name not in self.skills:
                        self.skills[name] = skill
                        indexed += 1
        
        return indexed
    
    def _save_cache(self, cache_file: Path):
        """Save skill index to cache."""
        cache_data = {
            "version": "1.0",
            "updated": datetime.now(timezone.utc).isoformat() + "Z",
            "skill_count": len(self.skills),
            "skills": [skill.to_dict() for skill in self.skills.values()]
        }
        cache_file.write_text(json.dumps(cache_data, indent=2))
    
    def search(self, query: str, top_n: int = 10, threshold: float = 0.1) -> List[dict]:
        """Search for skills matching query."""
        if not self._index_loaded:
            self.load_index()
        
        query_tokens = set(re.findall(r'\b[a-z]{2,}\b', query.lower()))
        
        if not query_tokens:
            return []
        
        results = []
        
        for skill in self.skills.values():
            score = self._calculate_score(query_tokens, skill)
            if score >= threshold:
                results.append({
                    "name": skill.name,
                    "score": round(score, 3),
                    "description": skill.description[:200],
                    "category": skill.category,
                    "source": skill.source,
                    "url": skill.url,
                    "skill_md_url": skill.skill_md_url,
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]
    
    def _calculate_score(self, query_tokens: set, skill: RemoteSkill) -> float:
        """Calculate match score."""
        name_tokens = set(re.findall(r'\b[a-z]{2,}\b', skill.name.lower().replace('-', ' ')))
        desc_tokens = set(re.findall(r'\b[a-z]{2,}\b', skill.description.lower()))
        keyword_set = set(skill.keywords)
        
        # Weighted scoring
        name_overlap = len(query_tokens & name_tokens)
        desc_overlap = len(query_tokens & desc_tokens)
        keyword_overlap = len(query_tokens & keyword_set)
        
        name_score = name_overlap / max(len(name_tokens), 1) * 1.0
        desc_score = desc_overlap / max(len(query_tokens), 1) * 0.7
        keyword_score = keyword_overlap / max(len(query_tokens), 1) * 0.5
        
        # Exact name match bonus
        query_str = ' '.join(query_tokens)
        if skill.name.lower().replace('-', ' ') == query_str or skill.name.lower() in query_str:
            name_score = 1.0
        
        total = name_score + desc_score + keyword_score
        return min(total / 2.2, 1.0)  # Normalize to 0-1
    
    def get(self, name: str) -> Optional[RemoteSkill]:
        """Get a skill by exact name."""
        if not self._index_loaded:
            self.load_index()
        return self.skills.get(name)
    
    def list_skills(self, source: str = None, category: str = None) -> List[RemoteSkill]:
        """List all skills with optional filters."""
        if not self._index_loaded:
            self.load_index()
        
        skills = list(self.skills.values())
        
        if source:
            skills = [s for s in skills if s.source == source]
        if category:
            skills = [s for s in skills if s.category == category]
        
        return sorted(skills, key=lambda s: s.name)
    
    def add_registry(self, name: str, owner: str, repo: str, 
                     branch: str = "master", priority: int = 10):
        """Add a custom GitHub registry."""
        self.registries.append({
            "name": name,
            "type": "github",
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "url": f"https://github.com/{owner}/{repo}",
            "priority": priority,
        })
    
    def refresh(self) -> int:
        """Force refresh the index from all registries."""
        self.skills.clear()
        return self.load_index(force_refresh=True)


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Search external skill registries')
    parser.add_argument('query', nargs='?', help='Search query')
    parser.add_argument('--list', '-l', action='store_true', help='List all skills')
    parser.add_argument('--refresh', '-r', action='store_true', help='Force refresh cache')
    parser.add_argument('--source', '-s', help='Filter by source registry')
    parser.add_argument('--category', '-c', help='Filter by category')
    parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    registry = ExternalRegistry()
    
    if args.refresh:
        count = registry.refresh()
        print(f"Indexed {count} skills from external registries")
        return
    
    if args.list:
        skills = registry.list_skills(source=args.source, category=args.category)
        if args.json:
            print(json.dumps([s.to_dict() for s in skills], indent=2))
        else:
            for skill in skills:
                print(f"{skill.name:30} [{skill.source}] {skill.description[:50]}...")
        return
    
    if args.query:
        results = registry.search(args.query)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print(f"No skills found matching '{args.query}'")
            else:
                print(f"Found {len(results)} skills matching '{args.query}':\n")
                for r in results:
                    print(f"  {r['name']:25} (score: {r['score']:.2f})")
                    print(f"    {r['description'][:60]}...")
                    print(f"    Source: {r['source']} | URL: {r['url']}")
                    print()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
