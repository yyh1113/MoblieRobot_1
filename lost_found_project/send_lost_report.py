import io
import requests
from PIL import Image

def send_dummy_lost_reports():
    # 메인 서버 주소 (로컬 또는 원격 IP로 설정해서 사용하세요)
    # 로컬 테스트 시: "http://localhost:8000/api/lost-reports"
    # 배포 서버 테스트 시: "http://115.136.116.86:8000/api/lost-reports"
    server_url = "http://localhost:8000/api/lost-reports"

    # 1. 분실물 이미지 전송 테스트를 위한 더미 이미지 생성 (Pillow)
    img = Image.new("RGB", (600, 600), color=(220, 100, 100))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    # 2. VLM 습득물 더미데이터와 매칭될 만한 분실 신고 데이터 정의
    dummy_reports = [
        {
            "category": "전자기기",
            "item_name": "아이패드 프로",
            "start_date": "2026-06-20",
            "end_date": "2026-06-22",
            "lost_building": "학술정보관",
            "lost_detail": "2층 노트북 열람실 자리 근처",
            "unique_features": "스페이스 그레이 색상이고 투명 젤리 케이스가 끼워져 있습니다. 뒷면에 노란색 별 스티커가 붙어있는 것이 특징입니다.",
            "reporter_name": "홍길동",
            "reporter_phone": "010-1234-5678",
            "reporter_student_id": "2021000123",
            "report_time_clock": "2026-06-22T18:10:00+09:00",
            "matching_status": "매칭대기",
        },
        {
            "category": "지갑",
            "item_name": "마르지엘라 지갑",
            "start_date": "2026-06-21",
            "end_date": "2026-06-22",
            "lost_building": "미래창조관",
            "lost_detail": "1층 편의점 옆 의자",
            "unique_features": "검은색 가죽 재질의 카드지갑입니다. 뒷면에 마르지엘라 시그니처인 하얀색 실 스티치 4개가 있습니다. 내부에 학생증이 들어있습니다.",
            "reporter_name": "김철수",
            "reporter_phone": "010-9876-5432",
            "reporter_student_id": "2022000456",
            "report_time_clock": "2026-06-22T18:12:00+09:00",
            "matching_status": "매칭대기",
        }
    ]

    for i, report in enumerate(dummy_reports):
        print(f"\n🚀 [{i+1}/{len(dummy_reports)}] 분실 신고 전송 시작: '{report['item_name']}'...")

        # multipart/form-data 형식으로 전송하기 위해 파일 객체 지정
        files = {"image": ("lost_dummy_photo.jpg", img_bytes, "image/jpeg")}

        try:
            # POST 요청 전송
            response = requests.post(
                server_url, data=report, files=files, timeout=30
            )

            if response.status_code == 200:
                print("[Success] Transmitted successfully! Server response:")
                print(response.json())
            else:
                print(f"[Failure] Transmission failed (Status code: {response.status_code})")
                print(response.text)

        except Exception as e:
            print(f"[Error] Exception occurred during communication: {e}")

if __name__ == "__main__":
    send_dummy_lost_reports()
