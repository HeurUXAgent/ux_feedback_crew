# ══ CRITICAL: This must be the very first import ══
# Patches builtins.input globally before CrewAI or any other module loads.
# If this import is not first, CrewAI caches the original input() and the
# patch won't intercept it.
import app.utils.hitl_handler  # noqa: F401  ← patch happens here at import time

import logging
import time
import sys
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
from starlette.concurrency import run_in_threadpool

from src.ws_manager import manager
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("outputs", exist_ok=True)


# ─── Models ───────────────────────────────────────────────────────────────────

class HITLFeedbackRequest(BaseModel):
    evaluation_id: str
    agent_name: str
    ai_suggestion: str = ""
    user_action: str                    # "agree" | "disagree" | "modify"
    user_modified_suggestion: str = ""


# ─── Pipeline Endpoint ────────────────────────────────────────────────────────

@app.post("/analyze-and-wireframe-s3/{client_id}")
async def analyze_and_wireframe_s3(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    client_id: str = "",
    x_user_id: str = Header(default="anonymous"),
):
    job_id = str(uuid.uuid4())
    pipeline_start = time.time()

    try:
        logger.info(f"[JOB START] {job_id} | user: {x_user_id}")

        # 1. Upload to S3
        await manager.send_progress(client_id, "Uploading image to S3...", 5)
        image_url = await upload_image_to_s3(file)

        # 2. Create MongoDB document (status: processing)
        create_evaluation_document(
            evaluation_id=job_id,
            user_id=x_user_id,
            screenshot_url=image_url,
        )

        # 3. Send JOB_ID to Flutter BEFORE pipeline starts
        #    Flutter stores this so it can POST to /submit-feedback mid-pipeline
        await manager.send_progress(client_id, f"JOB_ID:{job_id}", 8)
        await manager.send_progress(client_id, "Initializing Agents...", 10)

        # 4. Register HITL session for this evaluation
        register_hitl_session(job_id)

        # 5. Run pipeline in thread
        #    When generate_feedback task completes, CrewAI calls input()
        #    → our patch intercepts → sends HITL_REQUIRED to Flutter
        #    → blocks until Flutter POSTs to /submit-feedback
        result = await run_in_threadpool(
            run_full_ux_pipeline_raw,
            image_url,
            client_id,
            job_id,
        )

        duration = time.time() - pipeline_start
        logger.info(f"[PIPELINE] Completed in {duration:.2f}s")

        # 6. Save results to MongoDB
        complete_evaluation(
            evaluation_id=job_id,
            tasks_output=result.tasks_output,
            pipeline_duration_seconds=duration,
        )

        background_tasks.add_task(cleanup_hitl_session, job_id)
        await manager.send_progress(client_id, "Pipeline Complete", 100)

        return {
            "evaluation_id": job_id,
            "image_url": image_url,
            "feedback":  str(result.tasks_output[2].raw),
            "wireframe": str(result.tasks_output[3].raw),
        }

    except Exception as e:
        fail_evaluation(job_id, str(e))
        logger.error(f"[ERROR] {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── HITL Endpoint ────────────────────────────────────────────────────────────

@app.post("/submit-feedback")
async def submit_hitl_feedback(
    body: HITLFeedbackRequest,
    x_user_id: str = Header(default="anonymous"),
):
    if body.user_action not in ["agree", "disagree", "modify"]:
        raise HTTPException(status_code=400, detail="user_action must be: agree | disagree | modify")

    # Unblocks the pipeline thread waiting inside _patched_input()
    unblocked = submit_human_feedback(
        evaluation_id=body.evaluation_id,
        rating=body.user_action,
        suggestion=body.user_modified_suggestion,
    )

    # Save to MongoDB regardless of whether pipeline was waiting
    save_hitl_response(
        evaluation_id=body.evaluation_id,
        agent_name=body.agent_name,
        ai_suggestion=body.ai_suggestion,
        user_action=body.user_action,
        user_modified_suggestion=body.user_modified_suggestion,
        reviewed_by=x_user_id,
    )

    logger.info(f"[HITL] {body.agent_name} | {body.user_action} | unblocked={unblocked}")

    return {
        "message": "Feedback saved",
        "pipeline_unblocked": unblocked,
        "evaluation_id": body.evaluation_id,
    }


# ─── Fetch Endpoints ──────────────────────────────────────────────────────────

@app.get("/evaluation/{evaluation_id}")
async def get_single_evaluation(evaluation_id: str):
    doc = get_evaluation(evaluation_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return doc


@app.get("/evaluations/user/{user_id}")
async def get_user_history(user_id: str):
    return {"evaluations": get_user_evaluations(user_id)}


@app.get("/evaluations/analysis/export")
async def export_for_analysis():
    docs = get_evaluations_for_analysis()
    return {"total": len(docs), "evaluations": docs}


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    logger.info(f"[WS] Connected: {client_id}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"[WS] Disconnected: {client_id}")