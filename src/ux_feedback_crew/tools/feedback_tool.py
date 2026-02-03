from crewai.tools import tool
from google import genai
import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv


@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str) -> str:
    """
    Transforms heuristic violations into developer-friendly, actionable feedback using Gemini.
    
    Args:
        vision_analysis: JSON string of vision analysis
        heuristic_evaluation: JSON string of heuristic evaluation
        
    Returns:
        JSON string with actionable feedback, priorities, and implementation guidance
    """
    
    load_dotenv()
    
    # Configure Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    
    client = genai.Client(api_key=api_key)
    
    feedback_prompt = f"""
You are a developer-focused UX consultant. Transform these UX violations into clear, actionable feedback.

ORIGINAL UI ANALYSIS:
{vision_analysis}

IDENTIFIED VIOLATIONS:
{heuristic_evaluation}

TASK: Create developer-ready feedback for EACH violation.

For each issue:
1. **Action-oriented title** (e.g., "Add loading spinner to submit button")
2. **Priority**: P0 (critical), P1 (high), P2 (medium), P3 (low)
3. **Why it matters** - User impact in 1 sentence
4. **Implementation steps** - Specific, technical steps
5. **Wireframe instructions** - Visual changes needed
6. **Effort estimate** - quick-win (<2h), small (2-8h), medium (1-2d), large (3-5d)

Also identify QUICK WINS (P1/P2 + quick-win/small effort).

Return ONLY valid JSON (no markdown):

{{
  "feedback_items": [
    {{
      "id": 1,
      "title": "Add loading indicator to login button",
      "priority": "P1",
      "why_it_matters": "Users don't know if their tap registered, causing confusion and repeated taps",
      "implementation_steps": [
        "Wrap button in StatefulWidget to track loading state",
        "Add CircularProgressIndicator when isLoading==true",
        "Disable button during loading to prevent double-submission",
        "Show success checkmark or error icon after completion"
      ],
      "wireframe_instructions": "Show button in 3 states: normal, loading (with spinner), success/error",
      "effort_estimate": "small",
      "related_heuristic": "Visibility of system status",
      "affected_components": ["login button", "form submit"],
      "technical_notes": "Use Flutter's ElevatedButton with child: isLoading ? CircularProgressIndicator() : Text('Login')"
    }}
  ],
  "quick_wins": [
    {{
      "id": 3,
      "title": "Increase button touch targets to 48dp",
      "impact": "Prevents accidental mis-taps, improves accessibility",
      "effort": "quick-win",
      "priority": "P1"
    }}
  ],
  "summary": {{
    "total_issues": 8,
    "by_priority": {{
      "P0": 0,
      "P1": 3,
      "P2": 3,
      "P3": 2
    }},
    "by_effort": {{
      "quick-win": 2,
      "small": 4,
      "medium": 2,
      "large": 0
    }},
    "estimated_total_effort": "4-6 hours"
  }},
  "implementation_order": [
    "1. Quick wins: Fix contrast, touch targets, spacing (30 min)",
    "2. High priority: Add loading states, error handling (2-3 hours)",
    "3. Medium priority: Improve labels, add help text (1-2 hours)",
    "4. Low priority: Polish animations, refine visuals (1 hour)"
  ]
}}

GUIDELINES:
- Be specific (mention Flutter widgets, CSS properties, etc.)
- Explain WHY (user impact + business value)
- Think mobile-first (touch targets, screen size, performance)
- Realistic effort estimates
- Prioritize by: severity × ease of implementation

Generate comprehensive feedback now.
"""
    
    print("💬 Calling Gemini for feedback generation...")
    
    # Call Gemini
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=feedback_prompt
    )
    
    # Extract and clean JSON
    result_text = response.text.strip()
    
    # Remove markdown code blocks
    if result_text.startswith("```json"):
        result_text = result_text[7:]
    elif result_text.startswith("```"):
        result_text = result_text[3:]
    if result_text.endswith("```"):
        result_text = result_text[:-3]
    
    result_text = result_text.strip()
    
    # Validate JSON
    try:
        json_data = json.loads(result_text)
        
        # Save feedback
        output_dir = Path("data/outputs")
        output_dir.mkdir(exist_ok=True, parents=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON
        json_path = output_dir / f"feedback_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        # Save Markdown
        md_path = output_dir / f"feedback_{timestamp}.md"
        markdown_content = convert_feedback_to_markdown(json_data, timestamp)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"✓ Feedback JSON saved: {json_path}")
        print(f"✓ Feedback Markdown saved: {md_path}")
        print(f"✓ Total issues: {json_data.get('summary', {}).get('total_issues', 0)}")
        print(f"✓ Quick wins: {len(json_data.get('quick_wins', []))}")
        
    except json.JSONDecodeError as e:
        print(f"⚠ JSON validation error: {e}")
        output_path = output_dir / f"feedback_{timestamp}.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
    
    return result_text


