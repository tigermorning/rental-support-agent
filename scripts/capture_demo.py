"""데모 화면 캡처. 사용법: streamlit run app.py 를 띄운 상태에서 python scripts/capture_demo.py

설치된 Chrome 을 Playwright 로 띄워 문의를 입력하고 docs/images/ 에 PNG 로 저장한다.
문의는 평가셋에 없는 문장만 쓴다. API 를 부르므로 문의 수만큼 비용이 든다.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
URL = "http://localhost:8501"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SHOTS = [
    ("demo-answer", "집주인이 제 직장 이름까지 볼 수 있어요?"),
    ("demo-escalate", "소유 확인 서류 검토는 보통 며칠 걸려요?"),
    ("demo-out-of-scope", "연말정산 때 월세 공제 받으려면 뭐가 필요해요?"),
]


def ask(page, q):
    box = page.get_by_placeholder("직거래 서비스 이용에 대해 물어보세요", exact=False)
    box.fill(q)
    box.press("Enter")
    page.get_by_text("완료", exact=True).wait_for(timeout=120_000)
    page.wait_for_timeout(1500)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=1)
        for name, q in SHOTS:
            page.goto(URL)
            page.get_by_placeholder("직거래 서비스 이용에 대해 물어보세요", exact=False).wait_for(timeout=60_000)
            ask(page, q)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("저장:", OUT / f"{name}.png")
            if name == "demo-answer":
                # Streamlit 은 본문이 안쪽 컨테이너에서 스크롤돼 full_page 로 아래가 안 찍힌다
                page.get_by_text("조회한 조항", exact=False).first.scroll_into_view_if_needed()
                page.mouse.move(850, 500)   # 사이드바가 아니라 본문 위에서 굴려야 본문이 스크롤된다
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(1000)
                page.screenshot(path=str(OUT / f"{name}-clauses.png"))
                print("저장:", OUT / f"{name}-clauses.png")

        page.goto(URL)
        page.get_by_role("tab", name="평가 결과").click()
        page.get_by_text("한 번이라도 실패한 문항").wait_for(timeout=60_000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "demo-eval-tab.png"))
        print("저장:", OUT / "demo-eval-tab.png")
        browser.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
