"""
EBS 다큐프라임 콘텐츠 스크래퍼 + Supabase 업로더

사용법:
  python scraper.py                      # 콘텐츠 수집 후 contents.json 저장
  python scraper.py --upload             # 콘텐츠 수집 + Supabase 업로드
  python scraper.py --episodes           # 회차 수집 후 episodes.json 저장
  python scraper.py --episodes --upload  # 회차 수집 + Supabase 업로드
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import sys
import io
import time
from dotenv import load_dotenv

# Windows 터미널에서 한글·특수문자 깨짐 방지 (cp949 → utf-8)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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
# 1. 콘텐츠 목록 스크래핑
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
# 2. 회차(에피소드) 스크래핑
# ============================================================

def scrape_episodes_for(step_id: str) -> list[dict]:
    """특정 step_id 상세 페이지에서 회차 목록을 수집합니다."""
    url = f"{BASE_URL}/docuprime/newReplayList?courseId={COURSE_ID}&stepId={step_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  [오류] {step_id}: {e}")
        return []

    episodes = []
    # lectId 파라미터가 있는 링크를 가진 li 항목 탐색
    for a in soup.find_all("a", href=re.compile(r"lectId=")):
        href = a.get("href", "")
        lect_match = re.search(r"lectId=(\w+)", href)
        if not lect_match:
            continue
        lect_id = lect_match.group(1)

        # 제목: <strong> 태그
        strong = a.find("strong")
        episode_title = strong.get_text(strip=True) if strong else ""

        # 설명: <span class="stit_info"> 태그
        stit = a.find("span", class_="stit_info")
        description = stit.get_text(strip=True) if stit else ""

        # 썸네일
        img = a.find("img")
        thumbnail = (img.get("data-src") or img.get("src", "")) if img else ""

        # 날짜: <span class="date_info">
        date_el = a.find("span", class_="date_info")
        date = date_el.get_text(strip=True) if date_el else ""

        # 조회수·추천수: span.ico-v / span.ico-h (텍스트가 있을 경우)
        views_el = a.find("span", class_=re.compile(r"ico-v"))
        likes_el = a.find("span", class_=re.compile(r"ico-h"))
        views = views_el.get_text(strip=True) if views_el else ""
        likes = likes_el.get_text(strip=True) if likes_el else ""

        episodes.append({
            "step_id":       step_id,
            "lect_id":       lect_id,
            "episode_title": episode_title,
            "description":   description,
            "date":          date,
            "views":         views,
            "likes":         likes,
            "thumbnail":     thumbnail,
            "url":           f"{BASE_URL}{href}",
        })

    return episodes


def scrape_all_episodes(items: list[dict], delay: float = 0.3) -> list[dict]:
    """전체 콘텐츠의 회차를 수집합니다. delay(초) 간격으로 요청."""
    all_episodes = []
    total = len(items)
    for i, item in enumerate(items, 1):
        step_id = item["step_id"]
        if not step_id:
            continue
        eps = scrape_episodes_for(step_id)
        all_episodes.extend(eps)
        print(f"  [{i:3d}/{total}] {item['title'][:20]:<20} → {len(eps)}회차")
        if i < total:
            time.sleep(delay)

    print(f"\n  회차 수집 완료: 총 {len(all_episodes)}개 "
          f"(콘텐츠 {total}개, 평균 {len(all_episodes)/total:.1f}회차/콘텐츠)")
    return all_episodes


def save_episodes_json(episodes: list[dict], path: str = "episodes.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)
    print(f"  JSON 저장: {path}")


# ============================================================
# 3. Supabase 업로드
# ============================================================

def _get_supabase_client():
    try:
        from supabase import create_client
    except ImportError:
        print("  supabase-py 미설치: pip install supabase")
        return None

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not url or url.startswith("https://YOUR"):
        print("  .env의 SUPABASE_URL / SUPABASE_SERVICE_KEY를 설정하세요.")
        return None

    print(f"  Supabase: {url}")
    return create_client(url, key)


def upload_to_supabase(items: list[dict]):
    """contents 테이블에 upsert (step_id 기준 중복 방지)"""
    client = _get_supabase_client()
    if not client:
        return False

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

    chunk_size = 100
    total = 0
    for i in range(0, len(rows), chunk_size):
        client.table("contents").upsert(rows[i:i+chunk_size], on_conflict="step_id").execute()
        total += len(rows[i:i+chunk_size])
        print(f"  contents 업서트: {total}/{len(rows)}")

    print(f"  [완료] contents {total}개 업로드")
    return True


def upload_episodes_to_supabase(episodes: list[dict]):
    """episodes 테이블에 upsert (lect_id 기준 중복 방지)"""
    client = _get_supabase_client()
    if not client:
        return False

    rows = [{
        "step_id":       ep["step_id"],
        "lect_id":       ep["lect_id"],
        "episode_title": ep["episode_title"],
        "description":   ep["description"],
        "date":          ep["date"],
        "views":         ep["views"],
        "likes":         ep["likes"],
        "thumbnail":     ep["thumbnail"],
        "url":           ep["url"],
    } for ep in episodes]

    chunk_size = 100
    total = 0
    for i in range(0, len(rows), chunk_size):
        client.table("episodes").upsert(rows[i:i+chunk_size], on_conflict="lect_id").execute()
        total += len(rows[i:i+chunk_size])
        print(f"  episodes 업서트: {total}/{len(rows)}")

    print(f"  [완료] episodes {total}개 업로드")
    return True


# ============================================================
# 4. 실행
# ============================================================

if __name__ == "__main__":
    do_upload   = "--upload"   in sys.argv
    do_episodes = "--episodes" in sys.argv

    if not do_episodes:
        # ── 콘텐츠 모드 (기본) ──
        print("=== 콘텐츠 수집 모드 ===")
        items = scrape()
        save_json(items)
        if do_upload:
            upload_to_supabase(items)
        else:
            print("\n  Supabase 업로드: python scraper.py --upload")

    else:
        # ── 회차 모드 ──
        print("=== 회차(에피소드) 수집 모드 ===")
        # 기존 contents.json 로드 (이미 수집된 step_id 목록 사용)
        contents_path = "contents.json"
        if not os.path.exists(contents_path):
            print("  contents.json 없음 → 먼저 python scraper.py 실행")
            sys.exit(1)
        with open(contents_path, encoding="utf-8") as f:
            items = json.load(f)
        print(f"  contents.json 로드: {len(items)}개\n")

        episodes = scrape_all_episodes(items, delay=0.3)
        save_episodes_json(episodes)

        if do_upload:
            print()
            upload_episodes_to_supabase(episodes)
        else:
            print("\n  Supabase 업로드: python scraper.py --episodes --upload")
