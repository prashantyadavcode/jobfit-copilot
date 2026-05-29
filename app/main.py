from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.schemas import AnalyzeTextRequest, LatexRewriteRequest, LatexSectionsRequest
from src.core.config import get_settings
from src.services.analyzer_service import AnalyzerService
from src.services.latex_service import LatexService
from src.services.parser_service import parse_file

settings = get_settings()
service = AnalyzerService(spacy_model=settings.spacy_model)
latex_service = LatexService(
    llm_provider=settings.llm_provider,
    ollama_base_url=settings.ollama_base_url,
    ollama_model=settings.ollama_model,
    latex_compiler=settings.latex_compiler,
    openai_api_key=settings.openai_api_key,
    openai_model=settings.openai_model,
)

app = FastAPI(title=settings.app_name, version='1.0.0')

STATIC_DIR = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')


@app.get('/', include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / 'index.html')


@app.get('/health')
def health():
    return {'status': 'healthy', 'app': settings.app_name}


@app.post('/analyze/text')
def analyze_text(body: AnalyzeTextRequest):
    return service.analyze(body.resume_text, body.jd_text)


@app.post('/analyze/files')
async def analyze_files(
    resume_file: UploadFile = File(...),
    jd_file: UploadFile = File(...),
):
    resume_bytes = await resume_file.read()
    jd_bytes = await jd_file.read()

    resume_text = parse_file(resume_bytes, resume_file.filename)
    jd_text = parse_file(jd_bytes, jd_file.filename)
    return service.analyze(resume_text, jd_text)


@app.post('/analyze/mixed')
async def analyze_mixed(
    resume_file: UploadFile = File(...),
    jd_text: str = Form(...),
):
    resume_text = parse_file(await resume_file.read(), resume_file.filename)
    return service.analyze(resume_text, jd_text)


@app.post('/latex/sections')
def latex_sections(body: LatexSectionsRequest):
    return {'sections': latex_service.extract_sections(body.latex_code)}


@app.post('/latex/rewrite')
async def latex_rewrite(body: LatexRewriteRequest):
    try:
        return await latex_service.rewrite_sections(
            latex_code=body.latex_code,
            selected_section_ids=body.selected_section_ids,
            jd_text=body.jd_text,
            missing_skills=body.missing_skills,
            matched_skills=body.matched_skills,
            suggestions=body.suggestions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to rewrite sections: {exc}") from exc

