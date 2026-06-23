# 스마트 IoT 분실물 통합 관리 및 매칭 시스템

본 프로젝트는 모바일 제보 앱(Android), 엣지 실시간 객체 탐지 및 물리 도어/LED 제어 단말(RDK X5), 로컬 멀티모달 AI 분석 엔진(mlx_vlm Qwen 3.5-9B), 그리고 LLM 기반 AI 매칭 및 관리 대시보드(FastAPI + PostgreSQL)가 유기적으로 연동되는 **분산형 스마트 IoT 분실물 관리 플랫폼**입니다.

---

## 시스템 아키텍처 개요 (System Architecture)

전체 시스템은 비동기 REST API를 통해 결합도를 낮추고 유기적으로 통신하는 3개의 분산 서비스로 구성됩니다.

```mermaid
graph TD
    A[안드로이드 클라이언트 / 키오스크] -- "1. 습득 제보 등록 (1차 사진 + 메타 데이터)" --> B[VLM 조율 서버 :8080]
    B -- "2. 보관함 문 닫기 시그널 전달" --> C[RDK X5 엣지 제어 단말 :8000]
    B -- "3. 내부 스튜디오 정밀 촬영 요청" --> C
    C -- "4. 2차 이미지 반환 (BPU YOLOv8 바운딩박스 렌더링)" --> B
    B -- "5. 로컬 VLM (Qwen3.5-9B) 기반 물리 특징 태그 추출" --> B
    B -- "6. 정제된 메타 정보 및 경량화 썸네일 전송" --> D[메인 웹 및 데이터베이스 서버 :8000]
    D -- "7. PostgreSQL DB 적재 및 관리자 인가" --> D
    
    E[관리자 웹 콘솔] -- "8. AI 지능형 매칭 (OpenRouter LLM + 위치 가중치)" --> D
    A -- "9. 수령 확정 (인증 코드 검증)" --> D
    D -- "10. 보관함 문 열기 신호 릴레이" --> C
```

### 1. 메인 웹 및 데이터베이스 서버 (`lost_found_project`)
* **핵심 스택**: FastAPI, PostgreSQL, `asyncpg`, Jinja2 Templates.
* **주요 역할**:
  - 관리자를 위한 습득물 현황 시각화, 분실 신고 접수, 매칭 후보 제외/승인 기능 제공.
  - **AI 지능형 매칭 엔진 (`matcher_engine.py`)**: 분실자가 입력한 자연어 특이사항에서 LLM(OpenRouter 상의 Nemotron 또는 Fallback 파서)을 사용해 핵심 특징 키워드를 추출한 뒤, DB 내 보관 중인 습득물의 VLM 키워드와의 겹침 점수(Hit-rate)를 산출합니다.
  - **위치 보너스 (Location Boost)**: 분실 장소와 습득 장소가 유사하거나 일치할 경우 **15%의 매칭율 가중치**를 부여하여 검색 정확도를 고도화합니다.
  - 수령 완료 신호(`api_confirm_relay`) 수신 시, 지정된 하드웨어 단말(RDK X5)로 보관함 잠금 해제 요청을 포워딩합니다.

### 2. VLM 조율 서버 (`vlm`)
* **핵심 스택**: FastAPI, `mlx_vlm` (Apple Silicon Metal 가속), Pillow, `requests`.
* **주요 역할**:
  - 키오스크/안드로이드로부터 접수된 습득물 처리의 중간 오케스트레이터 역할을 수행합니다.
  - 원격 2차 촬영을 진행하기 전 안전사고 예방을 위해 RDK X5 단말에 도어 닫힘 명령을 먼저 송신합니다.
  - RDK X5의 정밀 촬상 본을 입수한 후 로컬 가중치(`Qwen3.5-9B`) 모델에 전처리 텍스트와 이미지를 주입하여 색상, 로고, 세부 형태 등 시각적으로 유의미한 콤팩트 태그 문자열(`vlm_keywords`)을 추출합니다.
  - 메인 서버의 저장 규격에 맞게 원본 해상도 이미지를 400px 폭의 80% 화질 JPEG 썸네일로 경량화하여 메인 DB 서버로 최종 이관합니다.

