EXAMPLES = [
    {
        "name": "login_screen_feedback",
        "vision_analysis": """
{
  "screen_type": "login",
  "ui_summary": [
    "Email and password inputs are centered and clearly grouped",
    "Primary sign-in button is visible but supporting recovery action is weak",
    "No visible inline validation or error messaging is shown",
    "Secondary actions have lower visual prominence than expected"
  ]
}
""".strip(),
        "heuristic_evaluation": """
{
  "violations": [
    {
      "heuristic": "Visibility of system status",
      "issue": "There is no clear inline feedback for failed authentication or invalid field input.",
      "severity": 4,
      "suggestion": "Show visible inline validation and authentication error messages near the affected field."
    },
    {
      "heuristic": "User control and freedom",
      "issue": "Password recovery is not prominent enough for users who get blocked during sign in.",
      "severity": 3,
      "suggestion": "Increase the prominence of the forgot-password recovery path."
    },
    {
      "heuristic": "WCAG",
      "issue": "Secondary text and support actions are low in emphasis and may be missed on smaller screens.",
      "severity": 2,
      "suggestion": "Improve contrast and spacing for recovery-related text actions."
    }
  ]
}
""".strip(),
        "expected_output": """
{
  "feedback_items": [
    {
      "title": "Make authentication errors immediately visible",
      "priority": "high",
      "effort_estimate": "medium",
      "why_it_matters": "When users do not understand why sign in failed, they are likely to repeat the same action, lose confidence, and abandon the task.",
      "what_to_do": [
        "Show inline error messages directly below the relevant input field",
        "Highlight the affected field border when validation fails",
        "Use clear human-readable messages such as 'Incorrect password' instead of vague failure text"
      ],
      "wireframe_changes": "Add an inline error label below the password field and show an error state on the field border."
    },
    {
      "title": "Strengthen the password recovery path",
      "priority": "medium",
      "effort_estimate": "low",
      "why_it_matters": "Users who forget credentials need a fast recovery option or they may drop out of the flow entirely.",
      "what_to_do": [
        "Increase the visibility of the forgot-password action",
        "Place it closer to the password field",
        "Use clearer spacing and contrast so it is easy to notice"
      ],
      "wireframe_changes": "Move the forgot-password link directly below the password input with stronger text contrast and spacing."
    }
  ],
  "ux_score": {
    "score": 6.8,
    "grade": "C"
  },
  "summary": {
    "total_issues": 2,
    "high": 1,
    "medium": 1,
    "low": 0
  }
}
""".strip(),
    },
    {
        "name": "dashboard_screen_feedback",
        "vision_analysis": """
{
  "screen_type": "dashboard",
  "ui_summary": [
    "The dashboard shows wallet cards, charts, and transaction content in one dense view",
    "Multiple sections compete for attention on first load",
    "Wallet selection state is not visually strong enough",
    "Graph information lacks immediate readability"
  ]
}
""".strip(),
        "heuristic_evaluation": """
{
  "violations": [
    {
      "heuristic": "Aesthetic and minimalist design",
      "issue": "The screen is visually dense and presents too many competing blocks of information in one fold.",
      "severity": 3,
      "suggestion": "Use progressive disclosure and reduce first-screen cognitive load."
    },
    {
      "heuristic": "Flexibility and efficiency of use",
      "issue": "The spending chart lacks clear labeling, which makes trend reading inefficient.",
      "severity": 2,
      "suggestion": "Add axis labels, clearer legends, and time-range controls."
    },
    {
      "heuristic": "Visibility of system status",
      "issue": "The active wallet is not clearly distinguished from inactive wallets.",
      "severity": 2,
      "suggestion": "Strengthen the selected wallet state visually and confirm updates in the chart."
    }
  ]
}
""".strip(),
        "expected_output": """
{
  "feedback_items": [
    {
      "title": "Reduce dashboard density to improve scannability",
      "priority": "high",
      "effort_estimate": "high",
      "why_it_matters": "When too many information blocks compete at once, users need more effort to locate key financial information and decide what to do next.",
      "what_to_do": [
        "Prioritize the most important metrics at the top of the screen",
        "Move secondary analytics into tabs, collapsible sections, or a lower screen area",
        "Use stronger spacing and grouping so each section feels distinct"
      ],
      "wireframe_changes": "Keep total balance and primary wallet cards in the first section, and move detailed analytics and transaction history into separated sections below."
    },
    {
      "title": "Make the active wallet state obvious",
      "priority": "medium",
      "effort_estimate": "low",
      "why_it_matters": "Users need to know which account is currently driving the chart and summary data to trust what they are seeing.",
      "what_to_do": [
        "Use a stronger selected state on the active wallet card",
        "Apply a clear border, highlight, or check indicator",
        "Visually confirm chart updates when a different wallet is selected"
      ],
      "wireframe_changes": "Add a distinct selected border and subtle highlight to the active wallet card, with a brief chart transition when selection changes."
    },
    {
      "title": "Improve chart readability for faster interpretation",
      "priority": "medium",
      "effort_estimate": "medium",
      "why_it_matters": "Unlabeled chart data slows down interpretation and makes the analytics feel less trustworthy.",
      "what_to_do": [
        "Add visible X-axis and Y-axis labels",
        "Include clear value references such as currency markers",
        "Provide a simple control to switch between daily, weekly, and monthly views"
      ],
      "wireframe_changes": "Add chart axes and place a compact time-range toggle above the graph."
    }
  ],
  "ux_score": {
    "score": 6.4,
    "grade": "C"
  },
  "summary": {
    "total_issues": 3,
    "high": 1,
    "medium": 2,
    "low": 0
  }
}
""".strip(),
    },
    {
        "name": "cart_screen_feedback",
        "vision_analysis": """
{
  "screen_type": "cart",
  "ui_summary": [
    "The cart includes quantity controls, remove actions, and a checkout CTA",
    "High-frequency controls appear visually small",
    "The screen supports editing items but some actions can be triggered accidentally",
    "Checkout is visible but readiness information is incomplete"
  ]
}
""".strip(),
        "heuristic_evaluation": """
{
  "violations": [
    {
      "heuristic": "User control and freedom",
      "issue": "The remove action is too close to quantity controls and may cause accidental deletion.",
      "severity": 3,
      "suggestion": "Add an undo option or confirmation for destructive actions."
    },
    {
      "heuristic": "WCAG",
      "issue": "The quantity stepper icons and remove icon are too small for comfortable mobile tapping.",
      "severity": 3,
      "suggestion": "Increase icon size and ensure touch targets are at least 44 by 44 pixels."
    },
    {
      "heuristic": "Visibility of system status",
      "issue": "Users are not shown enough order-readiness information such as delivery or payment context near checkout.",
      "severity": 2,
      "suggestion": "Show a concise order readiness summary near the checkout action."
    }
  ]
}
""".strip(),
        "expected_output": """
{
  "feedback_items": [
    {
      "title": "Prevent accidental item deletion in the cart",
      "priority": "high",
      "effort_estimate": "medium",
      "why_it_matters": "Destructive actions placed too close to frequent controls create frustration and can interrupt checkout momentum.",
      "what_to_do": [
        "Separate the remove action from the quantity controls",
        "Add an undo snackbar after deletion or a lightweight confirmation for destructive actions",
        "Use clearer spacing so the delete action is less likely to be tapped by mistake"
      ],
      "wireframe_changes": "Move the remove control farther from the quantity stepper and show an undo snackbar after an item is removed."
    },
    {
      "title": "Increase tap target size for cart actions",
      "priority": "high",
      "effort_estimate": "low",
      "why_it_matters": "Small controls are harder to tap accurately on mobile and increase error rate during high-frequency interactions.",
      "what_to_do": [
        "Increase the size of quantity and remove controls",
        "Ensure each interactive target is at least 44 by 44 pixels",
        "Use stronger icon weight so the actions are easier to recognize"
      ],
      "wireframe_changes": "Enlarge the plus, minus, and remove controls and provide more padding around each tap target."
    },
    {
      "title": "Show order-readiness details near checkout",
      "priority": "medium",
      "effort_estimate": "low",
      "why_it_matters": "Users feel more confident proceeding when they can quickly confirm key order details before tapping checkout.",
      "what_to_do": [
        "Add a short delivery or payment summary near the checkout button",
        "Keep the summary concise and easy to scan",
        "Use it to reinforce that the order is ready to proceed"
      ],
      "wireframe_changes": "Place a small summary row above the checkout button showing delivery or payment context."
    }
  ],
  "ux_score": {
    "score": 6.1,
    "grade": "C"
  },
  "summary": {
    "total_issues": 3,
    "high": 2,
    "medium": 1,
    "low": 0
  }
}
""".strip(),
    },
]