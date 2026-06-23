import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

from config.database import init_db_pool, close_db_pool
from app.routes.routes import router

# Lifespan manager to handle startup/shutdown cleanly
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the asyncpg PostgreSQL connection pool
    try:
        await init_db_pool()
    except Exception as e:
        print(f"[Lifespan Startup Error] Could not establish connection pool: {e}")
        
    yield
    
    # Shutdown: Clean up the connection pool resources
    await close_db_pool()

app = FastAPI(
    title="Hanyang Univ ERICA Lost & Found Control Server",
    description="Core backend server coordinating Temi Kiosk, RDK X5 hardware, Qwen VLM, and Admin Dashboard.",
    version="1.0.0",
    lifespan=lifespan
)

# Create folders if they do not exist
os.makedirs("static/thumbnails", exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# Standard Exception Handler to display custom premium error pages
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_html = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>시스템 오류 발생</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Outfit:wght@500;700&display=swap" rel="stylesheet">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
                color: #f1f5f9;
                font-family: 'Inter', sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                overflow: hidden;
            }}
            .error-card {{
                background: rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                padding: 40px;
                max-width: 600px;
                width: 90%;
                text-align: center;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
                animation: fadeIn 0.8s ease-out;
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            h1 {{
                font-family: 'Outfit', sans-serif;
                font-size: 3rem;
                margin-top: 0;
                background: linear-gradient(to right, #f43f5e, #f43f5e);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            p {{
                font-size: 1.1rem;
                color: #94a3b8;
                line-height: 1.6;
            }}
            .debug-box {{
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                padding: 15px;
                text-align: left;
                font-family: 'Courier New', Courier, monospace;
                font-size: 0.9rem;
                color: #f43f5e;
                word-break: break-all;
                max-height: 150px;
                overflow-y: auto;
                margin: 20px 0;
            }}
            .btn {{
                display: inline-block;
                background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
                color: #ffffff;
                text-decoration: none;
                padding: 12px 30px;
                border-radius: 8px;
                font-weight: 600;
                transition: all 0.3s ease;
                box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(99, 102, 241, 0.6);
            }}
        </style>
    </head>
    <body>
        <div class="error-card">
            <h1>500</h1>
            <h2>시스템 내부 오류 발생</h2>
            <p>서버 실행 도중 예기치 못한 에러가 발생했습니다. 관리자 페이지로 돌아가거나 시스템 관리자에게 문의해 주세요.</p>
            <div class="debug-box">
                {str(exc)}
            </div>
            <a href="/admin/lost-items" class="btn">관제 메인으로 이동</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=error_html, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"\n[Validation Error] Path: {request.url.path}")
    print(f" - Errors: {exc.errors()}")
    try:
        body = await request.body()
        print(f" - Body: {body.decode('utf-8', errors='ignore')}")
    except Exception:
        pass
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()}
    )

# Include routes
app.include_router(router)

if __name__ == "__main__":
    # Standard run configuration
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
