#!/usr/bin/env python3
"""
Unified Skill Search - Search both local and external skill registries.

This is the main entry point for skill discovery. It:
1. Searches local skill directories first
2. Falls back to external registries (awesome-claude-skills, etc.)
3. Provides installation commands for remote skills

Usage:
    python unified_search.py "invoice organizer"
    python unified_search.py --query "pdf creation" --include-external
    python unified_search.py --list-sources
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Import local modules
try:
    from skill_registry import SkillRegistry
    from external_registry import ExternalRegistry
except ImportError:
    # Handle case where running from different directory
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from skill_registry import SkillRegistry
    from external_registry import ExternalRegistry


class UnifiedSkillSearch:
    """Unified search across local and external skill registries."""
    
    # Default local paths to scan
    DEFAULT_LOCAL_PATHS = [
        "/mnt/skills/public",
        "/mnt/skills/user", 
        "/mnt/skills/examples",
        "~/.claude/skills",
        ".claude/skills",
    ]
    
    def __init__(self, 
                 local_paths: List[str] = None,
                 include_external: bool = True,
                 cache_dir: str = None):
        """
        Initialize unified search.
        
        Args:
            local_paths: Paths to scan for local skills
            include_external: Whether to search external registries
            cache_dir: Directory for caching external registry data
        """
        self.local_paths = local_paths or self.DEFAULT_LOCAL_PATHS
        self.include_external = include_external
        
        # Initialize registries
        self.local_registry = SkillRegistry()
        self.external_registry = ExternalRegistry(cache_dir) if include_external else None
        
        self._local_scanned = False
        self._external_loaded = False
    
    def _ensure_local_scanned(self):
        """Ensure local directories have been scanned."""
        if not self._local_scanned:
            for path in self.local_paths:
                expanded = Path(path).expanduser()
                if expanded.exists():
                    self.local_registry.scan(expanded)
            self._local_scanned = True
    
    def _ensure_external_loaded(self):
        """Ensure external registry is loaded."""
        if self.external_registry and not self._external_loaded:
            self.external_registry.load_index()
            self._external_loaded = True
    
    def search(self, 
               query: str, 
               top_n: int = 10,
               local_only: bool = False,
               external_only: bool = False) -> Dict[str, List[dict]]:
        """
        Search for skills matching query.
        
        Args:
            query: Search query
            top_n: Maximum results per source
            local_only: Only search local skills
            external_only: Only search external skills
            
        Returns:
            Dict with 'local' and 'external' result lists
        """
        results = {
            "query": query,
            "local": [],
            "external": [],
        }
        
        # Search local
        if not external_only:
            self._ensure_local_scanned()
            local_results = self.local_registry.search(query, top_n=top_n)
            results["local"] = local_results
        
        # Search external
        if not local_only and self.include_external:
            self._ensure_external_loaded()
            external_results = self.external_registry.search(query, top_n=top_n)
            results["external"] = external_results
        
        return results
    
    def get(self, name: str) -> Optional[dict]:
        """
        Get a skill by exact name from any source.
        
        Args:
            name: Skill name
            
        Returns:
            Skill info dict with 'source' field indicating origin
        """
        # Check local first
        self._ensure_local_scanned()
        local_skill = self.local_registry.get(name)
        if local_skill:
            return {**local_skill, "source": "local", "installed": True}
        
        # Check external
        if self.include_external:
            self._ensure_external_loaded()
            external_skill = self.external_registry.get(name)
            if external_skill:
                return {
                    **external_skill.to_dict(),
                    "installed": False,
                    "install_command": self._get_install_command(external_skill),
                }
        
        return None
    
    def _get_install_command(self, skill) -> str:
        """Generate installation command for external skill."""
        if hasattr(skill, 'skill_md_url') and skill.skill_md_url:
            return f"# Download to ~/.claude/skills/{skill.name}/\ncurl -sL {skill.skill_md_url} -o ~/.claude/skills/{skill.name}/SKILL.md --create-dirs"
        return f"# Visit: {skill.url}"
    
    def list_sources(self) -> dict:
        """List all available skill sources."""
        sources = {
            "local_paths": [],
            "external_registries": [],
        }
        
        # Local paths
        for path in self.local_paths:
            expanded = Path(path).expanduser()
            sources["local_paths"].append({
                "path": str(expanded),
                "exists": expanded.exists(),
                "skill_count": len(list(expanded.glob("*/SKILL.md"))) if expanded.exists() else 0,
            })
        
        # External registries
        if self.external_registry:
            for reg in self.external_registry.registries:
                sources["external_registries"].append({
                    "name": reg["name"],
                    "url": reg["url"],
                    "type": reg["type"],
                })
        
        return sources
    
    def refresh_external(self) -> int:
        """Force refresh external registry cache."""
        if self.external_registry:
            return self.external_registry.refresh()
        return 0
    
    def recommend(self, query: str) -> dict:
        """
        Recommend the best skill for a query.
        
        Returns recommendation with confidence score and alternatives.
        """
        results = self.search(query, top_n=5)
        
        # Combine and score
        all_results = []
        
        for r in results["local"]:
            all_results.append({**r, "source": "local", "installed": True})
        
        for r in results["external"]:
            all_results.append({**r, "installed": False})
        
        # Sort by score
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        if not all_results:
            return {
                "recommended": False,
                "confidence": 0,
                "message": f"No skills found matching '{query}'",
            }
        
        best = all_results[0]
        
        return {
            "recommended": True,
            "skill": best["name"],
            "confidence": best.get("score", 0),
            "installed": best.get("installed", False),
            "source": best.get("source", "external"),
            "url": best.get("url", best.get("path", "")),
            "description": best.get("description", ""),
            "alternatives": [r["name"] for r in all_results[1:4]],
            "install_command": self._get_install_command_from_result(best) if not best.get("installed") else None,
        }
    
    def _get_install_command_from_result(self, result: dict) -> str:
        """Generate install command from result dict."""
        skill_md_url = result.get("skill_md_url", "")
        if skill_md_url:
            return f"curl -sL {skill_md_url} -o ~/.claude/skills/{result['name']}/SKILL.md --create-dirs"
        return f"# Visit: {result.get('url', 'N/A')}"


def format_results(results: dict, verbose: bool = False) -> str:
    """Format search results for display."""
    lines = []
    
    query = results.get("query", "")
    local = results.get("local", [])
    external = results.get("external", [])
    
    total = len(local) + len(external)
    
    if total == 0:
        return f"No skills found matching '{query}'"
    
    lines.append(f"Found {total} skills matching '{query}':")
    lines.append("")
    
    if local:
        lines.append("📁 LOCAL SKILLS (installed):")
        lines.append("-" * 40)
        for r in local:
            lines.append(f"  {r['name']:25} (score: {r['score']:.2f})")
            if verbose:
                lines.append(f"    {r.get('description', '')[:60]}...")
                lines.append(f"    Path: {r.get('path', 'N/A')}")
        lines.append("")
    
    if external:
        lines.append("🌐 EXTERNAL SKILLS (available to install):")
        lines.append("-" * 40)
        for r in external:
            lines.append(f"  {r['name']:25} (score: {r['score']:.2f})")
            if verbose:
                lines.append(f"    {r.get('description', '')[:60]}...")
                lines.append(f"    Source: {r.get('source', 'N/A')}")
                lines.append(f"    URL: {r.get('url', 'N/A')}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Search for Claude skills across local and external registries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python unified_search.py "invoice organizer"
  python unified_search.py --query "pdf" --local-only
  python unified_search.py --list-sources
  python unified_search.py --refresh
  python unified_search.py --get invoice-organizer
        """
    )
    
    parser.add_argument('query', nargs='?', help='Search query')
    parser.add_argument('--query', '-q', dest='query_flag', help='Search query (alternative)')
    parser.add_argument('--get', '-g', help='Get specific skill by name')
    parser.add_argument('--recommend', '-r', help='Get recommendation for task')
    parser.add_argument('--local-only', '-l', action='store_true', help='Only search local skills')
    parser.add_argument('--external-only', '-e', action='store_true', help='Only search external skills')
    parser.add_argument('--list-sources', action='store_true', help='List all skill sources')
    parser.add_argument('--refresh', action='store_true', help='Refresh external registry cache')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    parser.add_argument('--top', '-n', type=int, default=10, help='Max results (default: 10)')
    
    args = parser.parse_args()
    
    search = UnifiedSkillSearch()
    
    # Handle list-sources
    if args.list_sources:
        sources = search.list_sources()
        if args.json:
            print(json.dumps(sources, indent=2))
        else:
            print("Skill Sources:")
            print("=" * 50)
            print("\n📁 Local Paths:")
            for p in sources["local_paths"]:
                status = "✓" if p["exists"] else "✗"
                count = f"({p['skill_count']} skills)" if p["exists"] else "(not found)"
                print(f"  {status} {p['path']} {count}")
            
            print("\n🌐 External Registries:")
            for r in sources["external_registries"]:
                print(f"  • {r['name']}: {r['url']}")
        return
    
    # Handle refresh
    if args.refresh:
        count = search.refresh_external()
        print(f"Refreshed external registry: {count} skills indexed")
        return
    
    # Handle get
    if args.get:
        skill = search.get(args.get)
        if args.json:
            print(json.dumps(skill, indent=2) if skill else json.dumps({"error": "Not found"}))
        else:
            if skill:
                print(f"Skill: {skill['name']}")
                print(f"Description: {skill.get('description', 'N/A')}")
                print(f"Source: {skill.get('source', 'N/A')}")
                print(f"Installed: {'Yes' if skill.get('installed') else 'No'}")
                if skill.get('url'):
                    print(f"URL: {skill['url']}")
                if skill.get('install_command'):
                    print(f"\nInstall command:\n{skill['install_command']}")
            else:
                print(f"Skill '{args.get}' not found")
        return
    
    # Handle recommend
    if args.recommend:
        rec = search.recommend(args.recommend)
        if args.json:
            print(json.dumps(rec, indent=2))
        else:
            if rec["recommended"]:
                print(f"✓ Recommended: {rec['skill']} (confidence: {rec['confidence']:.2f})")
                print(f"  {rec['description'][:80]}...")
                print(f"  Installed: {'Yes' if rec['installed'] else 'No'}")
                if rec.get('install_command'):
                    print(f"\n  Install:\n  {rec['install_command']}")
                if rec['alternatives']:
                    print(f"\n  Alternatives: {', '.join(rec['alternatives'])}")
            else:
                print(rec["message"])
        return
    
    # Handle search
    query = args.query or args.query_flag
    if query:
        results = search.search(
            query,
            top_n=args.top,
            local_only=args.local_only,
            external_only=args.external_only
        )
        
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(format_results(results, verbose=args.verbose))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
