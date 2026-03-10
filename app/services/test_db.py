"""
test_db.py

Simulates the exact pipeline payload and tests MongoDB schema.
Run from project root: python app/services/test_db.py
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

import uuid
from datetime import datetime, timezone
from app.services.database import (
    create_evaluation_document,
    complete_evaluation,
    fail_evaluation,
    save_hitl_response,
    get_evaluation,
    get_user_evaluations,
)

# ─── Fake Data ────────────────────────────────────────────────────────────────

FAKE_EVALUATION_ID = str(uuid.uuid4())
FAKE_USER_ID       = "firebase_uid_test_123"
FAKE_IMAGE_URL     = "https://s3.amazonaws.com/heuruxagent/test-ui.png"

# Simulates raw text output from each CrewAI agent
class FakeTaskOutput:
    def __init__(self, raw: str):
        self.raw = raw

FAKE_TASKS_OUTPUT = [
    FakeTaskOutput("""
        The UI appears to be a login screen. It contains an email input field,
        a password field, a sign in button, and a Google sign in option.
        The background is light grey with a blue gradient panel on the left.
        Text contrast appears low in some areas. The button color is blue.
        Overall layout follows standard login screen conventions.
    """),

    FakeTaskOutput("""
        Heuristic Evaluation Results:
        
        1. Visibility of System Status - Score: 6/10
        The system does not provide clear feedback when login fails.
        
        2. Consistency and Standards - Score: 7/10
        Follows platform conventions reasonably well.
        
        3. Error Prevention - Score: 5/10
        No inline validation before form submission.
        
        4. Accessibility (WCAG) - Score: 4/10
        Low contrast on placeholder text. Fails WCAG AA standard.
        
        5. Recognition over Recall - Score: 8/10
        Labels are visible and clear.
        
        6. Aesthetic and Minimalist Design - Score: 7/10
        Clean layout with minimal clutter.
    """),

    FakeTaskOutput("""
        Feedback Report:
        
        Issues Detected:
        - Low contrast on placeholder text fails WCAG 2.1 AA (contrast ratio < 3:1)
        - No inline form validation before submission
        - Missing password visibility toggle
        - Error messages not descriptive enough
        - Button lacks focus state for keyboard navigation
        
        Suggestions:
        - Increase placeholder text contrast to minimum 4.5:1
        - Add real-time inline validation on email and password fields
        - Add password visibility toggle icon inside password field
        - Provide specific error messages (e.g. 'Incorrect password' vs 'Login failed')
        - Add visible focus ring on interactive elements for accessibility
    """),

    FakeTaskOutput("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Improved Login UI</title>
            <style>
                body { font-family: Arial, sans-serif; background: #F4F6FB; }
                .container { max-width: 400px; margin: 80px auto; padding: 40px; background: white; border-radius: 12px; }
                input { width: 100%; padding: 12px; border: 1.5px solid #E0E4EF; border-radius: 8px; font-size: 14px; }
                button { width: 100%; padding: 14px; background: #3D5AFE; color: white; border: none; border-radius: 8px; font-size: 15px; cursor: pointer; }
                button:focus { outline: 3px solid #A0AEFF; }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Welcome back</h2>
                <input type="email" placeholder="you@example.com" aria-label="Email" />
                <input type="password" placeholder="Password" aria-label="Password" />
                <button type="submit">Sign In</button>
            </div>
        </body>
        </html>
    """),
]


# ─── Test Functions ───────────────────────────────────────────────────────────

def test_create_document():
    print("\n─── TEST 1: Create evaluation document (status: processing) ───")
    result = create_evaluation_document(
        evaluation_id=FAKE_EVALUATION_ID,
        user_id=FAKE_USER_ID,
        screenshot_url=FAKE_IMAGE_URL,
    )
    assert result, "create_evaluation_document returned False"

    doc = get_evaluation(FAKE_EVALUATION_ID)
    assert doc is not None, "Document not found after insert"
    assert doc["status"] == "processing", f"Expected 'processing', got {doc['status']}"
    assert doc["evaluation_id"] == FAKE_EVALUATION_ID
    assert doc["user_id"] == FAKE_USER_ID
    assert doc["input"]["screenshot_url"] == FAKE_IMAGE_URL
    assert doc["input"]["screen_type"] == "unknown"
    assert doc["ai_results"] is None
    assert doc["hitl_feedback"]["review_status"] == "pending"
    assert doc["hitl_feedback"]["responses"] == []

    print("✅ Document created correctly with status: processing")
    print(f"   evaluation_id : {doc['evaluation_id']}")
    print(f"   user_id       : {doc['user_id']}")
    print(f"   status        : {doc['status']}")
    print(f"   screen_type   : {doc['input']['screen_type']}")


def test_complete_evaluation():
    print("\n─── TEST 2: Complete evaluation with agent outputs ───")
    result = complete_evaluation(
        evaluation_id=FAKE_EVALUATION_ID,
        tasks_output=FAKE_TASKS_OUTPUT,
        pipeline_duration_seconds=47.32,
    )
    assert result, "complete_evaluation returned False"

    doc = get_evaluation(FAKE_EVALUATION_ID)
    assert doc["status"] == "completed", f"Expected 'completed', got {doc['status']}"
    assert doc["ai_results"] is not None, "ai_results is None after completion"

    # Check screen type detection
    print(f"   screen_type detected : {doc['input']['screen_type']}")
    assert doc["input"]["screen_type"] == "login", f"Expected 'login', got {doc['input']['screen_type']}"

    # Check heuristic scores
    scores = doc["ai_results"]["heuristic_evaluation"]["scores"]
    print(f"   heuristic scores     : {scores}")
    assert isinstance(scores, dict), "Scores should be a dict"

    # Check feedback parsing
    issues = doc["ai_results"]["feedback_report"]["issues_detected"]
    suggestions = doc["ai_results"]["feedback_report"]["suggestions"]
    print(f"   issues detected      : {len(issues)} items")
    print(f"   suggestions          : {len(suggestions)} items")
    assert len(issues) > 0, "No issues parsed from feedback report"
    assert len(suggestions) > 0, "No suggestions parsed from feedback report"

    # Check UX score
    ux_score = doc["ai_results"]["ux_score"]
    print(f"   ux_score             : {ux_score}")

    # Check wireframe
    html = doc["ai_results"]["improved_design"]["html_code"]
    assert "<html" in html.lower(), "Wireframe HTML not stored correctly"
    print(f"   wireframe html       : ✅ stored ({len(html)} chars)")

    # Check timestamps
    assert doc["timestamps"]["completed_at"] is not None
    assert doc["timestamps"]["pipeline_duration_seconds"] == 47.32
    print(f"   pipeline duration    : {doc['timestamps']['pipeline_duration_seconds']}s")

    print("✅ Evaluation completed and all fields populated correctly")


def test_hitl_feedback():
    print("\n─── TEST 3: Save HITL feedback responses ───")

    # Feedback on feedback_specialist
    save_hitl_response(
        evaluation_id=FAKE_EVALUATION_ID,
        agent_name="feedback_specialist",
        ai_suggestion="Increase placeholder text contrast to minimum 4.5:1",
        user_action="agree",
        user_modified_suggestion="",
        reviewed_by=FAKE_USER_ID,
    )

    # Feedback on wireframe_designer
    save_hitl_response(
        evaluation_id=FAKE_EVALUATION_ID,
        agent_name="wireframe_designer",
        ai_suggestion="Add password visibility toggle icon inside password field",
        user_action="modify",
        user_modified_suggestion="Use an eye icon on the right side of the field with ARIA label",
        reviewed_by=FAKE_USER_ID,
    )

    doc = get_evaluation(FAKE_EVALUATION_ID)
    responses = doc["hitl_feedback"]["responses"]
    assert len(responses) == 2, f"Expected 2 responses, got {len(responses)}"
    assert doc["hitl_feedback"]["review_status"] == "reviewed"

    print(f"   review_status        : {doc['hitl_feedback']['review_status']}")
    for r in responses:
        print(f"   [{r['agent']}] {r['user_action']} — {r['ai_suggestion'][:50]}...")
        if r["user_modified_suggestion"]:
            print(f"     └─ modified: {r['user_modified_suggestion']}")

    print("✅ HITL feedback saved correctly")


def test_user_history():
    print("\n─── TEST 4: Fetch user evaluation history ───")
    docs = get_user_evaluations(FAKE_USER_ID)
    assert len(docs) > 0, "No evaluations found for user"
    print(f"   evaluations found    : {len(docs)}")
    print(f"   first evaluation_id  : {docs[0]['evaluation_id']}")
    print(f"   ux_score             : {docs[0].get('ai_results', {}).get('ux_score')}")
    print("✅ User history fetched correctly")


def test_fail_evaluation():
    print("\n─── TEST 5: Fail a separate evaluation ───")
    fail_id = str(uuid.uuid4())
    create_evaluation_document(fail_id, FAKE_USER_ID, FAKE_IMAGE_URL)
    fail_evaluation(fail_id, "Simulated pipeline crash")

    doc = get_evaluation(fail_id)
    assert doc["status"] == "failed"
    assert "error" in doc
    print(f"   status               : {doc['status']}")
    print(f"   error                : {doc['error']}")
    print("✅ Failed evaluation stored correctly")


# ─── Run All Tests ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  HeurUXAgent — MongoDB Schema Test")
    print("=" * 60)

    try:
        test_create_document()
        test_complete_evaluation()
        test_hitl_feedback()
        test_user_history()
        test_fail_evaluation()

        print("\n" + "=" * 60)
        print("  ALL TESTS PASSED ✅")
        print("=" * 60)
        print(f"\n  Check MongoDB Atlas → heuruxagent_db → evaluations")
        print(f"  Look for evaluation_id: {FAKE_EVALUATION_ID}")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        raise