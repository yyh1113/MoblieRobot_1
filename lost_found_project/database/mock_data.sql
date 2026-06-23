-- 1. Insert initial mock data for lost_items (Found Items)
-- (We use hardcoded placeholder image files. In the actual app, these are written to static/thumbnails/)

INSERT INTO lost_items (
    management_number, category, sub_category, item_name, found_date, 
    found_location_building, found_location_detail, detail_memo, 
    thumbnail_path, vlm_keywords, status
) VALUES 
(
    'L-20260608-0001', '전자기기', '스마트폰', '갤럭시 S24 울트라', '2026-06-08', 
    '미래창조관', '3층 로비 테이블 위', '액정에 아주 미세한 스크래치 있음. 뒷면에 투명 젤리 케이스 장착됨.', 
    'thumb_s24.jpg', '갤럭시, 삼성, 스마트폰, 회색, 그레이, 젤리케이스', '보관중'
),
(
    'L-20260608-0002', '지갑', '반지갑', '구찌 마몽 가죽 카드지갑', '2026-06-08', 
    '학술정보관', '4층 노트북석 일반 열람대', '검은색 가죽 카드지갑. 학생증(김민수) 및 소액의 현금 동봉.', 
    'thumb_gucci.jpg', '지갑, 구찌, 블랙, 검정색, 가죽, 카드지갑', '보관중'
),
(
    'L-20260607-0001', '전자기기', '무선이어폰', '에어팟 프로 2세대', '2026-06-07', 
    '제1과학기술관', '212호 강의실 뒤편', '흰색 에어팟 프로 2세대 본체와 유닛. 본체에 분홍색 실리콘 케이스와 키링 부착.', 
    'thumb_airpods.jpg', '에어팟, 애플, 무선이어폰, 흰색, 실리콘케이스, 분홍색, 키링', '보관중'
),
(
    'L-20260605-0001', '의류', '아우터', '나이키 검은색 바람막이', '2026-06-05', 
    '체육관', '관중석 3열 중간 좌석', 'L 사이즈 나이키 스포츠 바람막이. 지퍼 부분이 흰색이며 안쪽에 이름표 없음.', 
    'thumb_nike.jpg', '나이키, 바람막이, 아우터, 블랙, 검은색, 스포츠웨어, 바람막이', '수령완료'
);

-- Update released information for the completed item
UPDATE lost_items 
SET recipient_name = '박수령',
    recipient_phone = '010-9999-8888',
    recipient_student_id = '2022098765',
    released_at = '2026-06-06 14:30:00'
WHERE management_number = 'L-20260605-0001';


-- 2. Insert initial mock data for lost_reports (Lost Reports Filed by Owners)
INSERT INTO lost_reports (
    report_number, category, item_name, start_date, end_date, 
    lost_building, lost_detail, unique_features, 
    reporter_name, reporter_phone, reporter_student_id, 
    matching_status, matched_lost_item_id
) VALUES
(
    'R-20260608-0001', '전자기기', '삼성 갤럭시 폰', '2026-06-08', '2026-06-08',
    '미래창조관', '3층 전선 주변 테이블', '회색 갤럭시 스마트폰입니다. 뒤에 다 닳은 투명 젤리 케이스가 씌워져 있고 액정에 작은 흠집이 있습니다.',
    '홍길동', '010-1234-5678', '2021012345',
    '매칭대기', NULL
),
(
    'R-20260609-0001', '지갑', '구찌 가죽지갑', '2026-06-07', '2026-06-09',
    '학술정보관', '4층 열람실 혹은 3층', '검은색 구찌 카드 지갑인데 가죽으로 되어있습니다. 안에 에리카 학생증 김민수 카드가 들어있습니다.',
    '김민수', '010-5678-1234', '2020123456',
    '매칭대기', NULL
),
(
    'R-20260608-0002', '전자기기', '아이폰 15', '2026-06-08', '2026-06-08',
    '컨퍼런스홀', '1층 로비', '분홍색 아이폰 15 기종이고 케이스는 없습니다.',
    '이영희', '010-4444-5555', '2023055555',
    '매칭대기', NULL
),
(
    'R-20260605-0001', '의류', '나이키 바람막이', '2026-06-05', '2026-06-05',
    '체육관', '관중석 부근', '검은색 나이키 바람막이이고 지퍼 부분이 흰색 포인트가 들어가 있는 겉옷입니다.',
    '박지성', '010-8888-7777', '2022098765',
    '매칭완료', 4
);
