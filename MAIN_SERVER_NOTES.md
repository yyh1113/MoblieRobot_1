# Main Server Notes From Screenshots

These notes summarize the partial FastAPI main-server code shown in screenshots.
They are context for aligning the Android app; they are not a complete server source.

## Stack and structure

- FastAPI `APIRouter`
- Jinja2 admin pages
- PostgreSQL through `asyncpg` and `get_db_pool`
- Matching functions:
  - `calculate_llm_match_case`
  - `search_found_items_by_android_request`
- Imported request schemas:
  - `ReleaseRequest`
  - `MatchConfirmRequest`
  - `AndroidSearchRequest`
- Thumbnail directory: `static/thumbnails`

## Authentication

- Admin authentication uses an `admin_session` cookie.
- Unauthenticated admin requests redirect to `/admin/login` with HTTP 303/307.
- The screenshots contain insecure default credentials and a hard-coded session token.
  Their literal values are intentionally not copied here and should be replaced with
  secure environment configuration.

## Admin routes shown

- `GET /` -> redirect to `/admin/login`
- `GET /admin` -> redirect to `/admin/lost-items`
- `GET /admin/login`
- `POST /admin/login` using form fields `username`, `password`
- `GET /admin/logout`
- `GET /admin/lost-items`
  - Filters: `category`, `status_filter`
  - Reads from `lost_items`
- `GET /admin/lost-items/{item_id}`
- `POST /admin/lost-items/{item_id}/release`
  - Form fields: `recipient_name`, `recipient_phone`, `recipient_student_id`
  - Updates item status to `수령완료`
  - Saves recipient data and `released_at`
- `GET /admin/lost-reports`
  - Filters: `category`, `matching_status`
- `GET /admin/lost-reports/{report_id}`
  - Runs `calculate_llm_match_case(report_id, db_pool)`
- `POST /admin/lost-reports/{report_id}/match-confirm`
  - Form field: `lost_item_id`
  - Marks the item `수령완료`
  - Copies reporter identity into recipient fields
  - Marks report `매칭완료` and sets `matched_lost_item_id`
- `GET /admin/lost-reports/{report_id}/compare/{item_id}`
  - Recalculates and displays match information

## Database fields observed

### `lost_items`

- `id`
- `management_number`
- `category`
- `sub_category`
- `item_name`
- `found_date`
- `found_location_building`
- `found_location_detail`
- `detail_memo`
- `thumbnail_path`
- `vlm_keywords`
- `status`
- `recipient_name`
- `recipient_phone`
- `recipient_student_id`
- `released_at`

### `lost_reports`

- `id`
- `report_number`
- `category`
- `item_name`
- `start_date`
- `end_date`
- `lost_building`
- `lost_detail`
- `unique_features`
- `reporter_name`
- `reporter_phone`
- `reporter_student_id`
- `report_time_clock`
- `matching_status`
- `matched_lost_item_id`

## Matching behavior observed

- The report detail page runs `calculate_llm_match_case`.
- Candidate `match_rate` is used when available.
- A keyword-overlap fallback computes a percentage.
- The fallback score is explicitly capped at `95` using:
  - `match_rate = min(match_rate, 95)`
- Highlight labels include:
  - `물품 분류 일치`
  - `색상 일치`
  - `장소 일치` / `장소 유사`
  - `특이사항 유사`
  - fallback `카테고리 연관`

## Android integration gap visible in screenshots

The screenshots still do not show these Android-facing routes currently used by the app:

- `POST /api/lost-reports`
- `POST /api/admin-approval-requests`

They must either be added to the server or the Android endpoints/payloads must be
changed to match existing server routes. Existing `/admin/...` routes are browser
form routes that redirect and should not be treated as JSON Android APIs.

## Additional routes shown later

### Excluding an incorrect match

- `POST /admin/lost-reports/{report_id}/exclude`
- Form field: `lost_item_id`
- Inserts `(report_id, lost_item_id)` into `excluded_matches`.
- Uses `ON CONFLICT DO NOTHING` and redirects back to the report detail page.

### Saving a found item from VLM/temi

- `POST /api/save-found-item`
- Content type: `multipart/form-data`
- Required form/file fields:
  - `category`
  - `sub_category`
  - `item_name`
  - `found_date` (`YYYYMMDD` or `YYYY-MM-DD`)
  - `found_location_building`
  - `found_location_detail`
  - `vlm_keywords`
  - `thumbnail` file
- Optional field: `detail_memo`
- Invalid dates fall back to the server's current date.
- Generates management numbers in `L-YYYYMMDD-XXXX` format by counting items
  registered for the same `found_date`.
- Saves the thumbnail under `static/thumbnails` as:
  - `thumb_{management_number}{extension}`
- Inserts the item into `lost_items` with status `보관중`.
- Success response:
  - HTTP 200
  - `status: success`
  - `item_id`
  - `management_number`
  - `thumbnail_path: /static/thumbnails/{filename}`
- Error response: HTTP 500 with `status: error` and `message`.

Potential path inconsistency to verify: the shown insert appears to pass only
`save_filename` into the DB `thumbnail_path` column, while the API response returns
`/static/thumbnails/{save_filename}`. Search responses must normalize this before
the Android app downloads the image.

### Android search

- `POST /api/search-items`
- JSON body schema: `AndroidSearchRequest`
- Calls `search_found_items_by_android_request(req_dict, db_pool)`.
- Success response (HTTP 200):
  - `status`
  - `phase`
  - `query` from request `detail`
  - `keywords`
  - `results`
- Error response: HTTP 500 with `status: error` and `message`.

### Android confirmation and locker relay

The same handler, `api_confirm_relay`, is registered for all of these aliases:

- `POST /api/locker/open`
- `GET /api/locker/open`
- `POST /api/confirm`
- `GET /api/confirm`

It merges input from query parameters, JSON, and form data.

Accepted item identity aliases:

- `lost_item_id`
- `item_id`
- `itemId`
- `id`
- `management_number`
- `managementNumber`

Accepted recipient aliases:

- Name: `recipient_name` or `claimantName`
- Phone: `recipient_phone` or `claimantPhone`
- Student number:
  - `recipient_student_id`
  - `claimantStudentNumber`
  - `claimantStudentId`

DB behavior:

- Finds an item by numeric ID first, then management number.
- Updates `lost_items.status` to `수령완료`.
- Sets `released_at = CURRENT_TIMESTAMP`.
- Stores recipient identity fields.
- Uses `안드로이드 키오스크` as the fallback recipient name.

Relay behavior:

- Target is `payload.target_ip`, otherwise environment `TAILSCALE_IP`, otherwise
  the hard-coded fallback IP shown in source.
- Optional `relay_url` can override the target URL.
- Default relay URL: `http://{target_ip}/api/door/open`
- Sends a GET request with the Android payload as query parameters.
- Relay timeout: 5 seconds.

Confirmation response is always HTTP 200 unless the handler itself throws:

- `status`: `success` when either DB update or relay succeeds, otherwise `warning`
- `message`
- `db_updated`
- `relay_success`
- `relay_info`

Important Android implication: checking only HTTP 200 is insufficient. The app
should inspect `status`, `db_updated`, and especially `relay_success` before showing
the locker as physically opened.
