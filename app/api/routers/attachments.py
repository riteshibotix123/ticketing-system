from urllib.parse import quote

from fastapi import APIRouter, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import ClockDep, CurrentActor, DbSession, SettingsDep
from app.integrations.scanner import build_scanner
from app.integrations.storage import build_storage
from app.schemas.attachments import AttachmentOut
from app.services.attachments import AttachmentService

router = APIRouter(tags=["attachments"])


def _service(db: DbSession, clock: ClockDep, settings: SettingsDep) -> AttachmentService:
    return AttachmentService(db, clock, settings, build_storage(settings), build_scanner(settings))


@router.post("/attachments", response_model=AttachmentOut, status_code=201)
def upload_attachment(
    file: UploadFile,
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
) -> AttachmentOut:
    service = _service(db, clock, settings)
    return service.upload(actor, file.filename, file.content_type, file.file)


@router.get("/attachments/{id}/download")
def download_attachment(
    id: str, actor: CurrentActor, db: DbSession, clock: ClockDep, settings: SettingsDep
) -> StreamingResponse:
    download = _service(db, clock, settings).download(actor, id)
    name = quote(download.attachment.file_name, safe="")
    return StreamingResponse(
        download.stream,
        media_type=download.attachment.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{name}",
            "X-Content-Type-Options": "nosniff",
            "Content-Length": str(download.attachment.size_bytes),
        },
    )
