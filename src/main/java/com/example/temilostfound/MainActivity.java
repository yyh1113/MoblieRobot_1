package com.example.temilostfound;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.CountDownTimer;
import android.provider.MediaStore;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.Random;

import org.json.JSONArray;
import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final String TAG = "TemiLostFound";
    private static final int REQUEST_CAMERA_PERMISSION = 100;
    private static final int REQUEST_CAPTURE_IMAGE = 101;
    private static final int REQUEST_AUDIO_PERMISSION = 102;
    private static final int REQUEST_VOICE_INPUT = 103;
    // Found item registration phase: Android app -> VLM server -> main server.
    private static final String API_BASE_URL = normalizeBaseUrl(BuildConfig.FOUND_API_BASE_URL);
    private static final String FOUND_ITEM_ENDPOINT = API_BASE_URL + "/api/found-items";
    // Lost item search phase: Android app -> search/main server -> LLM -> DB -> Android app.
    private static final String SEARCH_API_BASE_URL = normalizeBaseUrl(BuildConfig.SEARCH_API_BASE_URL);
    private static final String SEARCH_ITEM_ENDPOINT = SEARCH_API_BASE_URL + "/api/search-items";
    private static final String LOCKER_OPEN_ENDPOINT = SEARCH_API_BASE_URL + "/api/locker/open";
    private static final String LOST_REPORT_ENDPOINT = SEARCH_API_BASE_URL + "/api/lost-reports";
    private static final int SEARCH_CONNECT_TIMEOUT_MS = 15000;
    private static final int SEARCH_READ_TIMEOUT_MS = 90000;
    private static final int SEARCH_IMAGE_READ_TIMEOUT_MS = 120000;

    private static String normalizeBaseUrl(String value) {
        if (value == null) {
            return "";
        }
        String trimmed = value.trim();
        while (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }

    private static final int BLUE = Color.rgb(37, 143, 219);
    private static final int TEXT = Color.rgb(50, 50, 50);
    private static final int MUTED = Color.rgb(115, 115, 115);
    private static final int BG = Color.WHITE;

    private FrameLayout screen;
    private LinearLayout root;
    private Bitmap capturedItemImage;
    private Bitmap lostReportImage;
    private EditText voiceTargetInput;
    private boolean temiVoiceListening = false;
    private final com.robotemi.sdk.Robot.AsrListener temiAsrListener = (text, language) ->
            runOnUiThread(() -> handleTemiVoiceResult(text));
    private boolean captureForLostReport = false;
    private boolean captureForLostReportForm = false;
    private boolean lostReportFromSimilarMatch = false;
    private String foundCategory = "";
    private String foundSubCategory = "";
    private String foundDate = "";
    private String foundItemName = "";
    private String foundBuilding = "";
    private String foundLocationDetail = "";
    private String foundDetail = "";
    private String searchCategory = "";
    private String searchSubCategory = "";
    private String searchStartDate = "";
    private String searchEndDate = "";
    private String searchBuilding = "";
    private String searchLocationDetail = "";
    private String searchDetail = "";
    private String lostItemCategory = "";
    private String lostItemSubCategory = "";
    private String lostItemStartDate = "";
    private String lostItemEndDate = "";
    private String lostItemBuilding = "";
    private String lostItemLocationDetail = "";
    private String lostItemDetail = "";
    private String lostItemName = "";
    private String lostReportRequestNumber = "";
    private String claimantName = "";
    private String claimantPhone = "";
    private String claimantStudentNumber = "";
    private String activeLockerNumber = "A-7";
    private FoundItemCandidate latestCandidate;

    private final String[] majorCategories = {
            "물품 분류 선택", "가방", "지갑", "전자기기", "카드/신분증", "의류", "우산", "기타"
    };
    private final String[] minorCategories = {
            "세부 분류 선택", "숄더백", "반지갑", "충전기", "스마트폰", "이어폰", "학생증", "카드", "기타"
    };
    private final String[] buildings = {
            "학교 건물 선택", "학생복지시설", "공학관", "도서관", "강의동", "체육관", "기숙사"
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        showIdle();
    }

    private void showIdle() {
        base();
        LinearLayout row = horizontal();
        row.setGravity(Gravity.CENTER);
        row.addView(bigCard("습득물", "주인을\n찾아요", v -> showFoundGuide()), weight(1, 0, 14));
        row.addView(bigCard("분실물", "물건을\n잃어버렸어요", v -> showLostGuide()), weight(1, 14, 0));
        root.addView(row, fillArea());
    }

    private void showLostGuide() {
        base();
        title("분실물은 이렇게 찾아요");
        LinearLayout row = horizontal();
        row.addView(stepCard("1단계", "분실물 검색"), weight(1, 0, 12));
        row.addView(stepCard("2단계", "본인 확인"), weight(1, 12, 12));
        row.addView(stepCard("3단계", "수령 완료"), weight(1, 12, 0));
        root.addView(row, fillArea());
        bottomButton("분실물 찾기", v -> showSearchForm());
        backButton(v -> showIdle());
    }

    private void showSearchForm() {
        base();
        title("어떤 물건을 잃어버리셨나요?");

        LinearLayout form = formContainer();
        Spinner category = spinner(majorCategories);
        Spinner subCategory = spinner(minorCategories);
        Spinner building = spinner(buildings);
        EditText startDate = input(today());
        EditText endDate = input(today());
        EditText placeDetail = input("예) 1층 화장실, 302호 강의실");
        EditText detail = input("예) 갤럭시 s24 울트라, 검은색 가방, 개구리 키링");

        form.addView(formLine("물품 분류", category, subCategory));
        form.addView(formLine("분실 기간", startDate, endDate));
        form.addView(formLine("분실 장소", building, placeDetail));
        form.addView(formLine("키워드", detail, null));

        LinearLayout voiceButtons = horizontal();
        voiceButtons.setGravity(Gravity.CENTER);
        voiceButtons.addView(grayButton("키워드 말하기", v -> openVoiceInput(detail)), voiceButtonParams());
        voiceButtons.addView(grayButton("장소 말하기", v -> openVoiceInput(placeDetail)), voiceButtonParams());
        form.addView(voiceButtons, matchWrapWithMargin(0, 18, 0, 0));

        root.addView(form, fillArea());

        bottomButton("검색하기", v -> {
            String selected = category.getSelectedItem().toString();
            if ("물품 분류 선택".equals(selected)) {
                toast("물품 분류를 선택해 주세요.");
                return;
            }
            if (detail.getText().toString().trim().isEmpty()) {
                toast("검색할 물건의 키워드나 특징을 입력해 주세요.");
                return;
            }
            saveSearchInputs(category, subCategory, startDate, endDate, building, placeDetail, detail);
            requestSearchItems(false, searchDetail);
        });
        backButton(v -> showLostGuide());
    }

    private void saveSearchInputs(Spinner category, Spinner subCategory, EditText startDate, EditText endDate,
                                  Spinner building, EditText placeDetail, EditText detail) {
        searchCategory = category.getSelectedItem().toString();
        searchSubCategory = subCategory.getSelectedItem().toString();
        if ("세부 분류 선택".equals(searchSubCategory)) {
            searchSubCategory = "";
        }
        searchStartDate = startDate.getText().toString().trim();
        searchEndDate = endDate.getText().toString().trim();
        searchBuilding = building.getSelectedItem().toString();
        if ("학교 건물 선택".equals(searchBuilding)) {
            searchBuilding = "";
        }
        searchLocationDetail = placeDetail.getText().toString().trim();
        searchDetail = detail.getText().toString().trim();
    }

    private void showSearchResult(boolean hasItem) {
        showSearchResult(hasItem ? 2 : 0);
    }

    private void showSearchResult(int itemCount) {
        base();
        if (itemCount > 0) {
            title("해당 조건에 분실물이 있습니다");
            subtitle("목록은 공개하지 않아요.\n특이사항을 입력하면 LLM이 보관 중인 물품과 비교합니다.");

            LinearLayout form = formContainer();
            EditText detail = input("예) 검은색, 나이키, 안쪽에 스티커, 키링");
            if (!searchDetail.isEmpty()) {
                detail.setText(searchDetail);
            }
            form.addView(formLine("물건 특이사항", detail, null));
            LinearLayout voiceButtons = horizontal();
            voiceButtons.setGravity(Gravity.CENTER);
            voiceButtons.addView(grayButton("특징 말하기", v -> openVoiceInput(detail)), voiceButtonParams());
            form.addView(voiceButtons, matchWrapWithMargin(0, 18, 0, 0));
            root.addView(form, fillArea());

            bottomButton("탐색하기", v -> showExploreLoading(detail.getText().toString()));
        } else {
            showLowMatchOptions(0);
            return;
        }
        backButton(v -> showSearchForm());
    }

    private void showExploreLoading(String detail) {
        base();
        title("탐색 중");
        subtitle("LLM이 입력한 특이사항과 보관 중인 분실물을 비교하고 있습니다.");
        TextView status = label("분류 / 색상 / 브랜드 / 특징 분석 중", 34, true);
        status.setTextColor(BLUE);
        status.setGravity(Gravity.CENTER);
        root.addView(status, fillArea());
        requestSearchItems(true, detail);
        backButton(v -> showSearchResult(true));
    }

    private void requestSearchItems(boolean includeDetail, String detail) {
        new Thread(() -> {
            try {
                SearchResponse response = requestSearchItemsAsJson(includeDetail, detail);
                runOnUiThread(() -> {
                    latestCandidate = response.candidate;
                    if (includeDetail) {
                        toast("서버 유사도: " + response.score + "%");
                        showExploreResult(response.score);
                    } else {
                        toast("서버 후보 수: " + response.count + "건");
                        showSearchResult(response.count);
                    }
                });
            } catch (java.net.SocketTimeoutException e) {
                Log.e(TAG, "Search server timeout", e);
                runOnUiThread(() -> toast("검색 분석 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."));
            } catch (Exception e) {
                Log.e(TAG, "Search server request failed", e);
                runOnUiThread(() -> toast("검색 서버 연결 오류: " + e.getClass().getSimpleName()
                        + " " + String.valueOf(e.getMessage())));
            }
        }).start();
    }

    private SearchResponse requestSearchItemsAsJson(boolean includeDetail, String detail) throws java.io.IOException {
        java.net.URL url = new java.net.URL(SEARCH_ITEM_ENDPOINT);
        java.net.HttpURLConnection conn = openTrustedConnection(url);
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(SEARCH_CONNECT_TIMEOUT_MS);
        conn.setReadTimeout(SEARCH_READ_TIMEOUT_MS);
        conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
        conn.setRequestProperty("Accept", "application/json");
        conn.setDoOutput(true);

        String json = searchRequestJson(includeDetail, detail, true);
        Log.d(TAG, "Search request: " + json);
        java.io.OutputStream output = conn.getOutputStream();
        output.write(json.getBytes("UTF-8"));
        output.flush();
        output.close();

        int responseCode = conn.getResponseCode();
        String body = readResponseBody(conn, responseCode);
        Log.d(TAG, "Search response " + responseCode + ": " + body);
        conn.disconnect();
        if (responseCode < 200 || responseCode >= 300) {
            throw new java.io.IOException("HTTP " + responseCode);
        }
        return parseSearchResponse(body, includeDetail);
    }

    private SearchResponse requestSearchItemsWithImage(boolean includeDetail, String detail) throws java.io.IOException {
        String boundary = "----TemiSearchBoundary" + System.currentTimeMillis();
        java.net.URL url = new java.net.URL(SEARCH_ITEM_ENDPOINT);
        java.net.HttpURLConnection conn = openTrustedConnection(url);
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(SEARCH_CONNECT_TIMEOUT_MS);
        conn.setReadTimeout(SEARCH_IMAGE_READ_TIMEOUT_MS);
        conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        conn.setRequestProperty("Accept", "application/json");
        conn.setDoOutput(true);

        String payload = searchRequestJson(includeDetail, detail, false);
        Log.d(TAG, "Search multipart payload: " + payload);
        java.io.OutputStream output = conn.getOutputStream();
        writeMultipartField(output, boundary, "payload", payload);
        writeMultipartField(output, boundary, "category", valueOr(searchCategory, ""));
        writeMultipartField(output, boundary, "subCategory", valueOr(searchSubCategory, ""));
        writeMultipartField(output, boundary, "lostStartDate", valueOr(searchStartDate, today()));
        writeMultipartField(output, boundary, "lostEndDate", valueOr(searchEndDate, today()));
        writeMultipartField(output, boundary, "lostLocation", searchLocationText());
        writeMultipartField(output, boundary, "detail", valueOr(detail, ""));
        writeMultipartImage(output, boundary, "image", "lost-item.jpg", lostReportImage);
        output.write(("--" + boundary + "--\r\n").getBytes("UTF-8"));
        output.flush();
        output.close();

        int responseCode = conn.getResponseCode();
        String body = readResponseBody(conn, responseCode);
        Log.d(TAG, "Search multipart response " + responseCode + ": " + body);
        conn.disconnect();
        if (responseCode < 200 || responseCode >= 300) {
            throw new java.io.IOException("HTTP " + responseCode);
        }
        return parseSearchResponse(body, includeDetail);
    }

    private void showExploreResult(int score) {
        if (score >= 50) {
            showMatchedItemConfirm(score);
            return;
        }
        showLowMatchOptions(score);
    }

    private void showLowMatchOptions(int score) {
        base();
        title("일치하는 분실물을 찾지 못했어요");
        TextView desc = label("관리자에게 전화하거나 새로 분실 신고를 등록해 주세요.", 28, true);
        desc.setTextColor(MUTED);
        desc.setGravity(Gravity.CENTER);
        root.addView(desc, fillArea());

        TextView scoreView = label("검색 유사율 " + score + "%", 26, true);
        scoreView.setTextColor(BLUE);
        scoreView.setGravity(Gravity.CENTER);
        root.addView(scoreView, matchWrapWithMargin(0, 0, 0, 20));

        LinearLayout buttons = horizontal();
        buttons.setGravity(Gravity.CENTER);
        buttons.addView(grayButton("temi 앱으로 전화걸기", v -> callTemiAdmin()), dualButton());
        buttons.addView(primaryButton("새로 분실신고하기", v -> startNewLostReport()), dualButton());
        root.addView(buttons, lowerArea());
        backButton(v -> showSearchResult(true));
    }

    private void startNewLostReport() {
        lostReportFromSimilarMatch = false;
        lostItemCategory = "";
        lostItemSubCategory = "";
        lostItemStartDate = "";
        lostItemEndDate = "";
        lostItemBuilding = "";
        lostItemLocationDetail = "";
        lostItemDetail = "";
        lostItemName = "";
        lostReportRequestNumber = "";
        lostReportImage = null;
        claimantName = "";
        claimantPhone = "";
        claimantStudentNumber = "";
        showLostReportForm();
    }

    private void callTemiAdmin() {
        callTemiAdminByTelepresence();
    }

    private void callTemiAdminByTelepresence() {
        try {
            com.robotemi.sdk.Robot robot = com.robotemi.sdk.Robot.getInstance();
            com.robotemi.sdk.UserInfo admin = robot.getAdminInfo();
            if (admin == null || admin.getUserId() == null || admin.getUserId().trim().isEmpty()) {
                toast("전화 앱과 temi 관리자 계정을 모두 찾지 못했습니다.");
                return;
            }

            String callId = robot.startTelepresence(admin.getName(), admin.getUserId());
            Log.d(TAG, "temi admin telepresence started: " + callId);
            showAdminCallStarted(admin.getName());
        } catch (Exception e) {
            Log.e(TAG, "Failed to call temi admin", e);
            toast("관리자 통화 기능을 실행하지 못했습니다.");
        }
    }

    private void showAdminCallStarted(String adminName) {
        base();
        title("관리자에게 연결하고 있어요");
        subtitle(valueOr(adminName, "관리자") + "님이 응답할 때까지 잠시 기다려 주세요.");
        centerButton("통화 종료", v -> {
            com.robotemi.sdk.Robot.getInstance().stopTelepresence();
            showSearchResult(true);
        });
        backButton(v -> {
            com.robotemi.sdk.Robot.getInstance().stopTelepresence();
            showSearchResult(true);
        });
    }

    private void showMatchedItemConfirm(int score) {
        base();
        FoundItemCandidate candidate = candidateOrFallback(score);
        title("찾으시는 분실물인가요?");
        TextView desc = label("유사한 분실물을 찾았어요. 내 물건이 맞는지 확인해 주세요", 24, false);
        desc.setTextColor(MUTED);
        desc.setGravity(Gravity.CENTER);
        root.addView(desc, matchWrapWithMargin(0, 0, 0, 20));

        LinearLayout card = card();
        card.setPadding(dp(34), dp(28), dp(34), dp(28));
        LinearLayout body = horizontal();

        body.addView(candidateImageView(candidate, 260, 170),
                new LinearLayout.LayoutParams(dp(260), dp(170)));

        LinearLayout info = new LinearLayout(this);
        info.setOrientation(LinearLayout.VERTICAL);
        info.addView(label(valueOr(candidate.itemName, "후보 분실물"), 26, true), matchWrapWithMargin(0, 0, 0, 22));
        info.addView(matchInfoLine("물품분류", candidateCategoryText(candidate)));
        info.addView(matchInfoLine("습득일자", valueOr(candidate.foundDate, "확인 중")));
        info.addView(matchInfoLine("습득장소", candidateLocationText(candidate)));
        info.addView(matchInfoLine("유사율", candidate.matchRate + "%"));
        LinearLayout.LayoutParams infoParams = new LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.WRAP_CONTENT,
                1
        );
        infoParams.leftMargin = dp(32);
        body.addView(info, infoParams);
        card.addView(body, matchWrap());

        LinearLayout chips = horizontal();
        chips.setGravity(Gravity.CENTER);
        chips.addView(chip("물품 분류 일치"));
        chips.addView(chip("색상 일치"));
        chips.addView(chip("장소 유사"));
        chips.addView(chip("특이사항 유사"));
        card.addView(chips, matchWrapWithMargin(0, 22, 0, 0));

        LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(dp(710), dp(330));
        cardParams.gravity = Gravity.CENTER_HORIZONTAL;
        root.addView(card, cardParams);

        LinearLayout buttons = horizontal();
        buttons.setGravity(Gravity.CENTER);
        buttons.addView(grayButton("아니에요", v -> showLowMatchOptions(0)), dualButton());
        buttons.addView(primaryButton("네 맞아요", v -> showIdentityForm()), dualButton());
        root.addView(buttons, lowerArea());
        backButton(v -> showSearchResult(true));
    }

    private void showLostReportForm() {
        base();
        title("필요한 정보를 입력해 주세요");

        LinearLayout form = formContainer();
        TextView step = label("STEP 1. 분실물 정보", 28, true);
        form.addView(step, matchWrapWithMargin(0, 0, 0, 28));

        Spinner category = spinner(majorCategories);
        Spinner subCategory = spinner(minorCategories);
        EditText startDate = input(today());
        EditText endDate = input(today());
        Spinner building = spinner(buildings);
        EditText placeDetail = input("예) 1층 화장실, 302호 강의실");
        EditText detail = input("분실물의 색상, 패턴, 악세사리, 스티커, 오염, 재질 등 기억나는 특징을 입력해 주세요.");
        EditText itemName = input("물품명을 입력해 주세요");

        if (!lostItemName.isEmpty()) {
            setSpinnerSelection(category, lostItemCategory);
            setSpinnerSelection(subCategory, lostItemSubCategory);
            startDate.setText(valueOr(lostItemStartDate, today()));
            endDate.setText(valueOr(lostItemEndDate, today()));
            setSpinnerSelection(building, lostItemBuilding);
            placeDetail.setText(lostItemLocationDetail);
            detail.setText(lostItemDetail);
            itemName.setText(lostItemName);
        } else if (lostReportFromSimilarMatch) {
            setSpinnerSelection(category, searchCategory);
            setSpinnerSelection(subCategory, searchSubCategory);
            startDate.setText(valueOr(searchStartDate, today()));
            endDate.setText(valueOr(searchEndDate, today()));
            setSpinnerSelection(building, searchBuilding);
            placeDetail.setText(valueOr(searchLocationDetail, ""));
            detail.setText(valueOr(searchDetail, ""));
            if (latestCandidate != null) {
                itemName.setText(valueOr(latestCandidate.itemName, ""));
            }
        }

        form.addView(formLine("물품 분류", category, subCategory));
        form.addView(formLine("분실 기간", startDate, endDate));
        form.addView(formLine("분실장소", building, placeDetail));
        form.addView(formLine("특이사항", detail, null));
        form.addView(formLine("분실물명", itemName, photoButton(lostReportImage == null ? "+" : "✓", v -> {
            saveLostReportInputs(category, subCategory, startDate, endDate,
                    building, placeDetail, detail, itemName);
            captureForLostReport = true;
            captureForLostReportForm = true;
            openCamera();
        })));

        LinearLayout voiceButtons = horizontal();
        voiceButtons.setGravity(Gravity.CENTER);
        voiceButtons.addView(grayButton("분실물명 말하기", v -> openVoiceInput(itemName)), voiceButtonParams());
        voiceButtons.addView(grayButton("장소 말하기", v -> openVoiceInput(placeDetail)), voiceButtonParams());
        voiceButtons.addView(grayButton("특징 말하기", v -> openVoiceInput(detail)), voiceButtonParams());
        form.addView(voiceButtons, matchWrapWithMargin(0, 18, 0, 0));

        root.addView(form, fillArea());
        bottomButton("다음으로", v -> {
            saveLostReportInputs(category, subCategory, startDate, endDate,
                    building, placeDetail, detail, itemName);
            if ("물품 분류 선택".equals(lostItemCategory) || lostItemName.isEmpty()) {
                toast("물품 분류와 분실물명을 입력해 주세요.");
                return;
            }
            showLostReportContactForm();
        });
        backButton(v -> {
            if (lostReportFromSimilarMatch) {
                showLowMatchOptions(0);
            } else {
                showSearchResult(false);
            }
        });
    }

    private void saveLostReportInputs(Spinner category, Spinner subCategory,
                                      EditText startDate, EditText endDate,
                                      Spinner building, EditText placeDetail,
                                      EditText detail, EditText itemName) {
        lostItemCategory = category.getSelectedItem().toString();
        lostItemSubCategory = subCategory.getSelectedItem().toString();
        lostItemStartDate = startDate.getText().toString().trim();
        lostItemEndDate = endDate.getText().toString().trim();
        lostItemBuilding = building.getSelectedItem().toString();
        lostItemLocationDetail = placeDetail.getText().toString().trim();
        lostItemDetail = detail.getText().toString().trim();
        lostItemName = itemName.getText().toString().trim();
    }

    private void showLostReportContactForm() {
        base();
        title("필요한 정보를 입력해 주세요");

        LinearLayout form = formContainer();
        TextView step = label("STEP 2. 내 정보", 28, true);
        form.addView(step, matchWrapWithMargin(0, 0, 0, 28));
        EditText name = input("이름을 입력해 주세요");
        EditText phone = input("연락처를 입력해 주세요");
        EditText studentNumber = input("학번을 입력해 주세요");
        form.addView(formLine("이름", name, null));
        form.addView(formLine("연락처", phone, null));
        form.addView(formLine("학번", studentNumber, null));

        CheckBox agree = new CheckBox(this);
        agree.setText("(필수) 개인정보 수집 및 이용에 동의합니다");
        agree.setTextSize(19);
        agree.setTextColor(TEXT);
        form.addView(agree, matchWrapWithMargin(0, 8, 0, 0));

        CheckBox contactAgree = new CheckBox(this);
        contactAgree.setText("(필수) 입력한 연락처로 분실물 안내 및 관리자 연락을 받는 것에 동의합니다");
        contactAgree.setTextSize(19);
        contactAgree.setTextColor(TEXT);
        form.addView(contactAgree, matchWrapWithMargin(0, 8, 0, 0));

        root.addView(form, fillArea());

        LinearLayout row = horizontal();
        row.setGravity(Gravity.CENTER);
        row.addView(grayButton("이전으로", v -> showLostReportForm()), dualButton());
        Button submitButton = primaryButton("입력 완료", null);
        submitButton.setOnClickListener(v -> {
            if (!agree.isChecked() || !contactAgree.isChecked()) {
                toast("필수 동의가 필요합니다.");
                return;
            }
            claimantName = name.getText().toString().trim();
            claimantPhone = phone.getText().toString().trim();
            claimantStudentNumber = studentNumber.getText().toString().trim();
            if (claimantName.isEmpty() || claimantPhone.isEmpty() || claimantStudentNumber.isEmpty()) {
                toast("이름, 연락처, 학번을 모두 입력해 주세요.");
                return;
            }
            requestLostReport(submitButton);
        });
        row.addView(submitButton, dualButton());
        root.addView(row, lowerArea());
        backButton(v -> showLostReportForm());
    }

    private void requestLostReport(Button submitButton) {
        lostReportRequestNumber = "";
        submitButton.setEnabled(false);
        submitButton.setText("분실 신고 전송 중...");

        new Thread(() -> {
            java.net.HttpURLConnection conn = null;
            try {
                JSONObject payload = new JSONObject();
                payload.put("phase", "lost_report");
                payload.put("category", lostItemCategory);
                payload.put("subCategory", lostItemSubCategory);
                payload.put("itemName", lostItemName);
                payload.put("lostStartDate", lostItemStartDate);
                payload.put("lostEndDate", lostItemEndDate);
                payload.put("lostLocation", lostItemLocationText());
                payload.put("lostBuilding", lostItemBuilding);
                payload.put("lostLocationDetail", lostItemLocationDetail);
                payload.put("detail", lostItemDetail);
                payload.put("imageSkipped", lostReportImage == null);
                payload.put("claimantName", claimantName);
                payload.put("claimantPhone", claimantPhone);
                payload.put("claimantStudentNumber", claimantStudentNumber);
                String reportedAt = isoTimestamp();
                payload.put("reportedAt", reportedAt);
                // Main-server lost_reports column-compatible aliases.
                payload.put("sub_category", lostItemSubCategory);
                payload.put("item_name", lostItemName);
                payload.put("start_date", lostItemStartDate);
                payload.put("end_date", lostItemEndDate);
                payload.put("lost_building", lostItemBuilding);
                payload.put("lost_detail", lostItemLocationDetail);
                payload.put("unique_features", lostItemDetail);
                payload.put("reporter_name", claimantName);
                payload.put("reporter_phone", claimantPhone);
                payload.put("reporter_student_id", claimantStudentNumber);
                payload.put("report_time_clock", reportedAt);
                payload.put("matching_status", "미매칭");

                String boundary = "----TemiLostReportBoundary" + System.currentTimeMillis();
                conn = openTrustedConnection(new java.net.URL(LOST_REPORT_ENDPOINT));
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(SEARCH_CONNECT_TIMEOUT_MS);
                conn.setReadTimeout(60000);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
                conn.setRequestProperty("Accept", "application/json");

                java.io.OutputStream output = conn.getOutputStream();
                writeMultipartField(output, boundary, "payload", payload.toString());
                writeMultipartField(output, boundary, "phase", "lost_report");
                writeMultipartField(output, boundary, "category", lostItemCategory);
                writeMultipartField(output, boundary, "subCategory", lostItemSubCategory);
                writeMultipartField(output, boundary, "itemName", lostItemName);
                writeMultipartField(output, boundary, "lostStartDate", lostItemStartDate);
                writeMultipartField(output, boundary, "lostEndDate", lostItemEndDate);
                writeMultipartField(output, boundary, "lostLocation", lostItemLocationText());
                writeMultipartField(output, boundary, "lostBuilding", lostItemBuilding);
                writeMultipartField(output, boundary, "lostLocationDetail", lostItemLocationDetail);
                writeMultipartField(output, boundary, "detail", lostItemDetail);
                writeMultipartField(output, boundary, "imageSkipped", String.valueOf(lostReportImage == null));
                writeMultipartField(output, boundary, "claimantName", claimantName);
                writeMultipartField(output, boundary, "claimantPhone", claimantPhone);
                writeMultipartField(output, boundary, "claimantStudentNumber", claimantStudentNumber);
                writeMultipartField(output, boundary, "sub_category", lostItemSubCategory);
                writeMultipartField(output, boundary, "item_name", lostItemName);
                writeMultipartField(output, boundary, "start_date", lostItemStartDate);
                writeMultipartField(output, boundary, "end_date", lostItemEndDate);
                writeMultipartField(output, boundary, "lost_building", lostItemBuilding);
                writeMultipartField(output, boundary, "lost_detail", lostItemLocationDetail);
                writeMultipartField(output, boundary, "unique_features", lostItemDetail);
                writeMultipartField(output, boundary, "reporter_name", claimantName);
                writeMultipartField(output, boundary, "reporter_phone", claimantPhone);
                writeMultipartField(output, boundary, "reporter_student_id", claimantStudentNumber);
                writeMultipartField(output, boundary, "report_time_clock", reportedAt);
                writeMultipartField(output, boundary, "matching_status", "미매칭");
                if (lostReportImage != null) {
                    writeMultipartImage(output, boundary, "image", "lost-report.jpg", lostReportImage);
                }
                output.write(("--" + boundary + "--\r\n").getBytes("UTF-8"));
                output.flush();
                output.close();

                int responseCode = conn.getResponseCode();
                String responseBody = readResponseBody(conn, responseCode);
                Log.d(TAG, "Lost report response " + responseCode + ": " + responseBody);
                if (responseCode < 200 || responseCode >= 300) {
                    throw new java.io.IOException(
                            "HTTP " + responseCode + " " + shortMessage(responseBody)
                    );
                }

                lostReportRequestNumber = firstJsonString(
                        responseBody,
                        "",
                        "requestNumber",
                        "request_number",
                        "reportNumber",
                        "report_number"
                );
                runOnUiThread(this::showLostReportDone);
            } catch (Exception e) {
                Log.e(TAG, "Lost report request failed", e);
                runOnUiThread(() -> {
                    toast("분실 신고 전송 실패: " + valueOr(e.getMessage(), "연결 오류"));
                    submitButton.setEnabled(true);
                    submitButton.setText("입력 완료");
                });
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }).start();
    }

    private String lostItemLocationText() {
        boolean hasBuilding = lostItemBuilding != null && !lostItemBuilding.trim().isEmpty()
                && !"학교 건물 선택".equals(lostItemBuilding);
        String detail = valueOr(lostItemLocationDetail, "");
        if (hasBuilding && !detail.isEmpty()) {
            return lostItemBuilding.trim() + " " + detail;
        }
        if (hasBuilding) {
            return lostItemBuilding.trim();
        }
        return detail;
    }

    private void showLostReportDone() {
        base();
        String generatedNumber = "#A2026-" + (1000 + new Random().nextInt(8999));
        String number = valueOr(lostReportRequestNumber, generatedNumber);
        title(lostReportFromSimilarMatch
                ? "관리자 승인 요청이 접수되었어요"
                : "분실 신고가 완료되었어요");
        subtitle(lostReportFromSimilarMatch
                ? "관리자 확인 후 입력한 연락처로 안내드릴게요"
                : "유사한 물건이 등록될 때 연락처로 안내드릴게요");

        TextView label = label("신청 번호", 24, true);
        label.setGravity(Gravity.CENTER);
        root.addView(label, matchWrapWithMargin(0, 44, 0, 16));

        TextView numberView = label(number, 38, true);
        numberView.setGravity(Gravity.CENTER);
        numberView.setBackgroundResource(R.drawable.card);
        root.addView(numberView, requestNumberBoxParams());

        centerButton("10초 후 대기 화면으로", v -> showIdle());
        lostReportFromSimilarMatch = false;
        autoIdle(10000);
    }

    private void showIdentityForm() {
        base();
        title("본인 확인이 필요해요");
        LinearLayout form = formContainer();
        EditText name = input("이름을 입력해 주세요");
        EditText phone = input("연락처를 입력해 주세요");
        EditText studentNumber = input("학번을 입력해 주세요");
        form.addView(formLine("이름", name, null));
        form.addView(formLine("연락처", phone, null));
        form.addView(formLine("학번", studentNumber, null));

        CheckBox agree = new CheckBox(this);
        agree.setText("(필수) 개인정보 수집 및 이용에 동의합니다");
        agree.setTextSize(19);
        agree.setTextColor(TEXT);
        form.addView(agree, matchWrapWithMargin(0, 6, 0, 0));

        CheckBox claimAgree = new CheckBox(this);
        claimAgree.setText("(필수) 분실물 수령 시 본인 확인 절차에 협조하며,\n허위 수령 등 문제가 발생할 경우 관련 확인 절차에 협조하는 데 동의합니다");
        claimAgree.setTextSize(19);
        claimAgree.setTextColor(TEXT);
        form.addView(claimAgree, matchWrapWithMargin(0, 6, 0, 0));

        root.addView(form, fillArea());
        bottomButton("입력 완료", v -> {
            if (!agree.isChecked() || !claimAgree.isChecked()) {
                toast("개인정보 수집·이용 동의가 필요합니다.");
                return;
            }
            claimantName = name.getText().toString().trim();
            claimantPhone = phone.getText().toString().trim();
            claimantStudentNumber = studentNumber.getText().toString().trim();
            if (claimantName.isEmpty() || claimantPhone.isEmpty() || claimantStudentNumber.isEmpty()) {
                toast("이름, 연락처, 학번을 모두 입력해 주세요.");
                return;
            }
            showLockerUnlock();
        });
        backButton(v -> showMatchedItemConfirm(92));
    }

    private void showLockerUnlock() {
        base();
        title("본인 확인이 완료되었어요");
        subtitle("물건 수령 버튼을 누르면 메인 서버에 잠금 해제 요청을 보냅니다");

        TextView label = label("보관함 번호", 24, true);
        label.setGravity(Gravity.CENTER);
        root.addView(label, matchWrapWithMargin(0, 24, 0, 12));

        TextView locker = label(activeLockerNumber, 34, true);
        locker.setGravity(Gravity.CENTER);
        locker.setBackgroundResource(R.drawable.card);
        root.addView(locker, lockerBoxParams());

        Button pickupButton = primaryButton("물건 수령", null);
        pickupButton.setOnClickListener(v -> requestLockerOpen(pickupButton));
        root.addView(pickupButton, centerButtonParams());
        backButton(v -> showIdentityForm());
    }

    private void requestLockerOpen(Button pickupButton) {
        pickupButton.setEnabled(false);
        pickupButton.setText("잠금 해제 요청 중...");

        new Thread(() -> {
            java.net.HttpURLConnection conn = null;
            try {
                FoundItemCandidate candidate = latestCandidate;
                JSONObject payload = new JSONObject();
                payload.put("action", "open");
                payload.put("itemId", candidate == null ? 0 : candidate.id);
                payload.put("managementNumber", candidate == null ? "" : candidate.managementNumber);
                payload.put("lockerNumber", activeLockerNumber);
                payload.put("claimantName", claimantName);
                payload.put("claimantPhone", claimantPhone);
                payload.put("claimantStudentNumber", claimantStudentNumber);
                payload.put("requestedAt", isoTimestamp());

                conn = openTrustedConnection(new java.net.URL(LOCKER_OPEN_ENDPOINT));
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(30000);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                conn.setRequestProperty("Accept", "application/json");

                byte[] body = payload.toString().getBytes("UTF-8");
                java.io.OutputStream output = conn.getOutputStream();
                output.write(body);
                output.flush();
                output.close();

                int responseCode = conn.getResponseCode();
                String responseBody = readResponseBody(conn, responseCode);
                Log.d(TAG, "Locker open response " + responseCode + ": " + responseBody);
                if (responseCode < 200 || responseCode >= 300) {
                    throw new java.io.IOException(
                            "HTTP " + responseCode + " " + shortMessage(responseBody)
                    );
                }

                String lockerNumber = firstJsonString(
                        responseBody,
                        activeLockerNumber,
                        "lockerNumber",
                        "locker_number",
                        "locker"
                );
                activeLockerNumber = valueOr(lockerNumber, activeLockerNumber);
                runOnUiThread(this::showLockerOpened);
            } catch (Exception e) {
                Log.e(TAG, "Locker open request failed", e);
                runOnUiThread(() -> {
                    toast("잠금 해제 요청 실패: " + valueOr(e.getMessage(), "연결 오류"));
                    pickupButton.setEnabled(true);
                    pickupButton.setText("물건 수령");
                });
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }).start();
    }

    private void showLockerOpened() {
        base();
        title("보관함 잠금이 해제되었어요");
        subtitle("보관함 번호를 확인한 후 분실물을 수령해 주세요");

        TextView label = label("보관함 번호", 24, true);
        label.setGravity(Gravity.CENTER);
        root.addView(label, matchWrapWithMargin(0, 24, 0, 12));

        TextView locker = label(activeLockerNumber, 34, true);
        locker.setGravity(Gravity.CENTER);
        locker.setBackgroundResource(R.drawable.card);
        root.addView(locker, lockerBoxParams());

        centerButton("수령 완료", v -> showReceiveDone());
    }

    private void showReceiveDone() {
        base();
        title("분실물 수령이 완료되었어요");
        subtitle("이용해 주셔서 감사합니다");
        centerButton("5초 후 홈으로", v -> showIdle());
        autoIdle(5000);
    }

    private void showFoundGuide() {
        base();
        title("습득물은 이렇게 등록해요");
        LinearLayout row = horizontal();
        row.addView(stepCard("1단계", "정보 입력"), weight(1, 0, 12));
        row.addView(stepCard("2단계", "사진 촬영"), weight(1, 12, 12));
        row.addView(stepCard("3단계", "등록 완료"), weight(1, 12, 0));
        root.addView(row, fillArea());
        bottomButton("등록하기", v -> startFoundItemRegistration());
        backButton(v -> showIdle());
    }

    private void startFoundItemRegistration() {
        capturedItemImage = null;
        captureForLostReport = false;
        captureForLostReportForm = false;
        foundCategory = "";
        foundSubCategory = "";
        foundDate = "";
        foundItemName = "";
        foundBuilding = "";
        foundLocationDetail = "";
        foundDetail = "";
        showFoundItemForm();
    }

    private void showFoundItemForm() {
        base();
        title("습득물 정보를 입력해 주세요");
        LinearLayout form = formContainer();
        Spinner category = spinner(majorCategories);
        Spinner subCategory = spinner(minorCategories);
        EditText foundAt = input(today());
        EditText itemName = input("물품명을 입력해 주세요");
        Spinner building = spinner(buildings);
        EditText locationDetail = input("예) 1층 화장실, 302호");
        EditText detail = input("(선택) 예) 키링이 같이 달려있어요");

        form.addView(formLine("물품 분류", category, subCategory));
        form.addView(formLine("습득일자", foundAt, itemName));
        form.addView(formLine("습득장소", building, locationDetail));
        form.addView(formLine("특이사항", detail, null));

        LinearLayout voiceButtons = horizontal();
        voiceButtons.setGravity(Gravity.CENTER);
        voiceButtons.addView(grayButton("물품명 말하기", v -> openVoiceInput(itemName)), voiceButtonParams());
        voiceButtons.addView(grayButton("장소 말하기", v -> openVoiceInput(locationDetail)), voiceButtonParams());
        voiceButtons.addView(grayButton("특징 말하기", v -> openVoiceInput(detail)), voiceButtonParams());
        form.addView(voiceButtons, matchWrapWithMargin(0, 18, 0, 0));

        root.addView(form, fillArea());
        bottomButton("다음", v -> {
            if ("물품 분류 선택".equals(category.getSelectedItem().toString())) {
                toast("물품 분류를 선택해 주세요.");
                return;
            }
            if (itemName.getText().toString().trim().isEmpty()) {
                toast("습득물명을 입력해 주세요.");
                return;
            }
            saveFoundItemInputs(category, subCategory, foundAt, itemName, building, locationDetail, detail);
            showFoundCamera();
        });
        backButton(v -> showFoundGuide());
    }

    private void saveFoundItemInputs(Spinner category, Spinner subCategory, EditText foundAt, EditText itemName,
                                     Spinner building, EditText locationDetail, EditText detail) {
        foundCategory = category.getSelectedItem().toString();
        foundSubCategory = subCategory.getSelectedItem().toString();
        if ("세부 분류 선택".equals(foundSubCategory)) {
            foundSubCategory = "";
        }
        foundDate = foundAt.getText().toString().trim();
        foundItemName = itemName.getText().toString().trim();
        foundBuilding = building.getSelectedItem().toString();
        if ("학교 건물 선택".equals(foundBuilding)) {
            foundBuilding = "";
        }
        foundLocationDetail = locationDetail.getText().toString().trim();
        foundDetail = detail.getText().toString().trim();
    }

    private void showFoundCamera() {
        base();
        title("습득물을 카메라로 촬영해 주세요");
        addImagePreview(capturedItemImage, "촬영 이미지 미리보기\n\n아직 촬영된 이미지가 없습니다.");
        bottomButton(capturedItemImage == null ? "촬영" : "다시 촬영", v -> {
            captureForLostReport = false;
            captureForLostReportForm = false;
            openCamera();
        });
        centerButton(capturedItemImage == null ? "촬영 생략" : "등록하기", v -> showFoundConfirm());
        backButton(v -> showFoundItemForm());
    }

    private void showFoundConfirm() {
        base();
        title("입력한 정보가 맞는지 확인해 주세요");
        LinearLayout row = horizontal();
        LinearLayout info = new LinearLayout(this);
        info.setOrientation(LinearLayout.VERTICAL);
        info.addView(infoLine("물품 분류", foundCategoryText()));
        info.addView(infoLine("습득일자", valueOr(foundDate, today())));
        info.addView(infoLine("습득물명", valueOr(foundItemName, "미입력")));
        info.addView(infoLine("습득장소", foundLocationText()));
        info.addView(infoLine("특이사항", valueOr(foundDetail, "없음")));

        LinearLayout image = new LinearLayout(this);
        image.setOrientation(LinearLayout.VERTICAL);
        if (capturedItemImage == null) {
            TextView imageBox = label("이미지\n\n촬영 이미지 없음", 24, true);
            imageBox.setGravity(Gravity.CENTER);
            imageBox.setTextColor(MUTED);
            imageBox.setBackgroundResource(R.drawable.card);
            image.addView(imageBox, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(200)));
        } else {
            ImageView imageBox = new ImageView(this);
            imageBox.setImageBitmap(capturedItemImage);
            imageBox.setScaleType(ImageView.ScaleType.CENTER_CROP);
            imageBox.setBackgroundResource(R.drawable.card);
            image.addView(imageBox, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(200)));
        }


        row.addView(info, weight(1, 0, 20));
        row.addView(image, weight(1, 20, 0));
        root.addView(row, fillArea());

        LinearLayout buttons = horizontal();
        buttons.setGravity(Gravity.CENTER);
        buttons.addView(grayButton("수정하기", v -> showFoundItemForm()), dualButton());
        buttons.addView(primaryButton("확인", v -> uploadFoundItem()), dualButton());
        root.addView(buttons, lowerArea());
        backButton(v -> showFoundCamera());
    }

    private void showFoundDone() {
        base();
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(new View(this), fillArea());

        TextView doneTitle = label("등록을 완료했어요!", 42, true);
        doneTitle.setGravity(Gravity.CENTER);
        root.addView(doneTitle, matchWrapWithMargin(0, 0, 0, 28));

        TextView doneSubtitle = label("소중한 제보 감사합니다", 28, false);
        doneSubtitle.setTextColor(MUTED);
        doneSubtitle.setGravity(Gravity.CENTER);
        root.addView(doneSubtitle, matchWrap());

        root.addView(new View(this), fillArea());
        root.addView(primaryButton("5초 후 홈으로", v -> showIdle()), bottomButtonParams());
        autoIdle(5000);
    }

    private void uploadFoundItem() {
        showFoundUploading();
        uploadFoundItemWithImage();
        root.postDelayed(this::showFoundDone, 5000);
    }

    private void showFoundUploading() {
        base();
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(new View(this), fillArea());

        TextView title = label("등록 정보를 전송하고 있어요", 40, true);
        title.setGravity(Gravity.CENTER);
        root.addView(title, matchWrapWithMargin(0, 0, 0, 26));

        TextView desc = label("잠시만 기다려주세요", 28, false);
        desc.setTextColor(MUTED);
        desc.setGravity(Gravity.CENTER);
        root.addView(desc, matchWrap());

        root.addView(new View(this), fillArea());
    }

    private void uploadFoundItemWithImage() {
        new Thread(() -> {
            try {
                String boundary = "----TemiLostFoundBoundary" + System.currentTimeMillis();
                java.net.URL url = new java.net.URL(FOUND_ITEM_ENDPOINT);
                java.net.HttpURLConnection conn = openTrustedConnection(url);
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(60000);
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
                conn.setRequestProperty("Accept", "application/json");
                conn.setDoOutput(true);

                java.io.OutputStream output = conn.getOutputStream();
                writeMultipartField(output, boundary, "category", valueOr(foundCategory, ""));
                writeMultipartField(output, boundary, "subCategory", valueOr(foundSubCategory, ""));
                writeMultipartField(output, boundary, "itemName", valueOr(foundItemName, ""));
                writeMultipartField(output, boundary, "foundLocation", foundLocationText());
                writeMultipartField(output, boundary, "foundBuilding", valueOr(foundBuilding, ""));
                writeMultipartField(output, boundary, "foundLocationDetail", valueOr(foundLocationDetail, ""));
                writeMultipartField(output, boundary, "detail", valueOr(foundDetail, ""));
                writeMultipartField(output, boundary, "foundAt", valueOr(foundDate, today()));
                writeMultipartImage(
                        output,
                        boundary,
                        "image",
                        capturedItemImage == null ? "found-item-placeholder.jpg" : "found-item.jpg",
                        capturedItemImage == null ? placeholderImage() : capturedItemImage
                );
                output.write(("--" + boundary + "--\r\n").getBytes("UTF-8"));
                output.flush();
                output.close();

                int responseCode = conn.getResponseCode();
                String responseBody = readResponseBody(conn, responseCode);
                Log.d(TAG, "Found item response " + responseCode + ": " + responseBody);
                conn.disconnect();
                runOnUiThread(() -> {
                    if (!isAcceptedFoundItemResponse(responseCode, responseBody)) {
                        toast("서버 등록 실패: " + responseCode + " " + shortMessage(responseBody));
                    }
                });
            } catch (java.net.SocketTimeoutException e) {
                runOnUiThread(() -> toast("서버 응답이 늦지만 등록 요청은 전송되었습니다."));
            } catch (Exception e) {
                runOnUiThread(() -> toast("서버 연결 오류: " + e.getMessage()));
            }
        }).start();
    }

    private Bitmap placeholderImage() {
        Bitmap bitmap = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888);
        bitmap.eraseColor(Color.WHITE);
        return bitmap;
    }

    private void writeMultipartField(java.io.OutputStream output, String boundary, String name, String value)
            throws java.io.IOException {
        String part = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + name + "\"\r\n"
                + "Content-Type: text/plain; charset=UTF-8\r\n\r\n"
                + value + "\r\n";
        output.write(part.getBytes("UTF-8"));
    }

    private void writeMultipartImage(java.io.OutputStream output, String boundary, String name, String fileName, Bitmap bitmap)
            throws java.io.IOException {
        java.io.ByteArrayOutputStream imageBytes = new java.io.ByteArrayOutputStream();
        bitmap.compress(Bitmap.CompressFormat.JPEG, 90, imageBytes);

        String header = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + name + "\"; filename=\"" + fileName + "\"\r\n"
                + "Content-Type: image/jpeg\r\n\r\n";
        output.write(header.getBytes("UTF-8"));
        output.write(imageBytes.toByteArray());
        output.write("\r\n".getBytes("UTF-8"));
    }

    private void openCamera() {
        if (android.os.Build.VERSION.SDK_INT >= 23
                && checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.CAMERA}, REQUEST_CAMERA_PERMISSION);
            return;
        }

        Intent intent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        if (intent.resolveActivity(getPackageManager()) == null) {
            toast("카메라 앱을 찾을 수 없습니다.");
            return;
        }
        startActivityForResult(intent, REQUEST_CAPTURE_IMAGE);
    }

    private void openVoiceInput(EditText targetInput) {
        voiceTargetInput = targetInput;
        if (android.os.Build.VERSION.SDK_INT >= 23
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQUEST_AUDIO_PERMISSION);
            return;
        }

        if (startTemiVoiceInput()) {
            return;
        }

        startAndroidVoiceInput();
    }

    private boolean startTemiVoiceInput() {
        try {
            com.robotemi.sdk.Robot robot = com.robotemi.sdk.Robot.getInstance();
            if (!robot.isReady()) {
                return false;
            }

            robot.removeAsrListener(temiAsrListener);
            robot.addAsrListener(temiAsrListener);
            temiVoiceListening = true;
            robot.askQuestion("입력할 내용을 말씀해 주세요");
            toast("temi가 듣고 있어요.");
            return true;
        } catch (Throwable error) {
            temiVoiceListening = false;
            Log.w(TAG, "temi voice input unavailable; using Android speech recognizer", error);
            return false;
        }
    }

    private void handleTemiVoiceResult(String text) {
        if (!temiVoiceListening) {
            return;
        }

        stopTemiVoiceInput();
        if (text == null || text.trim().isEmpty()) {
            toast("음성 인식 결과를 불러오지 못했습니다.");
            return;
        }

        applyVoiceResult(text.trim());
    }

    private void stopTemiVoiceInput() {
        if (!temiVoiceListening) {
            return;
        }

        temiVoiceListening = false;
        try {
            com.robotemi.sdk.Robot robot = com.robotemi.sdk.Robot.getInstance();
            robot.removeAsrListener(temiAsrListener);
            robot.finishConversation();
        } catch (Throwable error) {
            Log.w(TAG, "Failed to stop temi voice input", error);
        }
    }

    private void startAndroidVoiceInput() {
        Intent intent = new Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(
                android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
        );
        intent.putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, "ko-KR");
        intent.putExtra(android.speech.RecognizerIntent.EXTRA_PROMPT, "찾는 물건의 특징을 말해 주세요");
        if (intent.resolveActivity(getPackageManager()) == null) {
            toast("음성 인식 기능을 찾을 수 없습니다.");
            return;
        }
        startActivityForResult(intent, REQUEST_VOICE_INPUT);
    }

    private void applyVoiceResult(String text) {
        if (voiceTargetInput == null) {
            return;
        }

        voiceTargetInput.setText(text);
        voiceTargetInput.setSelection(voiceTargetInput.getText().length());
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_CAMERA_PERMISSION) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                openCamera();
            } else {
                toast("카메라 권한이 필요합니다.");
            }
        } else if (requestCode == REQUEST_AUDIO_PERMISSION) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                if (voiceTargetInput != null) {
                    openVoiceInput(voiceTargetInput);
                }
            } else {
                toast("음성 인식을 위해 마이크 권한이 필요합니다.");
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_VOICE_INPUT && resultCode == RESULT_OK && data != null) {
            java.util.ArrayList<String> results = data.getStringArrayListExtra(
                    android.speech.RecognizerIntent.EXTRA_RESULTS
            );
            if (results != null && !results.isEmpty() && voiceTargetInput != null) {
                applyVoiceResult(results.get(0));
            } else {
                toast("음성 인식 결과를 불러오지 못했습니다.");
            }
        } else if (requestCode == REQUEST_CAPTURE_IMAGE && resultCode == RESULT_OK && data != null) {
            Bundle extras = data.getExtras();
            if (extras != null && extras.get("data") instanceof Bitmap) {
                if (captureForLostReport) {
                    lostReportImage = (Bitmap) extras.get("data");
                    if (captureForLostReportForm) {
                        showLostReportForm();
                    } else {
                        showSearchResult(true);
                    }
                } else {
                    capturedItemImage = (Bitmap) extras.get("data");
                    showFoundCamera();
                }
            } else {
                toast("촬영 이미지를 불러오지 못했습니다.");
            }
        }
    }

    @Override
    protected void onDestroy() {
        stopTemiVoiceInput();
        super.onDestroy();
    }

    private void base() {
        screen = new FrameLayout(this);
        screen.setBackgroundColor(BG);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(42), dp(34), dp(42), dp(34));
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.MATCH_PARENT
        ));
        screen.addView(scroll);
        setContentView(screen);
    }

    private void title(String value) {
        TextView view = label(value, 40, true);
        view.setGravity(Gravity.CENTER);
        root.addView(view, matchWrapWithMargin(0, 0, 0, 34));
    }

    private void subtitle(String value) {
        TextView view = label(value, 26, false);
        view.setGravity(Gravity.CENTER);
        view.setTextColor(MUTED);
        view.setLineSpacing(dp(5), 1.0f);
        root.addView(view, fillArea());
    }

    private LinearLayout bigCard(String eyebrow, String main, View.OnClickListener listener) {
        LinearLayout card = card();
        card.setGravity(Gravity.CENTER);
        card.setOnClickListener(listener);
        TextView small = label(eyebrow, 28, false);
        small.setGravity(Gravity.CENTER);
        TextView big = label(main, 46, true);
        big.setGravity(Gravity.CENTER);
        card.addView(small, matchWrapWithMargin(0, 0, 0, 54));
        card.addView(big, matchWrap());
        return card;
    }

    private LinearLayout stepCard(String step, String main) {
        LinearLayout card = card();
        card.setGravity(Gravity.CENTER);
        TextView small = label(step, 28, false);
        small.setGravity(Gravity.CENTER);
        TextView big = label(main, 42, true);
        big.setGravity(Gravity.CENTER);
        card.addView(small, matchWrapWithMargin(0, 0, 0, 56));
        card.addView(big, matchWrap());
        return card;
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(24), dp(24), dp(24), dp(24));
        card.setBackgroundResource(R.drawable.card);
        return card;
    }

    private LinearLayout formContainer() {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(120), 0, dp(120), 0);
        return form;
    }

    private LinearLayout formLine(String label, View left, View right) {
        LinearLayout line = horizontal();
        line.setGravity(Gravity.CENTER_VERTICAL);
        line.setPadding(0, 0, 0, dp(22));
        TextView labelView = label(label, 27, true);
        line.addView(labelView, new LinearLayout.LayoutParams(dp(170), LinearLayout.LayoutParams.WRAP_CONTENT));

        LinearLayout fields = horizontal();
        fields.addView(left, new LinearLayout.LayoutParams(0, dp(72), 1));
        if (right != null) {
            fields.addView(right, fieldRightParams());
        }
        line.addView(fields, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        return line;
    }

    private LinearLayout infoLine(String label, String value) {
        LinearLayout line = horizontal();
        line.setGravity(Gravity.CENTER_VERTICAL);
        TextView left = label(label, 22, false);
        TextView right = label(value, 26, true);
        line.addView(left, new LinearLayout.LayoutParams(dp(160), LinearLayout.LayoutParams.WRAP_CONTENT));
        line.addView(right, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        line.setPadding(0, 0, 0, dp(30));
        return line;
    }

    private LinearLayout matchInfoLine(String label, String value) {
        LinearLayout line = horizontal();
        line.setGravity(Gravity.CENTER_VERTICAL);
        TextView left = label(label, 21, false);
        left.setTextColor(MUTED);
        TextView right = label(value, 24, true);
        line.addView(left, new LinearLayout.LayoutParams(dp(120), LinearLayout.LayoutParams.WRAP_CONTENT));
        line.addView(right, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        line.setPadding(0, 0, 0, dp(18));
        return line;
    }

    private TextView chip(String text) {
        TextView chip = label(text, 18, false);
        chip.setGravity(Gravity.CENTER);
        chip.setBackgroundResource(R.drawable.button_secondary);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                dp(42)
        );
        params.setMargins(dp(6), 0, dp(6), 0);
        chip.setLayoutParams(params);
        chip.setPadding(dp(18), 0, dp(18), 0);
        return chip;
    }

    private void addImagePreview(Bitmap bitmap, String fallbackText) {
        if (bitmap == null) {
            TextView preview = label(fallbackText, 28, true);
            preview.setGravity(Gravity.CENTER);
            preview.setTextColor(MUTED);
            preview.setBackgroundResource(R.drawable.card);
            root.addView(preview, previewArea());
        } else {
            ImageView preview = new ImageView(this);
            preview.setImageBitmap(bitmap);
            preview.setScaleType(ImageView.ScaleType.CENTER_CROP);
            preview.setBackgroundResource(R.drawable.card);
            root.addView(preview, previewArea());
        }
    }

    private EditText input(String hint) {
        EditText input = new EditText(this);
        input.setTextSize(22);
        input.setHint(hint);
        input.setTextColor(TEXT);
        input.setHintTextColor(Color.rgb(190, 190, 190));
        input.setSingleLine(true);
        input.setPadding(dp(20), 0, dp(20), 0);
        input.setBackgroundResource(R.drawable.input_bg);
        return input;
    }

    private Spinner spinner(String[] values) {
        Spinner spinner = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<String>(
                this,
                android.R.layout.simple_spinner_dropdown_item,
                values
        );
        spinner.setAdapter(adapter);
        spinner.setBackgroundResource(R.drawable.input_bg);
        spinner.setPadding(dp(16), 0, dp(16), 0);
        return spinner;
    }

    private Button primaryButton(String text, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(32);
        button.setTextColor(Color.WHITE);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setAllCaps(false);
        button.setBackgroundResource(R.drawable.button_primary);
        button.setOnClickListener(listener);
        return button;
    }

    private Button grayButton(String text, View.OnClickListener listener) {
        Button button = primaryButton(text, listener);
        button.setBackgroundResource(R.drawable.button_gray);
        return button;
    }

    private Button photoButton(String text, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(42);
        button.setTextColor(MUTED);
        button.setAllCaps(false);
        button.setBackgroundResource(R.drawable.button_secondary);
        button.setOnClickListener(listener);
        return button;
    }

    private void bottomButton(String text, View.OnClickListener listener) {
        root.addView(primaryButton(text, listener), bottomButtonParams());
    }

    private void centerButton(String text, View.OnClickListener listener) {
        root.addView(primaryButton(text, listener), centerButtonParams());
    }

    private void backButton(View.OnClickListener listener) {
        Button back = new Button(this);
        back.setText("<");
        back.setTextSize(38);
        back.setTextColor(Color.WHITE);
        back.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        back.setAllCaps(false);
        back.setBackgroundResource(R.drawable.button_primary);
        back.setOnClickListener(listener);

        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(dp(70), dp(70));
        params.gravity = Gravity.START | Gravity.BOTTOM;
        params.leftMargin = dp(44);
        params.bottomMargin = dp(30);
        screen.addView(back, params);
    }

    private TextView label(String text, int sp, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(sp);
        view.setTextColor(TEXT);
        if (bold) {
            view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        }
        return view;
    }

    private LinearLayout horizontal() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        return layout;
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show();
    }

    private void autoIdle(long delayMs) {
        root.postDelayed(this::showIdle, delayMs);
    }

    private String today() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.KOREA).format(new Date());
    }

    private String isoTimestamp() {
        String timestamp = new SimpleDateFormat(
                "yyyy-MM-dd'T'HH:mm:ssZ",
                Locale.KOREA
        ).format(new Date());
        if (timestamp.length() >= 5) {
            return timestamp.substring(0, timestamp.length() - 2)
                    + ":"
                    + timestamp.substring(timestamp.length() - 2);
        }
        return timestamp;
    }

    private String searchRequestJson(boolean includeDetail, String detail, boolean imageSkipped) {
        return "{"
                + "\"phase\":\"explore\","
                + "\"category\":\"" + jsonEscape(valueOr(searchCategory, "")) + "\","
                + "\"subCategory\":\"" + jsonEscape(valueOr(searchSubCategory, "")) + "\","
                + "\"lostStartDate\":\"" + jsonEscape(valueOr(searchStartDate, today())) + "\","
                + "\"lostEndDate\":\"" + jsonEscape(valueOr(searchEndDate, today())) + "\","
                + "\"lostLocation\":\"" + jsonEscape(searchLocationText()) + "\","
                + "\"lostBuilding\":\"" + jsonEscape(valueOr(searchBuilding, "")) + "\","
                + "\"lostLocationDetail\":\"" + jsonEscape(valueOr(searchLocationDetail, "")) + "\","
                + "\"detail\":\"" + jsonEscape(valueOr(detail, "")) + "\","
                + "\"imageSkipped\":" + imageSkipped
                + "}";
    }

    private String searchLocationText() {
        boolean hasBuilding = searchBuilding != null && !searchBuilding.trim().isEmpty()
                && !"학교 건물 선택".equals(searchBuilding);
        String detail = valueOr(searchLocationDetail, "");
        if (hasBuilding && !detail.isEmpty()) {
            return searchBuilding.trim() + " " + detail;
        }
        if (hasBuilding) {
            return searchBuilding.trim();
        }
        return valueOr(searchLocationDetail, "");
    }

    private String readResponseBody(java.net.HttpURLConnection conn, int responseCode) throws java.io.IOException {
        java.io.InputStream stream = responseCode >= 200 && responseCode < 300
                ? conn.getInputStream()
                : conn.getErrorStream();
        if (stream == null) {
            return "";
        }
        java.io.ByteArrayOutputStream buffer = new java.io.ByteArrayOutputStream();
        byte[] chunk = new byte[1024];
        int read;
        while ((read = stream.read(chunk)) != -1) {
            buffer.write(chunk, 0, read);
        }
        stream.close();
        return buffer.toString("UTF-8");
    }

    private String shortMessage(String message) {
        if (message == null || message.trim().isEmpty()) {
            return "";
        }
        String compact = message.replace("\n", " ").replace("\r", " ").trim();
        if (compact.length() > 80) {
            return compact.substring(0, 80) + "...";
        }
        return compact;
    }

    private boolean isAcceptedFoundItemResponse(int responseCode, String responseBody) {
        if (responseCode >= 200 && responseCode < 300) {
            return true;
        }
        if (responseBody == null) {
            return false;
        }
        String body = responseBody.toLowerCase(Locale.ROOT);
        return body.contains("\"status\":\"success\"")
                || body.contains("\"success\":true")
                || body.contains("success");
    }

    private java.net.HttpURLConnection openTrustedConnection(java.net.URL url) throws java.io.IOException {
        java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
        if (conn instanceof javax.net.ssl.HttpsURLConnection) {
            trustAllCertificates((javax.net.ssl.HttpsURLConnection) conn);
        }
        return conn;
    }

    private void trustAllCertificates(javax.net.ssl.HttpsURLConnection conn) throws java.io.IOException {
        try {
            javax.net.ssl.TrustManager[] trustManagers = new javax.net.ssl.TrustManager[]{
                    new javax.net.ssl.X509TrustManager() {
                        public java.security.cert.X509Certificate[] getAcceptedIssuers() {
                            return new java.security.cert.X509Certificate[0];
                        }

                        public void checkClientTrusted(java.security.cert.X509Certificate[] certs, String authType) {
                        }

                        public void checkServerTrusted(java.security.cert.X509Certificate[] certs, String authType) {
                        }
                    }
            };
            javax.net.ssl.SSLContext sslContext = javax.net.ssl.SSLContext.getInstance("TLS");
            sslContext.init(null, trustManagers, new java.security.SecureRandom());
            conn.setSSLSocketFactory(sslContext.getSocketFactory());
            conn.setHostnameVerifier((hostname, session) -> true);
        } catch (Exception e) {
            throw new java.io.IOException("HTTPS 인증서 우회 설정 실패", e);
        }
    }

    private SearchResponse parseSearchResponse(String body, boolean includeDetail) {
        int count = firstJsonInt(body, 0, "count", "itemCount", "total", "foundCount");
        int resultCount = countResults(body);
        if (count == 0 && resultCount > 0) {
            count = resultCount;
        }
        FoundItemCandidate candidate = parseBestCandidate(body);
        int score = candidate != null ? candidate.matchRate : bestJsonScore(
                body,
                0,
                "score",
                "similarity",
                "matchRate",
                "matchingRate",
                "match_rate"
        );
        if (includeDetail && score == 0 && count > 0) {
            score = 50;
        }
        return new SearchResponse(count, score, candidate);
    }

    private FoundItemCandidate parseBestCandidate(String body) {
        if (body == null || body.trim().isEmpty()) {
            return null;
        }
        try {
            JSONObject rootObject = new JSONObject(body);
            JSONArray results = rootObject.optJSONArray("results");
            if (results == null || results.length() == 0) {
                return null;
            }

            FoundItemCandidate best = null;
            for (int i = 0; i < results.length(); i++) {
                JSONObject item = results.optJSONObject(i);
                if (item == null) {
                    continue;
                }
                FoundItemCandidate candidate = new FoundItemCandidate(
                        item.optInt("id", 0),
                        item.optString("management_number", ""),
                        item.optString("item_name", ""),
                        item.optString("category", ""),
                        item.optString("sub_category", ""),
                        item.optString("found_date", ""),
                        item.optString("found_location_building", ""),
                        item.optString("found_location_detail", ""),
                        item.optString("thumbnail_path", ""),
                        normalizeScore(item.optDouble("match_rate", 0))
                );
                if (best == null || candidate.matchRate > best.matchRate) {
                    best = candidate;
                }
            }
            return best;
        } catch (Exception e) {
            Log.d(TAG, "Candidate parse failed: " + e.getMessage());
            return null;
        }
    }

    private int bestJsonScore(String body, int fallback, String... keys) {
        if (body == null) {
            return fallback;
        }
        int best = fallback;
        for (String key : keys) {
            java.util.regex.Pattern pattern = java.util.regex.Pattern.compile(
                    "\"" + key + "\"\\s*:\\s*\"?([0-9]+(?:\\.[0-9]+)?)\"?"
            );
            java.util.regex.Matcher matcher = pattern.matcher(body);
            while (matcher.find()) {
                try {
                    double raw = Double.parseDouble(matcher.group(1));
                    int normalized = normalizeScore(raw);
                    if (normalized > best) {
                        best = normalized;
                    }
                } catch (NumberFormatException ignored) {
                    return best;
                }
            }
        }
        return best;
    }

    private int normalizeScore(double score) {
        if (score > 0 && score <= 1) {
            score = score * 100;
        }
        return Math.max(0, Math.min(100, (int) Math.round(score)));
    }

    private int countResults(String body) {
        if (body == null || !body.contains("\"results\"")) {
            return 0;
        }
        java.util.regex.Pattern arrayPattern = java.util.regex.Pattern.compile(
                "\"results\"\\s*:\\s*\\[(.*?)]",
                java.util.regex.Pattern.DOTALL
        );
        java.util.regex.Matcher arrayMatcher = arrayPattern.matcher(body);
        if (!arrayMatcher.find()) {
            return 0;
        }
        String resultsBody = arrayMatcher.group(1).trim();
        if (resultsBody.isEmpty()) {
            return 0;
        }
        java.util.regex.Pattern pattern = java.util.regex.Pattern.compile("\\{");
        java.util.regex.Matcher matcher = pattern.matcher(resultsBody);
        int count = 0;
        while (matcher.find()) {
            count++;
        }
        return count;
    }

    private int firstJsonInt(String body, int fallback, String... keys) {
        if (body == null) {
            return fallback;
        }
        for (String key : keys) {
            java.util.regex.Pattern pattern = java.util.regex.Pattern.compile(
                    "\"" + key + "\"\\s*:\\s*([0-9]+)"
            );
            java.util.regex.Matcher matcher = pattern.matcher(body);
            if (matcher.find()) {
                try {
                    return Integer.parseInt(matcher.group(1));
                } catch (NumberFormatException ignored) {
                    return fallback;
                }
            }
        }
        return fallback;
    }

    private String firstJsonString(String body, String fallback, String... keys) {
        if (body == null || body.trim().isEmpty()) {
            return fallback;
        }
        try {
            JSONObject object = new JSONObject(body);
            JSONObject data = object.optJSONObject("data");
            for (String key : keys) {
                String value = object.optString(key, "").trim();
                if (value.isEmpty() && data != null) {
                    value = data.optString(key, "").trim();
                }
                if (!value.isEmpty()) {
                    return value;
                }
            }
        } catch (Exception e) {
            Log.d(TAG, "String response parse failed: " + e.getMessage());
        }
        return fallback;
    }

    private String valueOr(String value, String fallback) {
        if (value == null || value.trim().isEmpty()) {
            return fallback;
        }
        return value.trim();
    }

    private String foundCategoryText() {
        String category = valueOr(foundCategory, "미선택");
        if (foundSubCategory == null || foundSubCategory.trim().isEmpty()
                || "세부 분류 선택".equals(foundSubCategory)) {
            return category;
        }
        return category + " / " + foundSubCategory.trim();
    }

    private String foundLocationText() {
        boolean hasBuilding = foundBuilding != null && !foundBuilding.trim().isEmpty()
                && !"학교 건물 선택".equals(foundBuilding);
        String detail = valueOr(foundLocationDetail, "");
        if (hasBuilding && !detail.isEmpty()) {
            return foundBuilding.trim() + " " + detail;
        }
        if (hasBuilding) {
            return foundBuilding.trim();
        }
        return valueOr(foundLocationDetail, "미입력");
    }

    private FoundItemCandidate candidateOrFallback(int score) {
        if (latestCandidate != null) {
            return latestCandidate;
        }
        return new FoundItemCandidate(
                0,
                "",
                "후보 분실물",
                searchCategory,
                searchSubCategory,
                "확인 중",
                searchBuilding,
                searchLocationDetail,
                "",
                score
        );
    }

    private View candidateImageView(FoundItemCandidate candidate, int widthDp, int heightDp) {
        FrameLayout container = new FrameLayout(this);
        container.setBackgroundResource(R.drawable.card);

        TextView placeholder = label("이미지를 불러오는 중", 18, true);
        placeholder.setGravity(Gravity.CENTER);
        placeholder.setTextColor(MUTED);
        container.addView(placeholder, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
        ));

        String imageUrl = candidateImageUrl(candidate == null ? "" : candidate.thumbnailPath);
        if (imageUrl.isEmpty()) {
            placeholder.setText("등록된 이미지 없음");
            return container;
        }

        ImageView imageView = new ImageView(this);
        imageView.setScaleType(ImageView.ScaleType.CENTER_CROP);
        imageView.setVisibility(View.INVISIBLE);
        imageView.setTag(imageUrl);
        container.addView(imageView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
        ));
        loadCandidateImage(imageUrl, imageView, placeholder);
        return container;
    }

    private String candidateImageUrl(String thumbnailPath) {
        if (thumbnailPath == null || thumbnailPath.trim().isEmpty()) {
            return "";
        }
        String path = thumbnailPath.trim().replace('\\', '/');
        if (path.startsWith("http://") || path.startsWith("https://")) {
            return path;
        }
        if (!path.startsWith("/")) {
            path = "/" + path;
        }
        return SEARCH_API_BASE_URL + path;
    }

    private void loadCandidateImage(String imageUrl, ImageView imageView, TextView placeholder) {
        new Thread(() -> {
            java.net.HttpURLConnection conn = null;
            try {
                conn = openTrustedConnection(new java.net.URL(imageUrl));
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(20000);
                conn.setInstanceFollowRedirects(true);
                conn.setRequestProperty("Accept", "image/*");

                int responseCode = conn.getResponseCode();
                if (responseCode < 200 || responseCode >= 300) {
                    throw new java.io.IOException("HTTP " + responseCode);
                }
                Bitmap bitmap = android.graphics.BitmapFactory.decodeStream(conn.getInputStream());
                if (bitmap == null) {
                    throw new java.io.IOException("이미지 디코딩 실패");
                }

                runOnUiThread(() -> {
                    if (!imageUrl.equals(imageView.getTag())) {
                        return;
                    }
                    imageView.setImageBitmap(bitmap);
                    imageView.setVisibility(View.VISIBLE);
                    placeholder.setVisibility(View.GONE);
                });
            } catch (Exception e) {
                Log.e(TAG, "Candidate image load failed: " + imageUrl, e);
                runOnUiThread(() -> {
                    if (imageUrl.equals(imageView.getTag())) {
                        placeholder.setText("이미지를 불러오지 못했어요");
                    }
                });
            } finally {
                if (conn != null) {
                    conn.disconnect();
                }
            }
        }).start();
    }

    private String candidateCategoryText(FoundItemCandidate candidate) {
        String category = valueOr(candidate.category, "미분류");
        String subCategory = valueOr(candidate.subCategory, "");
        if (subCategory.isEmpty()) {
            return category;
        }
        return category + " / " + subCategory;
    }

    private String candidateLocationText(FoundItemCandidate candidate) {
        String building = valueOr(candidate.foundLocationBuilding, "");
        String detail = valueOr(candidate.foundLocationDetail, "");
        if (!building.isEmpty() && !detail.isEmpty()) {
            return building + " " + detail;
        }
        if (!building.isEmpty()) {
            return building;
        }
        return valueOr(detail, "확인 중");
    }

    private String jsonEscape(String value) {
        if (value == null) {
            return "";
        }
        return value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }

    private void setSpinnerSelection(Spinner spinner, String value) {
        for (int i = 0; i < spinner.getCount(); i++) {
            if (value.equals(spinner.getItemAtPosition(i).toString())) {
                spinner.setSelection(i);
                return;
            }
        }
    }

    private static class SearchResponse {
        final int count;
        final int score;
        final FoundItemCandidate candidate;

        SearchResponse(int count, int score, FoundItemCandidate candidate) {
            this.count = count;
            this.score = score;
            this.candidate = candidate;
        }
    }

    private static class FoundItemCandidate {
        final int id;
        final String managementNumber;
        final String itemName;
        final String category;
        final String subCategory;
        final String foundDate;
        final String foundLocationBuilding;
        final String foundLocationDetail;
        final String thumbnailPath;
        final int matchRate;

        FoundItemCandidate(int id, String managementNumber, String itemName, String category, String subCategory,
                           String foundDate, String foundLocationBuilding, String foundLocationDetail,
                           String thumbnailPath, int matchRate) {
            this.id = id;
            this.managementNumber = managementNumber;
            this.itemName = itemName;
            this.category = category;
            this.subCategory = subCategory;
            this.foundDate = foundDate;
            this.foundLocationBuilding = foundLocationBuilding;
            this.foundLocationDetail = foundLocationDetail;
            this.thumbnailPath = thumbnailPath;
            this.matchRate = matchRate;
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams matchWrapWithMargin(int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(dp(left), dp(top), dp(right), dp(bottom));
        return params;
    }

    private LinearLayout.LayoutParams fillArea() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1
        );
    }

    private LinearLayout.LayoutParams lowerArea() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(110)
        );
    }

    private LinearLayout.LayoutParams weight(int value, int left, int right) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.MATCH_PARENT,
                value
        );
        params.setMargins(dp(left), 0, dp(right), 0);
        return params;
    }

    private LinearLayout.LayoutParams fieldRightParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(72), 1);
        params.leftMargin = dp(22);
        return params;
    }

    private LinearLayout.LayoutParams bottomButtonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(470), dp(92));
        params.gravity = Gravity.CENTER_HORIZONTAL;
        params.setMargins(0, dp(24), 0, 0);
        return params;
    }

    private LinearLayout.LayoutParams centerButtonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(470), dp(92));
        params.gravity = Gravity.CENTER_HORIZONTAL;
        params.setMargins(0, dp(16), 0, 0);
        return params;
    }

    private LinearLayout.LayoutParams dualButton() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(390), dp(92));
        params.setMargins(dp(16), 0, dp(16), 0);
        return params;
    }

    private LinearLayout.LayoutParams voiceButtonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(245), dp(72));
        params.setMargins(dp(8), 0, dp(8), 0);
        return params;
    }

    private LinearLayout.LayoutParams lockerBoxParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(175), dp(140));
        params.gravity = Gravity.CENTER_HORIZONTAL;
        params.setMargins(0, 0, 0, dp(48));
        return params;
    }

    private LinearLayout.LayoutParams requestNumberBoxParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(360), dp(190));
        params.gravity = Gravity.CENTER_HORIZONTAL;
        params.setMargins(0, 0, 0, dp(70));
        return params;
    }

    private LinearLayout.LayoutParams previewArea() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(560), dp(330));
        params.gravity = Gravity.CENTER_HORIZONTAL;
        return params;
    }
}
