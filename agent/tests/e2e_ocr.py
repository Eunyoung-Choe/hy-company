"""OCR 포함 종단 확인 (화면 캡처 없이 합성 이미지로).

실행: .venv\\Scripts\\python -m tests.e2e_ocr [출력폴더]
가짜 개인정보가 그려진 이미지를 만들어 EasyOCR → detect → 마스킹을 거치고,
원본/마스킹본을 출력 폴더에 저장한 뒤 감지 유형을 출력한다.
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pii_guard.detect import detect
from pii_guard.masker import black_boxes

LINES = [
    ("고객명", "김하늘"),
    ("주민등록번호", "900101-1234567"),
    ("연락처", "010-1234-5678"),
    ("주소", "서울특별시 성동구 왕십리로 222 3층"),
    ("카드번호", "4111 1111 1111 1111"),
    ("CVC", "123"),
    ("계좌번호", "110-123-456789"),
    ("", "OTP 482913"),
    ("", "상담 메모: 2026-11-05 본인 확인 완료"),
]
EXPECTED = {"RRN", "PHONE", "ADDRESS", "CARD", "CVC_OTP", "ACCOUNT"}


def render() -> np.ndarray:
    img = Image.new("RGB", (900, 40 + 52 * len(LINES)), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 24)
    for i, (label, value) in enumerate(LINES):
        y = 24 + 52 * i
        if label:
            draw.text((30, y), label, fill=(75, 85, 99), font=font)
            draw.text((230, y), value, fill=(20, 20, 20), font=font)
        else:
            draw.text((30, y), value, fill=(20, 20, 20), font=font)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def main() -> int:
    import easyocr

    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = render()
    cv2.imwrite(str(out_dir / "e2e_original.png"), frame)

    reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    t0 = time.perf_counter()
    results = reader.readtext(frame)
    ms = (time.perf_counter() - t0) * 1000
    hits = detect(results)
    for _, text, conf in results:
        print(f"  OCR {conf:.2f} | {text}")
    black_boxes(frame, hits)
    cv2.imwrite(str(out_dir / "e2e_masked.png"), frame)

    found = {h.kind for h in hits}
    print(f"OCR {ms:.0f}ms, boxes={len(hits)}, kinds={sorted(found)}")
    missing = EXPECTED - found
    if missing:
        print("누락:", sorted(missing))
        return 1
    print("OK: 기대한 유형 모두 감지")
    return 0


if __name__ == "__main__":
    sys.exit(main())