def convert_feedback_to_markdown(feedback_data: dict, timestamp: str) -> str:
    """Convert feedback JSON to beautifully formatted Markdown"""
    
    md = f"""# 📋 UX Feedback Report

**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}  
**Report ID:** {timestamp}

---

"""
    
    # Summary Section
    if 'summary' in feedback_data:
        summary = feedback_data['summary']
        by_priority = summary.get('by_priority', {})
        md += f"""## 📊 Summary

| Metric | Count |
|--------|-------|
| **Total Issues** | {summary.get('total_issues', 0)} |
| **Critical (P0)** | 🔴 {by_priority.get('P0', 0)} |
| **High (P1)** | 🟠 {by_priority.get('P1', 0)} |
| **Medium (P2)** | 🟡 {by_priority.get('P2', 0)} |
| **Low (P3)** | 🟢 {by_priority.get('P3', 0)} |
| **Estimated Effort** | {summary.get('estimated_total_effort', 'N/A')} |

---

"""
    
    # Implementation Order
    if 'implementation_order' in feedback_data:
        md += "## 🎯 Recommended Implementation Order\n\n"
        for order_item in feedback_data['implementation_order']:
            md += f"{order_item}\n"
        md += "\n---\n\n"
    
    # Quick Wins
    if 'quick_wins' in feedback_data and feedback_data['quick_wins']:
        md += "## ⚡ Quick Wins\n\nEasy changes with high impact:\n\n"
        for win in feedback_data['quick_wins']:
            md += f"""### {win.get('title', 'Untitled')}

**Priority:** {win.get('priority', 'N/A')}  
**Effort:** ⏱️ {win.get('effort', 'N/A')}  
**Impact:** {win.get('impact', 'N/A')}

"""
        md += "---\n\n"
    
    # Detailed Feedback
    if 'feedback_items' in feedback_data:
        md += "## 📝 Detailed Feedback\n\n"
        for item in feedback_data['feedback_items']:
            priority = item.get('priority', 'P3')
            priority_emoji = {'P0': '🔴', 'P1': '🟠', 'P2': '🟡', 'P3': '🟢'}.get(priority, '⚪')
            
            md += f"""### {priority_emoji} {item.get('title', 'Untitled')}

**Priority:** {priority} | **Effort:** {item.get('effort_estimate', 'N/A')} | **Heuristic:** {item.get('related_heuristic', 'N/A')}

#### 💡 Why It Matters
{item.get('why_it_matters', 'N/A')}

#### ✅ Implementation Steps
"""
            for idx, step in enumerate(item.get('implementation_steps', []), 1):
                md += f"{idx}. {step}\n"
            
            md += f"\n#### 🎨 Wireframe Instructions\n{item.get('wireframe_instructions', 'N/A')}\n\n"
            
            if 'technical_notes' in item:
                md += f"#### 🔧 Technical Notes\n```\n{item['technical_notes']}\n```\n\n"
            
            md += "---\n\n"
    
    md += "\n*Generated by UX Feedback Crew*\n"
    
    return md