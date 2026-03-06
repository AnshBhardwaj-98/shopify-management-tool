from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response
from app.services.bulk_fetch_service import BulkFetchService
import json
import threading

router = APIRouter()
service = BulkFetchService()

# In-memory store for the last exported file
_last_export: dict = {"data": None, "ready": False, "error": None}


def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@router.post("/export-products/start")
def start_export():
    """
    SSE endpoint — streams progress logs while running the full bulk sync.
    When done, stores the Excel bytes in memory for /export-products/download.
    """
    global _last_export
    _last_export = {"data": None, "ready": False, "error": None}

    def generate():
        yield ": keep-alive\n\n"

        messages = []

        def log(msg):
            messages.append(msg)

        try:
            yield sse_event({"type": "log", "msg": "🚀 Starting full product sync..."})

            excel_bytes = service.export_to_excel(
                progress_callback=lambda msg: messages.append(msg)
            )

            # Flush any buffered log messages
            for msg in messages:
                yield sse_event({"type": "log", "msg": msg})
            messages.clear()

            _last_export["data"] = excel_bytes
            _last_export["ready"] = True

            yield sse_event({"type": "done", "msg": "✅ Export ready — downloading..."})

        except Exception as e:
            _last_export["error"] = str(e)
            yield sse_event({"type": "error", "msg": f"❌ Export failed: {e}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/export-products/download")
def download_export():
    """Serve the Excel file produced by /export-products/start."""
    if not _last_export["ready"] or not _last_export["data"]:
        return Response(content="Export not ready", status_code=404)

    filename = f"shopify_products_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return Response(
        content=_last_export["data"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )