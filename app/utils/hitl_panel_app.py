"""
hitl_panel_app.py

Panel-based HITL review widget. Run separately:
  panel serve app/hitl_panel_app.py --port 5006 --allow-websocket-origin=localhost:3000

React opens this in an iframe modal when HITL_REQUIRED arrives.
On submit, POSTs to FastAPI /submit-feedback and notifies React to close.
"""

import requests
import json
import param
import panel as pn
from panel.viewable import Viewer

pn.extension(sizing_mode="stretch_width", notifications=True)

FASTAPI_URL = "http://127.0.0.1:8000"


def get_feedback_data(evaluation_id: str) -> dict | None:
    """Fetch the stored feedback from FastAPI's /hitl-content endpoint."""
    try:
        res = requests.get(f"{FASTAPI_URL}/hitl-content/{evaluation_id}", timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"[Panel] Could not fetch feedback: {e}")
    return None


def _normalize_feedback(fd: dict) -> dict:
    """
    Guard against the agent returning summary/ux_score as strings instead
    of dicts. Normalises in-place and returns the same dict.

    Handles two cases:
      1. summary   is a str  → replace with a stub dict
      2. ux_score  is a str  → treat the string as the reasoning field
    """
    summary = fd.get("summary", {})
    if isinstance(summary, str):
        # Try to count items from feedback_items if available
        items = fd.get("feedback_items", [])
        priorities = [i.get("priority", "low").lower() for i in items if isinstance(i, dict)]
        fd["summary"] = {
            "total_issues": len(items),
            "high":   priorities.count("high"),
            "medium": priorities.count("medium"),
            "low":    priorities.count("low"),
            "_note":  summary,   # keep original string for debugging
        }

    score = fd.get("ux_score", {})
    if isinstance(score, str):
        fd["ux_score"] = {"score": "—", "reasoning": score}
    elif score is None:
        fd["ux_score"] = {"score": "—", "reasoning": ""}

    return fd


