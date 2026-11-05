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

# ---------- 주소 ----------
# 시·도: 뒤의 \S* 가 특별시/광역시/특별자치시/특별자치도/도/시 를 모두 받는다 (서울특별시, 서울시, 서울 모두 매칭)
_SIDO = (r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청?북|충청?남|"
         r"전라?북|전라?남|경상?북|경상?남|제주)")
# 시·도와 도로명 사이: 시/군/구로 끝나는 행정구역만 허용 (OCR이 '서울 특별시'로 띄어 읽어도 통과)
#   → '서울 출장 가는 길' 같은 일반 문장은 '출장'이 행정구역이 아니라서 걸리지 않는다
_MID = r"(?:[가-힣]{1,6}(?:시|군|구|도|읍|면)\s+){0,3}"
# 도로명/지번: 테헤란로, 테헤란로7길, 을지로3가, 역삼동, 송도동, 봉담읍 ...
_ROAD = r"[가-힣A-Za-z0-9]+(?:로|길|동|읍|면|리|가)"
# 건물번호/지번: 152, 24-5, 산 12, 823-1번지
_NUM = r"(?:\s*(?:산\s?)?\d{1,5}(?:-\d{1,5})?(?:\s?번지)?)"
# 상세주소 (여러 개 연속 가능): (백현동) / 12층 / 1203호 / 101동 / B동 / 지하 1층 / B1층 / 3F / 롯데월드타워
_DETAIL_ONE = (r"(?:\([^)]{1,20}\)"
               r"|(?:지하|B)\s?\d{1,2}\s?층"
               r"|[A-Za-z]?\d{1,5}\s?(?:층|호|동|F)"
               r"|[A-Za-z가-힣]\s?동(?!\S)"
               r"|[가-힣A-Za-z0-9]{1,12}(?:빌딩|타워|아파트|빌라|오피스텔|맨션|센터|프라자|플라자|하우스|"
               r"캐슬|자이|힐스테이트|푸르지오|래미안|오피스))")
_DETAIL = rf"(?:(?:\s*,\s*|\s+){_DETAIL_ONE})*"

ADDRESS_RE = re.compile(
    # 1) 시·도로 시작: 서울특별시 성동구 왕십리로 222 3층
    rf"{_SIDO}\S*\s+{_MID}{_ROAD}{_NUM}?{_DETAIL}"
    # 2) 시·도 생략: 강남구 테헤란로 152 / 강남구 역삼동 823-1 4층
    #    (일반 문장과 헷갈리지 않게 도로명+번호, 또는 동+지번(하이픈)만 허용)
    rf"|(?<![가-힣])[가-힣]{{1,5}}(?:시|군|구)\s+{_MID}"
    rf"(?:[가-힣A-Za-z0-9]+(?:로|길)\s*\d{{1,5}}(?:-\d{{1,5}})?"
    rf"|[가-힣0-9]+(?:동|읍|면|리|가)\s*(?:산\s?)?\d{{1,5}}-\d{{1,5}}(?:\s?번지)?)"
    rf"{_DETAIL}"
)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 주소 라벨이 같은 줄에 있으면 라벨 뒤 전체를 가린다 (정규식이 모르는 형식의 주소도 놓치지 않게)
    ("ADDRESS", re.compile(r"^\s*(?:주소|거주지|배송지|자택\s?주소|현\s?주소)\s*[:：]?\s*(\S.*?)\s*$")),
    # 주소는 숫자 패턴(계좌 일부 등)보다 먼저 검사한다. '송도동 24-56'의 '24-56'을
    # 계좌번호 조각이 먼저 가져가면 겹침 검사 때문에 주소 전체가 빠지기 때문.
    ("ADDRESS", ADDRESS_RE),

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
            # 그룹이 있는 패턴(CVC_OTP, 주소 라벨)은 라벨을 빼고 값 부분만 가린다
            s, e = (m.start(1), m.end(1)) if pat.groups else (m.start(), m.end())

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
    """EasyOCR 결과 [(quad, text, conf), ...] → PII 좌표.
    pad=1 적용으로 불필요한 공백이나 주변 글자가 지워지지 않도록 정밀화
    """
    hits: list[Hit] = []
    lines = [(quad_box(q), str(t)) for q, t, *_ in ocr_results]

    for quad, text, *_ in ocr_results:
        text = str(text)
        for kind, s, e in find_spans(text):
            hits.append(Hit(kind, sub_box(quad, text, s, e, pad=pad)))

    return hits + _label_hits(lines, pad)


def _union(boxes: list[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _corners(b: Box):
    return [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]


def detect_words(ocr_lines: list[list[tuple[str, Box]]], pad: int = 1) -> list[Hit]:
    """Windows OCR 결과 (줄마다 [(단어, 박스), ...]) → PII 좌표.
    단어별 실제 박스를 쓰므로 글자 폭을 추정하는 것보다 정확하다.
    매칭이 단어 일부에만 걸치면 그 단어 안에서만 글자 폭으로 잘라낸다."""
    hits: list[Hit] = []
    lines: list[tuple[Box, str]] = []
    for words in ocr_lines:
        if not words:
            continue
        ranges, pos = [], 0
        for wt, wb in words:
            ranges.append((pos, pos + len(wt), wt, wb))
            pos += len(wt) + 1
        text = " ".join(wt for wt, _ in words)
        lines.append((_union([wb for _, wb in words]), text))
        for kind, s, e in find_spans(text):
            parts = [sub_box(_corners(wb), wt, max(s, a) - a, min(e, b) - a, pad=pad)
                     for a, b, wt, wb in ranges if a < e and s < b]
            if parts:
                hits.append(Hit(kind, _union(parts)))
    return hits + _label_hits(lines, pad)


def _label_hits(lines: list[tuple[Box, str]], pad: int) -> list[Hit]:
    """라벨("CVC", "주소" 등)만 있는 박스 → 오른쪽/아래의 값 박스를 가린다."""
    hits: list[Hit] = []
    for box, text in lines:
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