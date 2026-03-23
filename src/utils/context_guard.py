import json

# Hard context limit safeguard
MAX_CONTEXT_CHARS = 12000


def truncate_text(text: str, limit: int = MAX_CONTEXT_CHARS) -> str:
    """Hard truncate text to prevent large context errors."""
    if len(text) > limit:
        return text[:limit] + "\n\n[TRUNCATED]"
    return text


def compress_vision(data: dict) -> dict:
    """Reduce vision JSON to essential fields."""
    return {
        "screen_type": data.get("screen_type"),
        "components": [c.get("type") for c in data.get("components", [])][:15],
        "layout_structure": data.get("layout_structure"),
        "notable_patterns": data.get("notable_patterns", [])[:10],
        "accessibility_observations": data.get("accessibility_observations", [])[:8]
    }


def compress_heuristics(data: dict) -> dict:
    """Reduce heuristic JSON size."""
    return {
        "violations": data.get("violations", [])[:6],
        "strengths": data.get("strengths", [])[:6],
        "overall_score": data.get("overall_score"),
        "summary": data.get("summary")
    }


def safe_json_string(data: dict) -> str:
    """Convert JSON safely while keeping size small."""
    return truncate_text(json.dumps(data))