class HITLReviewWidget(Viewer):
    evaluation_id = param.String()
    selected      = param.String(default="")
    submitted     = param.Boolean(default=False)

    def __init__(self, evaluation_id: str, feedback_data: dict, **params):
        super().__init__(evaluation_id=evaluation_id, **params)
        self._feedback = _normalize_feedback(feedback_data)
        self._suggestion_input = pn.widgets.TextAreaInput(
            placeholder="e.g. Contrast issues were missed, please re-evaluate accessibility...",
            height=90, visible=False, name=""
        )
        self._submit_btn = pn.widgets.Button(
            name="Select an option above",
            button_type="primary",
            disabled=True,
            height=44,
        )
        self._status = pn.pane.Alert("", alert_type="success", visible=False)
        self._submit_btn.on_click(self._on_submit)

    def _select(self, value: str):
        self.selected = value
        self._suggestion_input.visible = value in ("disagree", "modify")
        self._submit_btn.disabled = False
        labels = {
            "agree":    "Approve & Generate Wireframe →",
            "disagree": "Submit Rejection & Continue →",
            "modify":   "Submit Modifications & Continue →",
        }
        self._submit_btn.name = labels[value]

    def _on_submit(self, event):
        if not self.selected:
            return
        suggestion = self._suggestion_input.value.strip()
        if self.selected in ("disagree", "modify") and not suggestion:
            pn.state.notifications.error("Please describe what should change.", duration=3000)
            return

        self._submit_btn.disabled = True
        self._submit_btn.name = "Submitting..."

        try:
            res = requests.post(
                f"{FASTAPI_URL}/submit-feedback",
                json={
                    "evaluation_id": self.evaluation_id,
                    "agent_name": "feedback_specialist",
                    "ai_suggestion": "",
                    "user_action": self.selected,
                    "user_modified_suggestion": suggestion,
                },
                timeout=10,
            )
            if res.status_code == 200:
                self.submitted = True
                self._status.object = (
                    "✓ Feedback submitted! Wireframe generation is now in progress. "
                    "You can close this panel."
                )
                self._status.visible = True
                self._submit_btn.name = "Submitted ✓"
                pn.state.execute(
                    "window.parent.postMessage({type:'HITL_SUBMITTED',action:'"
                    + self.selected + "'}, '*');"
                )
            else:
                pn.state.notifications.error(f"Submit failed: {res.status_code}", duration=4000)
                self._submit_btn.disabled = False
                self._submit_btn.name = "Retry"
        except Exception as e:
            pn.state.notifications.error(f"Error: {e}", duration=4000)
            self._submit_btn.disabled = False

    def _chip(self, value: str, label: str, color: str) -> pn.widgets.Button:
        btn = pn.widgets.Button(name=label, button_type="default", height=40)
        btn.stylesheets = [f"""
            .bk-btn {{
                border: 1.5px solid #E5E7EB;
                border-radius: 8px;
                font-weight: 600;
                font-size: 13px;
                background: #F9FAFB;
                color: #6B7280;
                transition: all 0.15s;
            }}
            .bk-btn:hover {{
                border-color: {color};
                color: {color};
                background: {color}18;
            }}
        """]
        btn.on_click(lambda e: self._select(value))
        return btn

    def _render_feedback_items(self) -> list:
        items = self._feedback.get("feedback_items", [])
        if not isinstance(items, list):
            return []
        cards = []
        for item in items:
            if not isinstance(item, dict):
                continue
            p = (item.get("priority") or "low").lower()
            colors = {"high": "#EF4444", "medium": "#D97706", "low": "#10B981"}
            color = colors.get(p, "#6B7280")

            priority_badge = pn.pane.HTML(
                f'<span style="background:{color}18;color:{color};padding:3px 10px;'
                f'border-radius:99px;font-size:11px;font-weight:700;letter-spacing:0.5px">'
                f'{p.upper()}</span>'
            )
            title = pn.pane.HTML(
                f'<strong style="font-size:14px;color:#111827">{item.get("title","")}</strong>'
            )
            why = pn.pane.HTML(
                f'<div style="margin-top:8px">'
                f'<span style="font-size:12px;font-weight:700;color:#374151">ℹ Why it matters</span><br>'
                f'<span style="font-size:12px;color:#6B7280;line-height:1.6">{item.get("why_it_matters","")}</span>'
                f'</div>'
            )
            what_to_do = item.get("what_to_do") or []
            if isinstance(what_to_do, str):
                what_to_do = [what_to_do]
            what_items = "".join(
                f'<li style="font-size:12px;color:#374151;margin-bottom:4px">• {s}</li>'
                for s in what_to_do
            )
            what = pn.pane.HTML(
                f'<div style="margin-top:8px">'
                f'<span style="font-size:12px;font-weight:700;color:#374151">✓ What to do</span>'
                f'<ul style="list-style:none;padding:0;margin:6px 0 0">{what_items}</ul>'
                f'</div>'
            )
            card_content = [priority_badge, title, why, what]
            if item.get("wireframe_changes"):
                card_content.append(pn.pane.HTML(
                    f'<div style="margin-top:8px">'
                    f'<span style="font-size:12px;font-weight:700;color:#374151">✎ Wireframe changes</span><br>'
                    f'<span style="font-size:12px;color:#6B7280">{item["wireframe_changes"]}</span>'
                    f'</div>'
                ))
            cards.append(pn.Card(
                *card_content,
                collapsible=True, collapsed=True,
                styles={
                    "border": "1px solid #E5E7EB",
                    "border-left": f"3px solid {color}",
                    "border-radius": "10px",
                    "padding": "0",
                }
            ))
        return cards

    def __panel__(self):
        fd = self._feedback
        # Already normalised in __init__ — safe to .get() as dicts
        summary = fd.get("summary", {})
        score   = fd.get("ux_score", {})
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(score, dict):
            score = {}

        # ── Header ──
        header = pn.pane.HTML("""
            <div style="display:flex;align-items:center;gap:12px;padding:16px 20px;
                        background:#F5F7FF;border-bottom:1px solid #DDE1F8">
                <div style="width:40px;height:40px;background:#FEF3C7;border-radius:10px;
                            display:flex;align-items:center;justify-content:center;font-size:20px">
                    📋
                </div>
                <div>
                    <div style="font-size:15px;font-weight:700;color:#111827">Review Feedback Report</div>
                    <div style="font-size:12px;color:#6B7280">Pipeline paused — approve or modify to continue</div>
                </div>
            </div>
        """, sizing_mode="stretch_width")

        # ── Stats ──
        stats_html = f"""
            <div style="display:flex;border-bottom:1px solid #E5E7EB">
                <div style="flex:1;text-align:center;padding:16px 8px">
                    <div style="font-size:26px;font-weight:800;color:#5B6FE7">{score.get('score', '—')}</div>
                    <div style="font-size:11px;color:#6B7280">UX Score</div>
                </div>
                <div style="width:1px;background:#E5E7EB"></div>
                <div style="flex:1;text-align:center;padding:16px 8px">
                    <div style="font-size:26px;font-weight:800;color:#5B6FE7">{summary.get('total_issues', 0)}</div>
                    <div style="font-size:11px;color:#6B7280">Total Issues</div>
                </div>
                <div style="width:1px;background:#E5E7EB"></div>
                <div style="flex:1;text-align:center;padding:16px 8px">
                    <div style="font-size:26px;font-weight:800;color:#EF4444">{summary.get('high', 0)}</div>
                    <div style="font-size:11px;color:#6B7280">High</div>
                </div>
                <div style="width:1px;background:#E5E7EB"></div>
                <div style="flex:1;text-align:center;padding:16px 8px">
                    <div style="font-size:26px;font-weight:800;color:#D97706">{summary.get('medium', 0)}</div>
                    <div style="font-size:11px;color:#6B7280">Medium</div>
                </div>
                <div style="width:1px;background:#E5E7EB"></div>
                <div style="flex:1;text-align:center;padding:16px 8px">
                    <div style="font-size:26px;font-weight:800;color:#10B981">{summary.get('low', 0)}</div>
                    <div style="font-size:11px;color:#6B7280">Low</div>
                </div>
            </div>
        """
        if score.get("reasoning"):
            stats_html += f"""
                <div style="padding:12px 20px;background:#FAFBFF;border-bottom:1px solid #E5E7EB;
                            font-size:12px;color:#6B7280;line-height:1.6">
                    <strong style="color:#374151">Summary:</strong> {score['reasoning']}
                </div>
            """
        stats = pn.pane.HTML(stats_html, sizing_mode="stretch_width")

        # ── Feedback items ──
        items_col = pn.Column(
            *self._render_feedback_items(),
            sizing_mode="stretch_width",
            styles={"padding": "12px 16px", "max-height": "380px", "overflow-y": "auto"},
        )

        # ── Decision section ──
        decision_header = pn.pane.HTML(
            '<div style="padding:16px 20px 8px;font-size:14px;font-weight:600;color:#111827;'
            'border-top:1px solid #E5E7EB">'
            'Are you satisfied with this feedback report?</div>',
            sizing_mode="stretch_width"
        )

        chips = pn.Row(
            self._chip("agree",    "Approve ✓", "#10B981"),
            self._chip("disagree", "Reject ✗",  "#EF4444"),
            self._chip("modify",   "Modify ✎",  "#5B6FE7"),
            sizing_mode="stretch_width",
            styles={"padding": "0 20px 12px"},
        )

        suggestion_label = pn.pane.HTML(
            '<div style="padding:4px 20px 6px;font-size:13px;font-weight:600;color:#374151">'
            'What should be changed?</div>',
            sizing_mode="stretch_width"
        )

        submit_row = pn.Row(
            self._submit_btn,
            sizing_mode="stretch_width",
            styles={"padding": "8px 20px 20px"},
        )

        return pn.Column(
            header, stats, items_col,
            decision_header, chips,
            suggestion_label,
            pn.Row(self._suggestion_input, sizing_mode="stretch_width",
                   styles={"padding": "0 20px 8px"}),
            submit_row,
            self._status,
            sizing_mode="stretch_width",
            styles={
                "background": "#FFFFFF",
                "border-radius": "12px",
                "box-shadow": "0 4px 16px rgba(0,0,0,0.08)",
                "font-family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            }
        )


def create_app():
    """Panel app factory — reads evaluation_id from URL param."""
    evaluation_id = pn.state.location.search.lstrip("?").split("eval_id=")
    if len(evaluation_id) < 2:
        return pn.pane.HTML(
            '<div style="padding:40px;text-align:center;color:#6B7280">No evaluation ID provided.</div>'
        )
    eval_id = evaluation_id[1].split("&")[0]

    feedback_data = get_feedback_data(eval_id)
    if not feedback_data:
        return pn.pane.HTML(
            f'<div style="padding:40px;text-align:center;color:#EF4444">'
            f'Could not load feedback for evaluation {eval_id}</div>'
        )

    widget = HITLReviewWidget(evaluation_id=eval_id, feedback_data=feedback_data)
    return pn.Column(
        widget,
        sizing_mode="stretch_width",
        styles={"max-width": "760px", "margin": "24px auto", "padding": "0 16px"},
    )