### 3. RDK X5 엣지 카메라 및 보관함 제어 단말 (`arducam_yolo_web`)
* **핵심 스택**: Flask, OpenCV (V4L2 Grabber), BPU YOLOv8 모델 (`hbm_runtime`), PWM Servo, SPI LEDs.
* **주요 역할**:
  - BPU 가속 및 OpenCV 프레임 캡처 스레드를 별도로 분리 설계하여 락 경합(Lock Contention)이 없고 프레임 누수가 발생하지 않는 실시간 영상 분석 파이프라인을 운영합니다.
  - 서보모터 구동 시간 제어를 통해 도어 개폐 시스템을 관리합니다.
  - 하드웨어 SPI 기반 LED 스트립을 상태에 맞게 제어합니다. (대기 상태: 초록색, 촬영 상태: 백색, 완료 상태: 청색)
  - 보관함 문이 열린 직후 10초 동안은 사람의 손이나 신체가 오탐지되는 노이즈를 방지하기 위해 YOLO 감지를 일시 차단(`skip_detection`)하는 안전장치를 내장하고 있습니다.

---

## 서비스 설치 및 실행 방법

### 공통 환경 설정
실행 전 PostgreSQL 연결 경로 및 AI 매칭용 OpenRouter API 키를 설정해야 합니다. (필요 시 환경 변수 등록)
```bash
export DATABASE_URL="postgresql://postgres:1234@localhost:5432/lost_found_db"
export OPENROUTER_API_KEY="your-openrouter-api-key"
```

### 1. 메인 웹 및 데이터베이스 서버
```bash
cd lost_found_project
pip install -r requirements.txt
# FastAPI 서버 가동
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. VLM 조율 서버
*`vlm/Qwen3.5-9B/` 경로에 로컬 가중치 파일이 적재되어 있어야 합니다.*
```bash
cd vlm
pip install -r requirements.txt # Apple Silicon 기기 권장
# FastAPI 서버 가동
uvicorn main:app --host 0.0.0.0 --port 8080
```

### 3. RDK X5 엣지 단말 제어 서버
```bash
cd arducam_yolo_web
pip install -r requirements.txt
# Flask 하드웨어 서버 가동
python -m arducam_yolo_web.server
```

---

## 예외 처리 및 폴백 안정성 설계 (Resiliency)
* **하드웨어 통신 장애 (Fallback)**: VLM 서버가 RDK X5 엣지 단말과 통신할 수 없는 상황(통신 두절 또는 타임아웃)이 발생하면 시스템 전체가 중단되지 않고 자동 안전장치(Fallback)가 가동됩니다. 촬영에 실패한 2차 이미지 대신 모바일 기기가 직접 전송한 1차 원본 사진으로 VLM 태그 분석과 DB 이관 프로세스를 무중단 진행합니다.
* **가상 카메라 디바이스 시뮬레이터**: 물리적인 카메라 장치(`/dev/video*`)가 감지되지 않는 런타임 환경일 경우, RDK 모듈은 자동으로 시뮬레이션 모드로 전환되어 실시간 시간 정보가 렌더링되는 가상의 더미 비디오 스트림을 안전하게 복제해 제공합니다.

---

## 기여자 (Contributors)

프로젝트에 기여해 주신 팀원분들입니다. (이미지나 이름을 클릭하면 GitHub 프로필로 이동합니다.)

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/uqer1244">
        <img src="https://github.com/uqer1244.png?size=70" width="70" height="70" style="border-radius: 50%;" alt="uqer1244"/><br />
        <sub><b>uqer1244</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/leann805-crypto">
        <img src="https://github.com/leann805-crypto.png?size=70" width="70" height="70" style="border-radius: 50%;" alt="leann805-crypto"/><br />
        <sub><b>leann805-crypto</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Parkjihooo">
        <img src="https://github.com/Parkjihooo.png?size=70" width="70" height="70" style="border-radius: 50%;" alt="Parkjihooo"/><br />
        <sub><b>Parkjihooo</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/yeonseung321">
        <img src="https://github.com/yeonseung321.png?size=70" width="70" height="70" style="border-radius: 50%;" alt="yeonseung321"/><br />
        <sub><b>yeonseung321</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/yyh1113">
        <img src="https://github.com/yyh1113.png?size=70" width="70" height="70" style="border-radius: 50%;" alt="yyh1113"/><br />
        <sub><b>yyh1113</b></sub>
      </a>
    </td>
  </tr>
</table>
