from crewai.tools import tool
import json
from pathlib import Path
from datetime import datetime

from crewai.tools import tool
from pathlib import Path
from datetime import datetime
import json


@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str) -> str:
    """
    Prepares developer-friendly feedback generation prompt for the agent.
    The agent will process this and return JSON feedback.
    
    Args:
        vision_analysis: JSON string of vision analysis
        heuristic_evaluation: JSON string of heuristic evaluation
        
    Returns:
        Structured prompt for agent to generate actionable feedback
    """
    
    feedback_prompt = f"""
TASK: Transform UX violations into developer-friendly, actionable feedback

## VISION ANALYSIS:
{vision_analysis}

## HEURISTIC EVALUATION:
{heuristic_evaluation}

## FEEDBACK GENERATION INSTRUCTIONS:

Convert each violation into clear, actionable feedback that developers can implement.

For each issue, create feedback that includes:
1. **Action-oriented title** - What to do (e.g., "Add loading spinner to submit button")
2. **Priority** - Based on severity and user impact
3. **Why it matters** - User impact in simple terms
4. **What to do** - Step-by-step implementation guide
5. **Wireframe changes** - Visual changes to make
6. **Effort estimate** - Time/complexity estimate

Also identify **QUICK WINS** - easy changes with high impact.

## OUTPUT FORMAT:

Return ONLY valid JSON:

{{
  "feedback_items": [
    {{
      "id": 1,
      "title": "Add loading indicator to login button",
      "priority": "high",
      "why_it_matters": "Users don't know if their tap registered or if the app is processing. This causes repeated taps and frustration.",
      "what_to_do": [
        "Add a CircularProgressIndicator widget to the button when tapped",
        "Disable the button while loading to prevent multiple submissions",
        "Show success/error state after completion"
      ],
      "wireframe_changes": "Show button in three states: default, loading (with spinner), and success/error",
      "effort_estimate": "Small (30 minutes)",
      "related_heuristic": "Visibility of system status"
    }}
  ],
  "quick_wins": [
    {{
      "change": "Increase button touch targets to 48dp minimum",
      "impact": "Easier tapping, fewer accidental misses",
      "effort": "10 minutes",
      "priority": "high"
    }}
  ],
  "summary": {{
    "total_issues": 8,
    "high": 3,
    "medium": 3,
    "low": 2,
    "estimated_total_effort": "4-6 hours"
  }},
  "implementation_order": [
    "1. Fix high-priority accessibility issues (contrast, touch targets)",
    "2. Add loading/feedback indicators",
    "3. Improve error handling and messages",
    "4. Refine visual polish and spacing"
  ]
}}

## WRITING GUIDELINES:
- Use developer-friendly language (mention Flutter widgets, CSS properties, etc.)
- Be specific and concrete
- Explain WHY changes matter (user impact + business value)
- Provide realistic effort estimates
- Think about mobile constraints (screen size, touch, performance)
- Prioritize based on: user impact × ease of implementation

Generate comprehensive, actionable feedback now.
"""
    
    print("✓ Feedback generation prompt prepared")
    
    return feedback_prompt


@tool("save_feedback_report")
def save_feedback_report(feedback_json: str) -> str:
    """
    Saves the feedback report to both JSON and Markdown formats.
    Call this tool after generating feedback to persist the results.
    
    Args:
        feedback_json: JSON string containing the feedback data
        
    Returns:
        Confirmation message with file paths
    """
    
    output_dir = Path("data/outputs")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        # Parse and validate JSON
        feedback_data = json.loads(feedback_json)
        
        # Save JSON version
        json_path = output_dir / f"feedback_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(feedback_data, f, indent=2, ensure_ascii=False)
        
        # Convert to Markdown
        md_path = output_dir / f"feedback_{timestamp}.md"
        markdown_content = convert_feedback_to_markdown(feedback_data, timestamp)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"✓ Feedback JSON saved to: {json_path}")
        print(f"✓ Feedback Markdown saved to: {md_path}")
        
        return f"""Feedback report saved successfully:
- JSON: {json_path}
- Markdown: {md_path}

The markdown report is ready for developers to review."""
        
    except json.JSONDecodeError as e:
        print(f"⚠ JSON parsing error: {e}")
        
        # Save as raw text if JSON is invalid
        txt_path = output_dir / f"feedback_{timestamp}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(feedback_json)
        
        return f"⚠ Could not parse JSON. Feedback saved as text: {txt_path}"


