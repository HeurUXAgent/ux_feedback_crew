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

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
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
    agent_name: str                     # "feedback_specialist" | "wireframe_designer"
    ai_suggestion: str = ""
    user_action: str                    # "agree" | "disagree" | "modify"
    user_modified_suggestion: str = ""


# ─── Pipeline ─────────────────────────────────────────────────────────────────

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

        await manager.send_progress(client_id, "Uploading image to S3...", 5)
        image_url = await upload_image_to_s3(file)

        create_evaluation_document(
            evaluation_id=job_id,
            user_id=x_user_id,
            screenshot_url=image_url,
        )

        await manager.send_progress(client_id, "Initializing Agents...", 10)

        # Run full pipeline — no blocking, completes end-to-end
        result = await run_in_threadpool(
            run_full_ux_pipeline_raw,
            image_url,
            client_id,
            job_id,
        )

        duration = time.time() - pipeline_start
        logger.info(f"[PIPELINE] Completed in {duration:.2f}s")

        complete_evaluation(
            evaluation_id=job_id,
            tasks_output=result.tasks_output,
            pipeline_duration_seconds=duration,
        )

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


# ─── Post-execution HITL ──────────────────────────────────────────────────────

@app.post("/submit-feedback")
async def submit_hitl_feedback(
    body: HITLFeedbackRequest,
    x_user_id: str = Header(default="anonymous"),
):
    """
    Called by Flutter after the user reviews the results on the result screen.
    Saves the HITL response to MongoDB for thesis analysis.
    No pipeline blocking — purely a data persistence endpoint.
    """
    if body.user_action not in ["agree", "disagree", "modify"]:
        raise HTTPException(status_code=400, detail="user_action must be: agree | disagree | modify")

    save_hitl_response(
        evaluation_id=body.evaluation_id,
        agent_name=body.agent_name,
        ai_suggestion=body.ai_suggestion,
        user_action=body.user_action,
        user_modified_suggestion=body.user_modified_suggestion,
        reviewed_by=x_user_id,
    )

    logger.info(f"[HITL] Saved | {body.agent_name} | {body.user_action} | {body.evaluation_id}")

    return {"message": "Feedback saved", "evaluation_id": body.evaluation_id}


# ─── Fetch ────────────────────────────────────────────────────────────────────

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