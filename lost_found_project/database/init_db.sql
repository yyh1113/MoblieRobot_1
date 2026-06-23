-- Enable standard trigram extension for fast textual similarity queries (GIN index)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. Table: lost_items (습득물 보관 및 하드웨어 연동 테이블)
CREATE TABLE IF NOT EXISTS lost_items (
    id SERIAL PRIMARY KEY,
    management_number VARCHAR(50) UNIQUE NOT NULL, -- Format: L-YYYYMMDD-XXXX
    category VARCHAR(100) NOT NULL,                -- e.g., 전자기기, 지갑
    sub_category VARCHAR(100) NOT NULL,            -- e.g., 스마트폰, 카드지갑
    item_name VARCHAR(255) NOT NULL,               -- 물품 이름
    found_date DATE NOT NULL,                      -- 습득 날짜
    found_location_building VARCHAR(100) NOT NULL, -- 발견 건물 (e.g., 미래창조관)
    found_location_detail VARCHAR(255) NOT NULL,   -- 발견 상세 위치 (e.g., 3층 로비 테이블)
    detail_memo TEXT,                              -- 상세 메모 (특이사항)
    thumbnail_path VARCHAR(255) NOT NULL,          -- 가로 400px 압축 썸네일 경로
    vlm_keywords TEXT NOT NULL,                    -- VLM 형태소 분석 추출 키워드셋 (콤마/공백 구분)
    status VARCHAR(20) DEFAULT '보관중' CHECK (status IN ('보관중', '수령완료')),
    
    -- 자율 수령 이력 추적용 필드 (Released information)
    recipient_name VARCHAR(50),
    recipient_phone VARCHAR(20),
    recipient_student_id VARCHAR(20),
    released_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Table: lost_reports (분실 신고 및 AI 매칭 연동 테이블)
CREATE TABLE IF NOT EXISTS lost_reports (
    id SERIAL PRIMARY KEY,
    report_number VARCHAR(50) UNIQUE NOT NULL,      -- Format: R-YYYYMMDD-XXXX
    category VARCHAR(100) NOT NULL,                 -- 분실 카테고리
    item_name VARCHAR(255) NOT NULL,                -- 분실 물품명
    start_date DATE NOT NULL,                       -- 분실 시작일 범위
    end_date DATE NOT NULL,                         -- 분실 종료일 범위
    lost_building VARCHAR(100) NOT NULL,            -- 분실 추정 건물
    lost_detail VARCHAR(255) NOT NULL,              -- 분실 추정 상세 위치
    unique_features TEXT NOT NULL,                  -- 분실자 자연어 특이사항 본문
    
    -- 신고자 정보
    reporter_name VARCHAR(50) NOT NULL,
    reporter_phone VARCHAR(20) NOT NULL,
    reporter_student_id VARCHAR(20) NOT NULL,
    report_time_clock TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 매칭 제어 플래그 및 매칭 브릿지
    matching_status VARCHAR(20) DEFAULT '매칭대기' CHECK (matching_status IN ('매칭대기', '매칭완료')),
    matched_lost_item_id INTEGER REFERENCES lost_items(id) ON DELETE SET NULL,
    image_path VARCHAR(255),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2.5 Table: excluded_matches (분실 신고별 매칭 제외 습득물 이력 관리)
CREATE TABLE IF NOT EXISTS excluded_matches (
    report_id INTEGER REFERENCES lost_reports(id) ON DELETE CASCADE,
    lost_item_id INTEGER REFERENCES lost_items(id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, lost_item_id)
);

-- 3. GIN Performance Indexes for Accelerated Keyword Searching
CREATE INDEX IF NOT EXISTS idx_lost_items_vlm_keywords_gin ON lost_items USING gin (vlm_keywords gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_lost_reports_unique_features_gin ON lost_reports USING gin (unique_features gin_trgm_ops);
