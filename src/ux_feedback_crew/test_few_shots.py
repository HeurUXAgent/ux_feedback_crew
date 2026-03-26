from dotenv import load_dotenv
load_dotenv()

from src.ux_feedback_crew.tools.feedback_tool_fewshot import generate_feedback_fewshot


def main():
    vision = """
{
  "screen_type": "login",
  "ui_summary": [
    "Email and password fields are visible",
    "Primary login button has weak contrast",
    "Forgot password action is easy to miss",
    "No visible inline validation is shown"
  ]
}
""".strip()

    heuristics = """
{
  "violations": [
    {
      "heuristic": "Visibility of system status",
      "issue": "No inline error feedback is shown when login fails.",
      "severity": 4,
      "suggestion": "Show inline error messaging near the affected field."
    },
    {
      "heuristic": "User control and freedom",
      "issue": "Forgot password is not visually prominent enough.",
      "severity": 3,
      "suggestion": "Make the recovery action easier to notice."
    },
    {
      "heuristic": "WCAG",
      "issue": "The primary button contrast is weak.",
      "severity": 3,
      "suggestion": "Increase color contrast for the main CTA."
    }
  ]
}
""".strip()

    result = generate_feedback_fewshot.run(
        vision_analysis=vision,
        heuristic_evaluation=heuristics,
        evaluation_id="fewshot_test"
    )

    print("\n===== FEW-SHOT RESULT =====\n")
    print(result)


if __name__ == "__main__":
    main()