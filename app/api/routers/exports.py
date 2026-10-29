from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime

from app.api.deps import ClockDep, CurrentActor, DbSession
from app.api.params import TicketListParams
from app.schemas.exports import ExportFormat, ExportType
from app.services.exports import ExportService

router = APIRouter(tags=["reports"])


@router.get("/reports/export", response_class=StreamingResponse)
def export_report(
    actor: CurrentActor,
    db: DbSession,
    clock: ClockDep,
    export_type: Annotated[ExportType, Query(alias="type")],
    export_format: Annotated[ExportFormat, Query(alias="format")],
    query: TicketListParams,
    start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> StreamingResponse:
    export = ExportService(db, clock).export(actor, export_type, export_format, query, start, end)
    return StreamingResponse(
        export.chunks,
        media_type=export.media_type,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )
