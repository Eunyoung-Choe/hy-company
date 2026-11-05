"""
detector.py - 순수 개인정보만 정교하게 감지하여 BBOX를 반환하는 모듈
"""
from __future__ import annotations

import re
from dataclasses import dataclass

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (픽셀)


@dataclass(frozen=True)
class Hit:
    kind: str
    box: Box


# ---------- 패턴 (개인정보 식별 정규식) ----------
_DATE6 = r"\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 주민등록번호 / 외국인등록번호
    ("RRN", re.compile(rf"(?<!\d){_DATE6}\s?-?\s?[1-8][\d*]{{6}}(?!\d)")),

    # 휴대폰 번호
    ("PHONE", re.compile(r"(?<!\d)01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)")),

    # 카드번호
    ("CARD", re.compile(r"(?<!\d)\d{4}[\s-]?[\d*]{4}[\s-]?[\d*]{4}[\s-]?[\d*]{4}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}(?!\d)")),

    # 계좌번호 (완전한 양식)
    ("ACCOUNT", re.compile(r"(?<!\d)\d{2,6}-\d{2,6}-\d{2,7}(?:-\d{1,3})?(?!\d)")),

    # [줄바꿈 대응] 줄 끝에 잘린 계좌번호 (예: "110-") 또는 줄 시작의 계좌 나머지 (예: "123-456789")
    ("ACCOUNT_PART", re.compile(r"(?<!\d)\d{2,6}-(?:$|\s)")),
    ("ACCOUNT_PART", re.compile(r"(?:^|\s)\d{2,6}-\d{2,7}(?:-\d{1,3})?(?!\d)")),

    # CVC / CVV / OTP / 보안코드
    ("CVC_OTP", re.compile(r"(?:CVC|CVV|OTP|인증\s?번호|보안\s?코드)\D{0,6}(\d{3,8})", re.I)),

    # 도로명/지번 주소 (실제 주소 구문 끝까지만 정확히 매칭 -> 과마스킹 방지)
    ("ADDRESS", re.compile(
        r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청?북|충청?남|전라?북|전북특별|"
        r"전라?남|경상?북|경상?남|제주)\S*\s+(?:\S+\s+){0,2}?\S+(?:로|길|동|읍|면|리)(?:\s*\d[\d-]*)?"
    )),
]

# 라벨과 값이 별도 박스로 분리된 경우 (은행명 라벨 추가)
LABELS: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = [
    ("CVC_OTP", re.compile(r"^(CVC|CVV|OTP|인증\s?번호|보안\s?코드|비밀\s?번호)$", re.I), re.compile(r"^\d{3,8}$")),
    ("ADDRESS", re.compile(r"^(주소|거주지|배송지)$"), re.compile(r"\S{2,}")),
    ("RRN", re.compile(r"^주민(등록)?\s?번호$"), re.compile(r"^\d{6}")),
    ("ACCOUNT", re.compile(r"^(계좌|계좌\s?번호|신한|국민|우리|하나|농협|기업|카카오|토스|우체국)$"), re.compile(r"\d{2,}")),
    ("CARD", re.compile(r"^카드\s?번호$"), re.compile(r"^\d{4}")),
]

_LABEL_ONLY_MAX_EXTRA = 4

# OCR 오인식 보정
_FIX_0 = re.compile(r"(?<=\d)[Oo]|[Oo](?=\d)")
_FIX_1 = re.compile(r"(?<=\d)[lI|]|[lI|](?=\d)")


def normalize(text: str) -> str:
    text = _FIX_0.sub("0", text)
    return _FIX_1.sub("1", text)


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def _valid(kind: str, matched: str) -> bool:
    digits = re.sub(r"\D", "", matched)
    if kind == "CARD":
        return "*" in matched or bool(re.search(r"[\s-]", matched)) or luhn_ok(digits)
    if kind in ("ACCOUNT", "ACCOUNT_PART"):
        # 하이픈(-)이 존재하고 숫자가 3자리 이상일 때만 허용 (일반 일반 텍스트/숫자 과마스킹 방지)
        return "-" in matched and len(digits) >= 3
    return True


