import logging
import time
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
from pathlib import Path
from src.ws_manager import manager
from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from app.services.s3_service import upload_image_to_s3
from app.services.database import (
    create_evaluation_document,
    complete_evaluation,
    fail_evaluation,
    save_hitl_response,
    get_evaluation,
    get_user_evaluations,
    get_evaluations_for_analysis,
)
from app.utils.hitl_handler import (
    register_hitl_session,
    submit_human_feedback,
    cleanup_hitl_session,
)
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR  = ROOT_DIR / "src"
sys.path.append(str(SRC_DIR))

from ux_feedback_crew.crew_pipeline import run_full_ux_pipeline_raw

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path("outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─── Pydantic Models ──────────────────────────────────────────────────────────

class HITLFeedbackRequest(BaseModel):
    evaluation_id: str
    agent_name: str                  # "feedback_specialist" | "wireframe_designer"
    ai_suggestion: str = ""          # the original AI suggestion being reviewed
    user_action: str                 # "agree" | "disagree" | "modify"
    user_modified_suggestion: str = ""


# ─── Main Pipeline Endpoint ───────────────────────────────────────────────────

@app.post("/analyze-and-wireframe-s3/{client_id}")
async def analyze_and_wireframe_s3(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    client_id: str = "",
    x_user_id: str = Header(default="anonymous"),   # Firebase UID sent from Flutter
):
    job_id = str(uuid.uuid4())
    pipeline_start = time.time()

    try:
        logger.info(f"[JOB START] {job_id} | user: {x_user_id}")

        # ── 1. Upload to S3 ──
        await manager.send_progress(client_id, "Uploading image to S3...", 5)
        image_url = await upload_image_to_s3(file)

        # ── 2. Create MongoDB document immediately (status: processing) ──
        create_evaluation_document(
            evaluation_id=job_id,
            user_id=x_user_id,
            screenshot_url=image_url,
        )
        logger.info(f"[MONGO] Document created for {job_id}")

        await manager.send_progress(client_id, "Initializing Agents...", 10)

        # ── 3. Register HITL session ──
        register_hitl_session(job_id)

        # ── 4. Run CrewAI pipeline ──
        result = await run_in_threadpool(
            run_full_ux_pipeline_raw,
            image_url,
            client_id,
            job_id,
        )

        duration = time.time() - pipeline_start
        logger.info(f"[PIPELINE] Done in {duration:.2f}s")

        # ── 5. Complete MongoDB document with all agent outputs ──
        complete_evaluation(
            evaluation_id=job_id,
            tasks_output=result.tasks_output,
            pipeline_duration_seconds=duration,
        )
        logger.info(f"[MONGO] Evaluation completed for {job_id}")

        # ── 6. Cleanup ──
        background_tasks.add_task(cleanup_hitl_session, job_id)

        await manager.send_progress(client_id, "Pipeline Complete", 100)

        return {
            "evaluation_id": job_id,
            "image_url": image_url,
            "feedback": str(result.tasks_output[2].raw),
            "wireframe": str(result.tasks_output[3].raw),
        }

    except Exception as e:
        # Mark as failed in MongoDB so history UI shows correct status
        fail_evaluation(job_id, str(e))
        logger.error(f"[ERROR] {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── HITL Feedback Endpoint ───────────────────────────────────────────────────

@app.post("/submit-feedback")
async def submit_hitl_feedback(
    body: HITLFeedbackRequest,
    x_user_id: str = Header(default="anonymous"),
):
    """
    Called by Flutter when reviewer submits their rating on an agent output.
    Does two things:
      1. Unblocks the waiting CrewAI pipeline thread
      2. Persists the feedback to MongoDB
    """
    if body.user_action not in ["agree", "disagree", "modify"]:
        raise HTTPException(status_code=400, detail="user_action must be: agree | disagree | modify")

    evaluation = get_evaluation(body.evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Unblock the CrewAI pipeline
    unblocked = submit_human_feedback(
        evaluation_id=body.evaluation_id,
        rating=body.user_action,
        suggestion=body.user_modified_suggestion,
    )

    # Persist to MongoDB
    save_hitl_response(
        evaluation_id=body.evaluation_id,
        agent_name=body.agent_name,
        ai_suggestion=body.ai_suggestion,
        user_action=body.user_action,
        user_modified_suggestion=body.user_modified_suggestion,
        reviewed_by=x_user_id,
    )

    logger.info(f"[HITL] {body.agent_name} | {body.user_action} | {body.evaluation_id}")

    return {
        "message": "Feedback saved",
        "pipeline_unblocked": unblocked,
        "evaluation_id": body.evaluation_id,
    }


# ─── History / Fetch Endpoints ────────────────────────────────────────────────

@app.get("/evaluation/{evaluation_id}")
async def get_single_evaluation(evaluation_id: str):
    """Full evaluation details — used on result screen."""
    doc = get_evaluation(evaluation_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return doc


@app.get("/evaluations/user/{user_id}")
async def get_user_history(user_id: str):
    """
    Lightweight evaluation history for a user.
    Used to render the history screen in Flutter.
    """
    docs = get_user_evaluations(user_id)
    return {"evaluations": docs}


@app.get("/evaluations/analysis/export")
async def export_for_analysis():
    """
    Exports all completed evaluations for thesis analysis.
    Use this to compute HITL agreement rates, score distributions etc.
    """
    docs = get_evaluations_for_analysis()
    return {"total": len(docs), "evaluations": docs}


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id)

    
# @app.websocket("/ws/{client_id}")
# async def websocket_endpoint(websocket: WebSocket, client_id: str):
#     await manager.connect(client_id, websocket)
#     try:
#         while True:
#             await websocket.receive_text()
#     except WebSocketDisconnect:
#         manager.disconnect(client_id)

