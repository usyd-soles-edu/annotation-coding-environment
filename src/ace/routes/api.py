import asyncio

from fastapi import APIRouter

from ace.routes.api_agreement import router as agreement_router
from ace.routes.api_codebook import router as codebook_router
from ace.routes.api_coding import router as coding_router
from ace.routes.api_project_import import router as project_import_router
from ace.routes.api_support import (
    _clear_agreement_cache,
    _oob_status,
    _render_colour_style_oob,
    _require_coder,
)

router = APIRouter()
router.include_router(project_import_router)
router.include_router(coding_router)
router.include_router(codebook_router)
router.include_router(agreement_router)
