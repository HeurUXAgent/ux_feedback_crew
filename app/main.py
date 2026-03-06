import logging
import time
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import json
from pathlib import Path
import shutil
from src.ws_manager import manager
from fastapi import WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from app.services.s3_service import upload_image_to_s3
# Import from your pipeline bridge
# (
#     run_evaluation_pipeline,
#     run_wireframe_pipeline
# )


import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
sys.path.append(str(SRC_DIR))

from ux_feedback_crew.crew_pipeline import run_full_ux_pipeline

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def cleanup_files(*paths: Path):
    """Deletes files after the response is sent."""
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            print(f"Successfully cleaned up: {path}")
        except Exception as e:
            print(f"Cleanup error: {e}")

# # parsing the image as bytes
# @app.post("/analyze-and-wireframe/{client_id}")
# async def analyze_and_wireframe(background_tasks: BackgroundTasks,file: UploadFile = File(...), client_id: str = ""):
#     try:
#         job_id = str(uuid.uuid4())
#         upload_path = UPLOAD_DIR / f"{job_id}.png"

#         with open(upload_path, "wb") as f:
#             f.write(await file.read())

#         await manager.send_progress(client_id, "Initializing Agents...", 0)

#         # Run the consolidated pipeline 
#         # This returns the report and the wireframe in one execution
#         feedback_report, wireframe_output = await run_in_threadpool(
#             run_full_ux_pipeline, 
#             str(upload_path), 
#             client_id
#         )

#         # Save everything to a single JSON for records
#         final_data = {
#             "evaluation_id": job_id,
#             "feedback": feedback_report,
#             "wireframe": wireframe_output
#         }
        
#         job_id = str(uuid.uuid4())
#         upload_path = UPLOAD_DIR / f"{job_id}.png"
#         result_json_path = OUTPUT_DIR / f"{job_id}_result.json"

#         with open(result_json_path, "w") as f:
#             json.dump(final_data, f, indent=2)

#         background_tasks.add_task(cleanup_files, upload_path, result_json_path)

#         # Return everything to Flutter in one response
#         return final_data
    
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"System Error: {str(e)}")
    
    # parsing the image as bytes and then uploading to S3
@app.post("/analyze-and-wireframe-s3/{client_id}")

async def analyze_and_wireframe_s3(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    client_id: str = ""
):
    try:
        job_id = str(uuid.uuid4())
        logger.info("========== NEW REQUEST ==========")
        logger.info(f"[JOB ID] {job_id}")

        # 🔹 Upload image directly to S3
        s3_start = time.time()
        await manager.send_progress(client_id, "Uploading image to S3...", 5)
        image_url = await upload_image_to_s3(file)
        s3_end = time.time()
        logger.info(f"[S3 UPLOAD TIME] {s3_end - s3_start:.2f} seconds")

        await manager.send_progress(client_id, "Initializing Agents...", 10)

        # 🔹 Run pipeline with S3 URL instead of local path
        crew_start = time.time()
        feedback_report, wireframe_output = await run_in_threadpool(
            run_full_ux_pipeline,
            image_url,   # ← pass URL instead of file path
            client_id
        )
        crew_end = time.time()
        logger.info(f"[CREW EXECUTION TIME] {crew_end - crew_start:.2f} seconds")

        total_time = time.time() - s3_start
        logger.info(f"[TOTAL PIPELINE TIME] {total_time:.2f} seconds")
        final_data = {
            "evaluation_id": job_id,
            "image_url": image_url,
            "feedback": feedback_report,
            "wireframe": wireframe_output
        }

        result_json_path = OUTPUT_DIR / f"{job_id}_result.json"

        with open(result_json_path, "w") as f:
            json.dump(final_data, f, indent=2)

        background_tasks.add_task(cleanup_files, result_json_path)

        return final_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 Pipeline Error: {str(e)}")

    
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id)

