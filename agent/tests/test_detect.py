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