def find_spans(text: str) -> list[tuple[str, int, int]]:
    t = normalize(text)
    taken: list[tuple[int, int]] = []
    out: list[tuple[str, int, int]] = []

    for kind, pat in PATTERNS:
        for m in pat.finditer(t):
            s, e = (m.start(1), m.end(1)) if kind == "CVC_OTP" else (m.start(), m.end())

            if not _valid(kind, m.group()):
                continue

            # 중복 영역 제외
            if any(s < te and ts < e for ts, te in taken):
                continue

            taken.append((s, e))
            out.append((kind, s, e))

    return out


# ---------- 좌표 산출 및 패딩 최적화 ----------
def _char_w(ch: str) -> float:
    if ch.isspace():
        return 0.35
    if "가" <= ch <= "힣" or "㄰" <= ch <= "㆏" or "一" <= ch <= "鿿":
        return 1.0
    return 0.58


def quad_box(quad) -> Box:
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def sub_box(quad, text: str, start: int, end: int, pad: int = 1) -> Box:
    """패딩(pad) 기본값을 1픽셀로 최소화하여 개인정보 글자 영역만 타이트하게 자름"""
    x0, y0, x1, y1 = quad_box(quad)
    widths = [_char_w(c) for c in text] or [1.0]
    total = sum(widths)

    a = sum(widths[:start]) / total
    b = sum(widths[:end]) / total
    w = x1 - x0

    return (
        max(0, int(x0 + w * a) - pad),
        max(0, y0 - pad),
        int(x0 + w * b) + pad,
        y1 + pad
    )


def _pad(box: Box, pad: int = 1) -> Box:
    return max(0, box[0] - pad), max(0, box[1] - pad), box[2] + pad, box[3] + pad


def _value_box_for(label: Box, boxes: list[tuple[Box, str]], value_re: re.Pattern[str]) -> int | None:
    lx0, ly0, lx1, ly1 = label
    lh = max(1, ly1 - ly0)
    best, best_d = None, float("inf")

    for i, (b, text) in enumerate(boxes):
        if b == label or not value_re.search(text):
            continue
        bx0, by0, bx1, by1 = b
        overlap = min(ly1, by1) - max(ly0, by0)

        # 오른쪽 (같은 줄)
        if overlap > 0.4 * lh and bx0 >= lx1 - 4 and bx0 - lx1 < 25 * lh:
            d = bx0 - lx1
        # 바로 아래 줄
        elif by0 >= ly1 - 4 and by0 - ly1 < 1.8 * lh and bx0 < lx1 + 2 * lh and bx1 > lx0:
            d = (by0 - ly1) + 1000
        else:
            continue

        if d < best_d:
            best, best_d = i, d

    return best


def detect(ocr_results, pad: int = 1) -> list[Hit]:
    """
    pad=1 적용으로 불필요한 공백이나 주변 글자가 지워지지 않도록 정밀화
    """
    hits: list[Hit] = []
    lines = [(quad_box(q), str(t)) for q, t, *_ in ocr_results]

    for (quad, text, *_), (box, _) in zip(ocr_results, lines):
        text = str(text)

        for kind, s, e in find_spans(text):
            hits.append(Hit(kind, sub_box(quad, text, s, e, pad=pad)))

        for kind, label_re, value_re in LABELS:
            m = label_re.search(text)
            if not m:
                continue
            rest = (text[: m.start()] + text[m.end():]).strip(" :：-")
            if len(rest) > _LABEL_ONLY_MAX_EXTRA:
                continue

            j = _value_box_for(box, lines, value_re)
            if j is not None:
                hits.append(Hit(kind, _pad(lines[j][0], pad=pad)))

    return hits