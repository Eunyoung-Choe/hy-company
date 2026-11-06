import unittest

import numpy as np

from pii_guard.detect import detect, find_spans, luhn_ok, normalize
from pii_guard.masker import Verified, diff_key, mask_frame
from pii_guard.detect import Hit


def q(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def kinds(text):
    return [k for k, *_ in find_spans(text)]


class FindSpans(unittest.TestCase):
    def test_rrn(self):
        self.assertEqual(kinds("주민번호 900101-1234567"), ["RRN"])
        self.assertEqual(kinds("900101-1******"), ["RRN"])
        self.assertEqual(kinds("991399-1234567"), [])  # 13월 없음

    def test_card_luhn(self):
        self.assertEqual(kinds("4111 1111 1111 1111"), ["CARD"])
        self.assertEqual(kinds("4111-1111-1111-1112"), ["CARD"])  # 오인식 대비
        self.assertEqual(kinds("4111111111111112"), [])  # 붙은 16자리는 Luhn 필수
        self.assertEqual(kinds("4111111111111111"), ["CARD"])
        self.assertEqual(kinds("1234-****-****-5678"), ["CARD"])

    def test_phone_not_account(self):
        self.assertEqual(kinds("010-1234-5678"), ["PHONE"])

    def test_account(self):
        self.assertEqual(kinds("신한 110-123-456789"), ["ACCOUNT"])
        self.assertEqual(kinds("2026-11-05"), [])  # 날짜는 계좌 아님

    def test_cvc_otp_inline(self):
        spans = find_spans("OTP 482913")
        self.assertEqual(spans, [("CVC_OTP", 4, 10)])

    def test_address(self):
        self.assertEqual(kinds("서울특별시 성동구 왕십리로 222"), ["ADDRESS"])
        _, s, e = find_spans("주소: 경기도 성남시 분당구 판교역로 235")[0]
        self.assertEqual(e, len("주소: 경기도 성남시 분당구 판교역로 235"))

    def test_address_full(self):
        def addr(text):
            return [text[s:e] for k, s, e in find_spans(text) if k == "ADDRESS"]
        whole = [  # 층·호수·동·건물명까지 통째로
            "서울특별시 강남구 테헤란로 152, 12층 1203호",
            "서울 송파구 올림픽로 300 롯데월드타워 101동 1203호",
            "경기도 성남시 분당구 판교역로 166 (백현동) 5층",
            "서울특별시 강남구 테헤란로7길 22 지하 1층 B101호",
            "인천광역시 연수구 송도동 24-56",
            "경기 화성시 봉담읍 와우리 산 12",
            "강남구 역삼동 823-1 4층",
            "서울특별시 성동구 왕십리로222 3층",
        ]
        for t in whole:
            self.assertEqual(addr(t), [t], t)
        self.assertEqual(addr("주소: 판교 사옥 정문 경비실"), ["판교 사옥 정문 경비실"])  # 라벨 뒤 전체
        for t in ("서울 출장 가는 길에 들렀어요", "연구 활동 3건 진행", "다음 주 서울 방문 예정"):
            self.assertEqual(addr(t), [], t)

    def test_ocr_fix(self):
        self.assertEqual(normalize("9OO1O1-1234567"), "900101-1234567")
        self.assertEqual(normalize("OTP"), "OTP")
        self.assertEqual(kinds("9OO1O1-l234567"), ["RRN"])

    def test_luhn(self):
        self.assertTrue(luhn_ok("4111111111111111"))
        self.assertFalse(luhn_ok("4111111111111112"))


class Detect(unittest.TestCase):
    def test_sub_box_inside_line(self):
        hits = detect([(q(100, 10, 500, 40), "주민번호 900101-1234567", 0.9)], pad=0)
        self.assertEqual(len(hits), 1)
        x0, y0, x1, y1 = hits[0].box
        self.assertGreater(x0, 100)  # 라벨 부분은 제외
        self.assertEqual(x1, 500)
        self.assertEqual((y0, y1), (10, 40))

    def test_label_then_value_right(self):
        res = [(q(10, 10, 60, 30), "CVC", 0.9), (q(80, 10, 120, 30), "123", 0.9),
               (q(10, 60, 60, 80), "123", 0.9)]
        hits = detect(res, pad=0)
        self.assertEqual(hits, [Hit("CVC_OTP", (80, 10, 120, 30))])

    def test_label_then_value_below(self):
        res = [(q(10, 10, 60, 30), "주소", 0.9), (q(10, 38, 300, 58), "어딘가 123번지", 0.9)]
        self.assertEqual(detect(res, pad=0), [Hit("ADDRESS", (10, 38, 300, 58))])

    def test_no_pii(self):
        self.assertEqual(detect([(q(0, 0, 100, 20), "안녕하세요 2026-11-05", 0.9)]), [])


class Mask(unittest.TestCase):
    def test_unverified_frame_fully_hidden(self):
        f = np.zeros((40, 40, 3), np.uint8)
        f[::2, ::2] = 255
        out, pending = mask_frame(f.copy(), Verified())
        self.assertEqual(pending, 1)
        self.assertLess(np.abs(out.astype(int) - 64).max(), 200)  # 체커 패턴이 뭉개짐

    def test_black_box_and_changed_region(self):
        base = np.full((100, 200, 3), 200, np.uint8)
        v = Verified(seq=0, ref_key=diff_key(base), hits=[Hit("RRN", (10, 10, 50, 30))])
        f = base.copy()
        out, pending = mask_frame(f, v)
        self.assertEqual(pending, 0)
        self.assertTrue((out[10:31, 10:51] == 0).all())

        changed = base.copy()
        changed[60:80, 120:180] = 0
        changed[60:80:2, 120:180:2] = 255  # 새 내용(검증 전)
        out, pending = mask_frame(changed, v)
        self.assertGreaterEqual(pending, 1)
        self.assertFalse((out[60:80:2, 120:180:2] == 255).all())  # 원래 패턴 그대로 송출되지 않음


if __name__ == "__main__":
    unittest.main()


class Incremental(unittest.TestCase):
    def test_strips_full_width_merge_and_extend(self):
        from pii_guard.workers import _strips
        regions = [(500, 400, 50, 20), (100, 430, 30, 20), (0, 900, 10, 10)]
        hits = [Hit("ADDRESS", (0, 250, 300, 290))]  # 띠 경계(280)에 걸친 박스
        self.assertEqual(_strips(regions, hits, 1000), [(242, 490), (780, 950)])

    def test_ocr_offsets_and_scale(self):
        from pii_guard.workers import _ocr

        class Fake:
            def readtext(self, img):
                return [(q(10, 5, 110, 25), "900101-1234567", 0.9)]

        img = np.zeros((60, 400, 3), np.uint8)
        (hit,) = _ocr(Fake(), img, 0.5, 300)
        self.assertEqual(hit.kind, "RRN")
        self.assertEqual(hit.box, (14, 304, 226, 356))  # (좌표-3패딩) / 0.5 + y오프셋


class HoldVerified(unittest.TestCase):
    def test_pending_region_shows_last_verified_not_original(self):
        base = np.full((100, 200, 3), 200, np.uint8)
        held = base.copy()
        held[10:31, 10:51] = 0  # 검증본(이미 마스킹)
        v = Verified(seq=0, ref_key=diff_key(base), hits=[Hit("RRN", (10, 10, 50, 30))], masked_frame=held)
        changed = base.copy()
        changed[60:80, 120:180] = 7  # 검증 전 새 내용
        out, pending = mask_frame(changed, v)
        self.assertGreaterEqual(pending, 1)
        self.assertTrue((out[60:80, 120:180] == 200).all())  # 직전 검증본으로 보류
        self.assertTrue((out[10:31, 10:51] == 0).all())

    def test_no_pending_regions_does_not_crash(self):
        base = np.full((50, 50, 3), 200, np.uint8)
        v = Verified(seq=0, ref_key=diff_key(base), masked_frame=base.copy())
        out, pending = mask_frame(base.copy(), v)
        self.assertEqual(pending, 0)


def _page(h=1400, w=400, seed=0):
    """글자처럼 보이는 무늬가 줄마다 다른 긴 페이지 (스크롤 테스트용)."""
    rng = np.random.default_rng(seed)
    page = np.full((h, w, 3), 230, np.uint8)
    for y in range(10, h - 20, 22):
        x = 10
        while x < w - 30:
            ww = int(rng.integers(8, 40))
            page[y:y + 12, x:x + ww] = int(rng.integers(0, 90))
            x += ww + int(rng.integers(4, 14))
    return page


class ScrollCompensation(unittest.TestCase):
    def setUp(self):
        from pii_guard.masker import DIFF_SCALE
        self.page, self.view = _page(), 600
        self.f0 = self.page[0:self.view].copy()
        self.pii = (100, 300, 220, 316)  # 처음 화면의 개인정보 박스
        held = self.f0.copy()
        held[300:317, 100:221] = 0
        self.v = Verified(seq=0, ref_key=diff_key(self.f0), hits=[Hit("RRN", self.pii)], masked_frame=held)
        self.scale = DIFF_SCALE

    def test_estimate_scroll(self):
        from pii_guard.masker import estimate_scroll
        for off in (10, 60, 200):
            cur = diff_key(self.page[off:off + self.view])
            self.assertEqual(estimate_scroll(cur, self.v.ref_key), round(-off * self.scale), off)
        self.assertEqual(estimate_scroll(self.v.ref_key, self.v.ref_key), 0)  # 그대로면 0

    def test_scrolled_frame_moves_box_and_shows_current_content(self):
        off = 80
        cur = self.page[off:off + self.view].copy()
        out, pending = mask_frame(cur.copy(), self.v)
        x0, y0, x1, y1 = self.pii
        self.assertTrue((out[y0 - off:y1 - off + 1, x0:x1 + 1] == 0).all())  # 박스가 내용을 따라 이동
        mid = slice(100, 200)  # 개인정보와 새로 드러난 띠를 뺀 곳은 지금 화면 그대로
        self.assertTrue((out[mid] == cur[mid]).all())
        self.assertEqual(pending, 1)  # 새로 드러난 띠 하나만 검증 대기

    def test_new_content_during_scroll_is_still_held(self):
        off = 80
        cur = self.page[off:off + self.view].copy()
        cur[150:170, 200:380] = 5  # 스크롤과 동시에 새로 뜬 내용 (검증 전)
        out, pending = mask_frame(cur.copy(), self.v)
        self.assertFalse((out[150:170, 200:380] == 5).all())  # 원본 그대로 송출되지 않음
        self.assertGreaterEqual(pending, 2)


class AddressOcrNoise(unittest.TestCase):
    """실측한 Windows OCR 오인식에서도 주소 끝(층수)까지 가리는지."""

    def addr(self, text):
        return [text[s:e] for k, s, e in find_spans(text) if k == "ADDRESS"]

    def test_floor_misread(self):
        for t in ("서울특별시 성동구 왕십리로 222 3좋", "대전광역시 유성구 대학로 99 12증",
                  "서을특별시 강남구 테해란로 152 7 증", "경기도 성남시 부 당구 판교 역로 235 3좋",
                  "이진국광역시 연丁구 -도과학로 32 3증", "서울특별시 A러동구 왕치리로 222 7증"):
            got = self.addr(t)
            self.assertTrue(got and t.endswith(got[0]), (t, got))

    def test_floor_does_not_eat_phone(self):
        t = "서울특별시 성동구 왕십리로 222 3층 010-1234-5678"
        self.assertEqual(self.addr(t), ["서울특별시 성동구 왕십리로 222 3층"])
        self.assertIn("PHONE", kinds(t))

    def test_not_address(self):
        for t in ("경기 결과 3대 2 승리", "부산 지사 3층 회의실", "강남역 2번 출구 앞에서 만나요"):
            self.assertEqual(self.addr(t), [], t)

    def test_split_line_is_merged(self):
        from pii_guard.detect import detect_words
        # OCR이 한 줄을 두 덩어리로 끊어 읽은 경우: '인천광역시 연수구' | '송도과학로 32 3층'
        lines = [[("인천광역시", (10, 10, 80, 30)), ("연수구", (88, 10, 130, 30))],
                 [("송도과학로", (140, 10, 210, 30)), ("32", (218, 10, 232, 30)), ("3층", (240, 10, 262, 30))]]
        (hit,) = [h for h in detect_words(lines, pad=0) if h.kind == "ADDRESS"]
        self.assertLessEqual(hit.box[0], 10)
        self.assertGreaterEqual(hit.box[2], 262)


class DigitGapOcrNoise(unittest.TestCase):
    """OCR이 숫자 사이에 끼워 넣은 띄어쓰기 (실측)에도 주민번호·OTP를 통째로 가리는지."""

    def test_rrn_with_gaps(self):
        for t in ("670620-1 109281", "96061 1-2979711", "8201 1 5-2291703"):
            self.assertEqual(find_spans(t), [("RRN", 0, len(t))], t)

    def test_otp_with_gaps(self):
        for t in ("OTP 01 4620", "OTP 1 68493"):
            self.assertEqual(find_spans(t), [("CVC_OTP", 4, len(t))], t)

    def test_spaced_numbers_untouched(self):
        self.assertEqual(kinds("4111 1111 1111 1111"), ["CARD"])
        self.assertEqual(kinds("010 1234 5678"), ["PHONE"])
        self.assertEqual(kinds("가입일 2024 03 02"), [])


class WrappedAccount(unittest.TestCase):
    """계좌번호가 줄바꿈으로 '110-123-' | '456789' 두 줄에 걸친 경우 (Tahoma 글꼴 데모 메모에서 실측)."""

    def test_line_end_chain(self):
        t = "환불은 신한은행 110-123-"
        self.assertIn(("ACCOUNT_PART", t.index("110"), len(t)), find_spans(t))

    def test_next_line_head_is_masked(self):
        from pii_guard.detect import detect_words
        lines = [[("환불은", (10, 10, 60, 30)), ("신한은행", (66, 10, 130, 30)), ("110-123-", (136, 10, 220, 30))],
                 [("456789", (10, 40, 70, 60)), ("로", (76, 40, 90, 60)), ("진행.", (96, 40, 130, 60))]]
        hits = detect_words(lines, pad=0)
        heads = [h for h in hits if h.box[1] >= 40]
        self.assertTrue(heads and heads[0].box[0] <= 10 and heads[0].box[2] >= 70, hits)
        self.assertFalse(any(h.box[0] >= 76 and h.box[1] >= 40 for h in hits))  # '로 진행.'은 가리지 않음
