# Temi Lost & Found

temi 로봇의 터치스크린에서 사용할 수 있는 분실물 수거/회수 Android 앱입니다. 학교 안에서 습득물을 등록하고, 분실자가 조건과 키워드로 물건을 검색한 뒤 서버 매칭 결과에 따라 수령 또는 관리자 문의로 이어지는 흐름을 구현했습니다.

## 주요 기능

- temi 태블릿 가로 화면 전용 UI
- 습득물 등록: 정보 입력, 카메라 촬영 또는 촬영 생략, multipart/form-data 전송
- 분실물 찾기: 카테고리, 날짜, 장소, 키워드 기반 서버 검색
- 매칭률 분기: 50% 이상은 후보 확인 및 본인 확인, 50% 미만은 전화걸기 또는 새 분실신고
- 분실 신고: 검색 실패 또는 낮은 매칭률 상황에서 신고 정보 POST 전송
- 음성 입력: temi SDK 음성 인식 우선 사용, 실패 시 Android 음성 인식으로 fallback
- 수령 처리: 보관함 잠금 해제 요청을 메인 서버로 전송

## 화면 흐름

### 습득물 등록

1. 대기 화면
2. 습득물 등록 안내
3. 습득물 정보 입력
4. 카메라 촬영 또는 촬영 생략
5. 입력 정보 확인
6. 서버 전송
7. 등록 완료 후 홈 복귀

### 분실물 찾기

1. 대기 화면
2. 분실물 찾기 안내
3. 검색 조건 입력
4. 서버 검색 및 AI 매칭
5. 후보 확인 또는 관리자 전화/분실 신고
6. 본인 확인
7. 보관함 잠금 해제 요청
8. 수령 완료 후 홈 복귀

## 서버 연동

현재 앱은 `local.properties`에 적은 서버 주소를 Gradle `BuildConfig`로 주입합니다. `local.properties`는 `.gitignore`에 포함되어 GitHub에 올라가지 않습니다.

```properties
# local.properties
FOUND_API_BASE_URL=https://your-vlm-server.example.com
SEARCH_API_BASE_URL=http://your-main-server.example.com:8000
```

처음 설정할 때는 `local.properties.example`을 `local.properties`로 복사한 뒤 각자 환경에 맞게 값을 수정하면 됩니다.

값을 넣지 않으면 기본값은 AVD 로컬 개발용 주소인 `http://10.0.2.2:8080`, `http://10.0.2.2:8000`입니다.

### 습득물 등록

```text
POST /api/found-items
Content-Type: multipart/form-data
```

전송 필드:

- `category`
- `subCategory`
- `itemName`
- `foundLocation`
- `foundBuilding`
- `foundLocationDetail`
- `detail`
- `foundAt`
- `image`

### 분실물 검색

```text
POST /api/search-items
Content-Type: application/json
```

예시 요청:

```json
{
  "phase": "explore",
  "category": "전자기기",
  "subCategory": "이어폰",
  "lostStartDate": "2026-06-23",
  "lostEndDate": "2026-06-23",
  "lostLocation": "기숙사",
  "detail": "검은색 이어폰 케이스",
  "imageSkipped": true
}
```

### 수령 확인 및 보관함 열림 요청

```text
POST /api/locker/open
Content-Type: application/json
```

서버는 이 요청을 받아 DB 상태를 `수령완료`로 갱신하고, 보관함 제어 장치로 열림 신호를 전달하는 구조를 가정합니다.

## 개발 환경

- Android Studio
- Java
- Android Gradle Plugin 4.1.3
- Gradle Wrapper 6.5
- compileSdkVersion 30
- minSdkVersion 23
- robotemi SDK 1.137.1

## 실행 방법

1. Android Studio에서 이 폴더를 엽니다.
2. Gradle Sync를 실행합니다.
3. `app` 모듈을 선택해 실행합니다.

temi와 유사한 화면으로 확인하려면 AVD를 태블릿 해상도로 만들고 가로 방향으로 실행합니다.

추천 AVD:

- Pixel Tablet
- Nexus 10
- 10.1" WXGA Tablet

## 권한

앱에서 사용하는 주요 권한은 다음과 같습니다.

- `CAMERA`: 습득물 사진 촬영
- `RECORD_AUDIO`: 음성 입력
- `INTERNET`: 서버 통신
- `com.robotemi.permission.meetings`: temi 관리자 통화 기능

## 저장소에 올리지 않는 파일

다음 파일과 폴더는 GitHub에 올리지 않습니다.

- Android Studio 로컬 설정: `.idea/`, `*.iml`
- Gradle 빌드 산출물: `.gradle/`, `build/`, `app/build/`
- 개인 SDK 경로: `local.properties`
- 프로젝트 참고용 강의 추출/렌더 파일: `course_extracts/`, `course_renders/`

## 참고

메인 서버와 관리자 페이지 쪽 API 구조는 [MAIN_SERVER_NOTES.md](MAIN_SERVER_NOTES.md)에 정리되어 있습니다.
