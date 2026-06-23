#!/bin/bash
# Uvicorn startup script for Hanyang ERICA Lost & Found Main Backend

# Ensure we are in the project root directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 1. Virtual Environment (.venv) 위치 탐색 및 생성
VENV_DIR=""
if [ -d "../.venv" ]; then
    VENV_DIR="../.venv"
elif [ -d "./.venv" ]; then
    VENV_DIR="./.venv"
else
    echo "📦 가상환경(.venv)이 존재하지 않아 새로 생성합니다 (.venv)..."
    python3 -m venv .venv
    VENV_DIR="./.venv"
fi

# 2. 가상환경 활성화
source "$VENV_DIR/bin/activate"
echo "✅ 가상환경 활성화 완료: $VENV_DIR"

# 3. requirements.txt 패키지 설치/업데이트
if [ -f "requirements.txt" ]; then
    echo "🔄 requirements.txt 기반 의존성 패키지를 확인 및 설치 중입니다..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "⚠️ Warning: requirements.txt 파일을 찾을 수 없어 설치 과정을 건너뜁니다."
fi

# 4. 가상환경 내 uvicorn 바이너리를 직접 지정하여 실행 (sudo 실행 시 PATH 초기화 대응)
echo "🚀 Starting Hanyang ERICA Lost & Found Main Server on port 8000..."
export PYTHONUNBUFFERED=1
"$VENV_DIR/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --reload
