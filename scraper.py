"""
EBS 다큐프라임 콘텐츠 스크래퍼 + Supabase 업로더

사용법:
  python scraper.py            # 수집 후 contents.json 저장
  python scraper.py --upload   # 수집 후 Supabase까지 업로드
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import sys
from dotenv import load_dotenv

load_dotenv()  # .env 파일 로드

BASE_URL  = "https://docuprime.ebs.co.kr"
COURSE_ID = "BP0PAPB0000000005"
LIST_URL  = f"{BASE_URL}/docuprime/newReplay?courseId={COURSE_ID}&main"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 카테고리 ID → 이름 매핑
CATEGORY_MAP = {
    "60002081": "육아",
    "60002082": "인류/문명",
    "60002083": "자연/생태",
    "60002084": "학교교육",
    "60002085": "과학",
    "60002086": "인문",
    "60002087": "가정",
    "60002088": "교육",
    "60002089": "역사",
    "60002090": "정치/사회",
    "60002091": "의학",
    "60002092": "예술/대중문화",
    "60002093": "경제/경영",
}


# ============================================================
# 1. EBS 스크래핑
# ============================================================

def resolve_category(data_category: str) -> str:
    cleaned = data_category.strip().strip("'\"")
    if not cleaned:
        return ""
    ids   = [x.strip().strip("'\"") for x in cleaned.split(",")]
    names = [CATEGORY_MAP[i] for i in ids if i in CATEGORY_MAP]
    return ", ".join(names)


def scrape() -> list[dict]:
    print("▶ EBS 목록 페이지 로딩 중...")
    resp = requests.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for li in soup.select("li[data-title]"):
        title       = li.get("data-title",   "").strip()
        description = li.get("data-content", "").strip()
        data_cat    = li.get("data-category","").strip()

        if not title:
            continue

        a        = li.find("a", attrs={"data-step-id": True})
        step_id  = a.get("data-step-id", "") if a else ""

        img       = li.find("img")
        thumbnail = (img.get("data-src") or img.get("src", "")) if img else ""

        date = ""
        for span in li.select("span"):
            t = span.text.strip()
            if re.match(r"^\d{4}\.\d{2}\.\d{2}$", t):
                date = t
                break

        views_el = li.select_one("span.ico-v")
        likes_el = li.select_one("span.ico-h")

        items.append({
            "step_id":     step_id,
            "title":       title,
            "description": description,
            "date":        date,
            "category":    resolve_category(data_cat),
            "views":       views_el.text.strip() if views_el else "",
            "likes":       likes_el.text.strip() if likes_el else "",
            "thumbnail":   thumbnail,
            "url":         f"{BASE_URL}/docuprime/newReplayList?courseId={COURSE_ID}&stepId={step_id}",
        })

    print(f"  수집 완료: {len(items)}개")
    print(f"  설명 있음: {sum(1 for x in items if x['description'])}/{len(items)}")
    print(f"  카테고리 있음: {sum(1 for x in items if x['category'])}/{len(items)}")
    return items


def save_json(items: list[dict], path: str = "contents.json"):
    # chatbot.html 호환용 키(stepId) 포함 버전 저장
    compat = [{**it, "stepId": it["step_id"]} for it in items]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(compat, f, ensure_ascii=False, indent=2)
    print(f"  JSON 저장: {path}")


# ============================================================
# 2. Supabase 업로드
# ============================================================

def upload_to_supabase(items: list[dict]):
    """contents 테이블에 upsert (step_id 기준 중복 방지)"""
    try:
        from supabase import create_client
    except ImportError:
        print("  ❌ supabase-py 미설치: pip install supabase")
        return False

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

    if not url or url.startswith("https://YOUR"):
        print("  ❌ .env의 SUPABASE_URL / SUPABASE_SERVICE_KEY를 설정하세요.")
        return False

    print(f"\n▶ Supabase 업로드 중... ({url})")
    client = create_client(url, key)

    # Supabase 컬럼명에 맞게 변환 (step_id 사용)
    rows = [{
        "step_id":     it["step_id"],
        "title":       it["title"],
        "description": it["description"],
        "date":        it["date"],
        "category":    it["category"],
        "views":       it["views"],
        "likes":       it["likes"],
        "thumbnail":   it["thumbnail"],
        "url":         it["url"],
    } for it in items]

    # 500개씩 청크 업서트 (Supabase 요청 크기 제한 대응)
    chunk_size = 100
    total_upserted = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        result = client.table("contents").upsert(
            chunk, on_conflict="step_id"
        ).execute()
        total_upserted += len(chunk)
        print(f"  업서트: {total_upserted}/{len(rows)}")

    print(f"  [완료] Supabase 업로드 완료: {total_upserted}개")
    return True


# ============================================================
# 3. 실행
# ============================================================

if __name__ == "__main__":
    do_upload = "--upload" in sys.argv

    # 스크래핑
    items = scrape()

    # 로컬 JSON 저장 (항상)
    save_json(items)

    # Supabase 업로드 (--upload 플래그 또는 .env 설정 시)
    if do_upload:
        success = upload_to_supabase(items)
        if not success:
            print("\n💡 Supabase 연동 없이 로컬 JSON으로 동작합니다.")
    else:
        print("\n💡 Supabase 업로드: python scraper.py --upload")