def convert_feedback_to_markdown(feedback_data: dict, timestamp: str) -> str:
    """
    Convert feedback JSON to beautifully formatted Markdown
    
    Args:
        feedback_data: Dictionary containing feedback information
        timestamp: Timestamp string for the report
        
    Returns:
        Formatted markdown string
    """
    
    md = f"""# 📋 UX Feedback Report

**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}  
**Report ID:** {timestamp}

---

"""
    
    # Summary Section
    if 'summary' in feedback_data:
        summary = feedback_data['summary']
        md += f"""## 📊 Summary

| Metric | Count |
|--------|-------|
| **Total Issues** | {summary.get('total_issues', 0)} |
| **High Priority** | 🔴 {summary.get('high', 0)} |
| **Medium Priority** | 🟡 {summary.get('medium', 0)} |
| **Low Priority** | 🟢 {summary.get('low', 0)} |
| **Estimated Effort** | {summary.get('estimated_total_effort', 'N/A')} |

---

"""
    
    # Implementation Order
    if 'implementation_order' in feedback_data and feedback_data['implementation_order']:
        md += f"""## 🎯 Recommended Implementation Order

"""
        for order_item in feedback_data['implementation_order']:
            md += f"{order_item}\n"
        md += "\n---\n\n"
    
    # Quick Wins Section
    if 'quick_wins' in feedback_data and feedback_data['quick_wins']:
        md += f"""## ⚡ Quick Wins

These are easy changes that will have immediate positive impact:

"""
        for idx, win in enumerate(feedback_data['quick_wins'], 1):
            priority_badge = {
                'high': '🔴 HIGH',
                'medium': '🟡 MEDIUM', 
                'low': '🟢 LOW'
            }.get(win.get('priority', 'low'), '⚪ UNKNOWN')
            
            md += f"""### {idx}. {win.get('change', 'Untitled')}

**Priority:** {priority_badge}  
**Effort:** ⏱️ {win.get('effort', 'N/A')}  
**Impact:** {win.get('impact', 'N/A')}

"""
        md += "---\n\n"
    
    # Detailed Feedback Items
    if 'feedback_items' in feedback_data and feedback_data['feedback_items']:
        md += f"""## 📝 Detailed Feedback Items

"""
        for item in feedback_data['feedback_items']:
            priority = item.get('priority', 'low').lower()
            priority_emoji = {
                'high': '🔴',
                'medium': '🟡',
                'low': '🟢'
            }.get(priority, '⚪')
            
            priority_badge = {
                'high': '🔴 **HIGH PRIORITY**',
                'medium': '🟡 **MEDIUM PRIORITY**',
                'low': '🟢 **LOW PRIORITY**'
            }.get(priority, '⚪ UNKNOWN')
            
            md += f"""### {priority_emoji} {item.get('title', 'Untitled Issue')}

**Priority:** {priority_badge}  
"""
            
            if 'related_heuristic' in item:
                md += f"**Related Heuristic:** {item['related_heuristic']}  \n"
            
            if 'effort_estimate' in item:
                md += f"**Effort Estimate:** ⏱️ {item['effort_estimate']}  \n"
            
            md += "\n"
            
            # Why it matters
            if 'why_it_matters' in item:
                md += f"""#### 💡 Why It Matters

{item['why_it_matters']}

"""
            
            # What to do
            if 'what_to_do' in item and item['what_to_do']:
                md += f"""#### ✅ What To Do

"""
                for step_idx, step in enumerate(item['what_to_do'], 1):
                    md += f"{step_idx}. {step}\n"
                md += "\n"
            
            # Wireframe changes
            if 'wireframe_changes' in item:
                md += f"""#### 🎨 Wireframe Changes

{item['wireframe_changes']}

"""
            
            md += "---\n\n"
    
    # Footer
    md += f"""
---

## 📌 Notes

- This report was automatically generated based on heuristic evaluation
- Priorities are based on user impact and usability severity
- Effort estimates are approximate and may vary based on your codebase
- Focus on high-priority items first for maximum user experience improvement

**Need help implementing these changes?** Refer to the wireframe for visual examples.

---

*Generated by UX Feedback Crew v1.0*
"""
    
    return md


