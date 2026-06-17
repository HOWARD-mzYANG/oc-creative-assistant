"""HTTP routes for project-scoped OC role model workflows."""

from fastapi import APIRouter, Body, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.schemas import (
    RoleModelChatHistoryItemPayload,
    RoleModelChatRequest,
    RoleModelChatResponse,
    RoleModelDatasetGenerateRequest,
    RoleModelDatasetPayload,
    RoleModelDatasetUpdateRequest,
    RoleModelDownloadRequest,
    RoleModelHardwarePayload,
    RoleModelJobPayload,
    RoleModelRecommendationPayload,
    RoleModelRecommendationRequest,
    RoleModelStatePayload,
    RoleModelTrainRequest,
)
from app.services.role_model_service import (
    chat_with_role_model,
    clear_role_model_chat_history,
    generate_dataset,
    get_dataset,
    get_download_status,
    get_role_model_chat_history,
    get_role_model_state,
    get_training_status,
    inspect_hardware,
    recommend_model,
    start_model_download,
    start_training,
    update_dataset,
)


router = APIRouter(prefix="/api/projects/{project_id}/role-model", tags=["role-model"])


def _bad_request(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.get("", response_model=RoleModelStatePayload)
async def read_role_model_state(project_id: str) -> RoleModelStatePayload:
    """Read the aggregate state used by the role-model studio."""
    return get_role_model_state(project_id)


@router.get("/hardware", response_model=RoleModelHardwarePayload)
async def read_role_model_hardware(project_id: str) -> RoleModelHardwarePayload:
    """Inspect backend host capabilities for local model work."""
    return inspect_hardware(project_id)


@router.post("/recommend", response_model=RoleModelRecommendationPayload)
async def create_role_model_recommendation(
    project_id: str,
    payload: RoleModelRecommendationRequest,
) -> RoleModelRecommendationPayload:
    """Recommend a small ModelScope model and LoRA parameters."""
    try:
        return recommend_model(project_id, payload)
    except ValueError as error:
        raise _bad_request(error) from error


@router.get("/dataset", response_model=RoleModelDatasetPayload)
async def read_role_model_dataset(project_id: str) -> RoleModelDatasetPayload:
    """Read the editable SFT dataset for this project."""
    return get_dataset(project_id)


@router.post("/dataset/generate", response_model=RoleModelDatasetPayload)
async def create_role_model_dataset(
    project_id: str,
    payload: RoleModelDatasetGenerateRequest | None = Body(default=None),
) -> RoleModelDatasetPayload:
    """Generate editable SFT samples from project characters."""
    return await run_in_threadpool(
        generate_dataset,
        project_id,
        payload or RoleModelDatasetGenerateRequest(),
    )


@router.put("/dataset", response_model=RoleModelDatasetPayload)
async def replace_role_model_dataset(
    project_id: str,
    payload: RoleModelDatasetUpdateRequest,
) -> RoleModelDatasetPayload:
    """Persist the user-reviewed SFT dataset and training JSONL."""
    return update_dataset(project_id, payload)


@router.post("/download", response_model=RoleModelJobPayload)
async def create_role_model_download(
    project_id: str,
    payload: RoleModelDownloadRequest,
) -> RoleModelJobPayload:
    """Start or return the current ModelScope download job."""
    try:
        return start_model_download(project_id, payload)
    except ValueError as error:
        raise _bad_request(error) from error


@router.get("/download", response_model=RoleModelJobPayload)
async def read_role_model_download(project_id: str) -> RoleModelJobPayload:
    """Read the current download job state."""
    return get_download_status(project_id)


@router.post("/train", response_model=RoleModelJobPayload)
async def create_role_model_training(
    project_id: str,
    payload: RoleModelTrainRequest,
) -> RoleModelJobPayload:
    """Start or return the current LoRA training job."""
    try:
        return start_training(project_id, payload)
    except ValueError as error:
        raise _bad_request(error) from error


@router.get("/train", response_model=RoleModelJobPayload)
async def read_role_model_training(project_id: str) -> RoleModelJobPayload:
    """Read the current LoRA training job state."""
    return get_training_status(project_id)


@router.get("/chat", response_model=list[RoleModelChatHistoryItemPayload])
async def read_role_model_chat(project_id: str) -> list[RoleModelChatHistoryItemPayload]:
    """Read persisted role-model chat history."""
    return get_role_model_chat_history(project_id)


@router.delete("/chat", status_code=204)
async def delete_role_model_chat(project_id: str) -> None:
    """Clear persisted role-model chat history."""
    clear_role_model_chat_history(project_id)


@router.post("/chat", response_model=RoleModelChatResponse)
async def post_role_model_chat(
    project_id: str,
    payload: RoleModelChatRequest,
) -> RoleModelChatResponse:
    """Chat with the trained role model, falling back to the configured AI API."""
    return chat_with_role_model(project_id, payload)
