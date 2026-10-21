"""pipeline/qtext.py: text-only crops -> common HTML markup (ruby / bold / frames), everything else stays a PNG."""
import sys
from collections import Counter
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from qtext import crop_html, crop_stats, is_plain  # noqa: E402

JA = "japan"  # PyMuPDF built-in CJK font


def _page(draw):
    doc = fitz.open()
    page = doc.new_page(width=516, height=728)
    draw(page)
    return doc


def _region(y0=40, y1=200):
    return [{"page": 0, "y0": y0, "y1": y1}]


def test_furigana_becomes_ruby():
    def draw(p):
        p.insert_text((60, 80), "問１　実際の距離を答えなさい。", fontname=JA, fontsize=11)
        p.insert_text((93, 68), "じっさい", fontname=JA, fontsize=5.5)  # above 実際 (x 93..115)
    html = crop_html(_page(draw), _region())
    assert "<ruby>実際<rt>じっさい</rt></ruby>" in html
    assert "じっさい" not in html.replace("<rt>じっさい</rt>", "")


def test_wrapped_lines_join_and_short_lines_break():
    def draw(p):
        p.insert_text((60, 80), "あ" * 30, fontname=JA, fontsize=11)
        p.insert_text((60, 98), "いいい。", fontname=JA, fontsize=11)
        p.insert_text((60, 116), "うう", fontname=JA, fontsize=11)
    html = crop_html(_page(draw), _region())
    assert html == "あ" * 30 + "いいい。\nうう"


def test_frame_with_text_inside_is_an_inline_box_and_empty_frame_a_blank():
    def draw(p):
        p.insert_text((60, 80), "ア　にあてはまる数は", fontname=JA, fontsize=11)
        p.draw_rect(fitz.Rect(57, 69, 73, 83), width=0.6)          # around ア
        p.draw_rect(fitz.Rect(180, 69, 220, 83), width=0.6)        # empty answer frame on the line
        p.insert_text((224, 80), "です。", fontname=JA, fontsize=11)
    html = crop_html(_page(draw), _region())
    assert '<span class="qbox">ア</span>' in html
    assert '<span class="qbox blank"></span>です。' in html


def test_frame_drawn_as_four_strokes_is_a_box_not_underlines():
    def draw(p):
        p.insert_text((60, 80), "問４　④　にあてはまることばを答えなさい。", fontname=JA, fontsize=11)
        for r in [(90, 68, 107, 68.6), (90, 83, 107, 83.6), (90, 68, 90.6, 83.6), (106.4, 68, 107, 83.6)]:
            p.draw_rect(fitz.Rect(*r), color=None, fill=(0, 0, 0))
    html = crop_html(_page(draw), _region())
    assert '<span class="qbox">④</span>' in html
    assert "<u>" not in html and "blank" not in html


def test_small_letter_on_a_ring_is_one_circled_char():
    def draw(p):
        p.insert_text((60, 80), "下線部○について答えなさい。", fontname=JA, fontsize=11)
        p.insert_text((95.25, 78.5), "あ", fontname=JA, fontsize=6.5)  # centred on ○ (x 93..104)
    html = crop_html(_page(draw), _region())
    assert html.startswith('下線部<span class="maru">あ</span>について')


def test_unreadable_text_layer_keeps_the_image():
    def draw(p):
        p.insert_text((60, 80), "abc def ghi jkl", fontname="helv", fontsize=11)
    assert crop_html(_page(draw), _region()) is None


def test_figures_and_math_layout_are_not_plain():
    def text_with(extra):
        def draw(p):
            p.insert_text((60, 80), "次の図を見て答えなさい。", fontname=JA, fontsize=11)
            extra(p)
        doc = _page(draw)
        page = doc[0]
        clip = fitz.Rect(36, 40, 486, 200)
        return crop_stats(page, clip), page.get_text("text", clip=clip)

    st, txt = text_with(lambda p: None)
    assert is_plain(st, txt, "social")
    assert not is_plain(st, txt, "japanese")
    st, txt = text_with(lambda p: (p.draw_circle((200, 150), 30), p.draw_circle((300, 150), 20)))  # a figure (one circle = 4 curves = a rounded frame)
    assert not is_plain(st, txt, "science")
    st, txt = text_with(lambda p: p.draw_line((100, 150), (115, 150)))  # fraction bar
    assert not is_plain(st, txt, "math")
    assert not is_plain(Counter(chars=20, hchars=20), "1 4 − 1 5", "math")


def _lines(*texts, x=60, size=11):
    def draw(p):
        for i, t in enumerate(texts):
            p.insert_text((x, 80 + i * 18), t, fontname=JA, fontsize=size)
    return draw


def test_list_entries_start_a_new_line_even_after_a_full_line():
    # the reported case: （イ）（ウ） were glued to the line before
    html = crop_html(_page(_lines("（ア）" + "あ" * 27, "い。", "（イ）" + "う" * 27, "（ウ）え。")), _region())
    assert html == "（ア）" + "あ" * 27 + "い。\n（イ）" + "う" * 27 + "\n（ウ）え。"


def test_half_width_kana_markers_and_sentence_end_at_the_edge_break():
    html = crop_html(_page(_lines("か" * 29 + "。", "(ｱ)カエル", "(ｲ)ヘビ")), _region())
    assert html == "か" * 29 + "。\n(ｱ)カエル\n(ｲ)ヘビ"


def test_page_number_bar_is_dropped():
    html = crop_html(_page(_lines("ア．変化しない", "━　0理　10　━", x=60)), _region())
    assert html == "ア．変化しない"


def test_figure_caption_keeps_the_image():
    def draw(p):
        p.insert_text((60, 80), "ふりこの長さを長くしました。", fontname=JA, fontsize=11)
        p.insert_text((400, 80), "図３", fontname=JA, fontsize=11)
    assert crop_html(_page(draw), _region()) is None


def test_photo_stored_as_thin_strips_is_a_raster():
    def draw(p):
        p.insert_text((60, 80), "右の写真を見て答えなさい。", fontname=JA, fontsize=11)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 4), False)
        for k in range(20):  # 20 strips of 300 x 4.5 pt: each one is under the old 1500 pt² limit
            p.insert_image(fitz.Rect(180, 90 + k * 4.5, 480, 94.5 + k * 4.5), pixmap=pix)
    page = _page(draw)[0]
    clip = fitz.Rect(36, 40, 486, 200)
    assert not is_plain(crop_stats(page, clip), "", "social")


def test_answer_column_box_drawn_as_strokes_keeps_the_image():
    def draw(p):
        p.insert_text((60, 80), "かかった時間は何秒ですか。", fontname=JA, fontsize=11)
        for a, b in [((380, 66), (470, 66)), ((380, 110), (470, 110)), ((380, 66), (380, 110)), ((470, 66), (470, 110))]:
            p.draw_line(a, b, width=0.6)
        p.insert_text((450, 104), "秒", fontname=JA, fontsize=11)
    assert crop_html(_page(draw), _region()) is None


def test_kana_followed_by_a_comma_is_not_a_list_marker():
    html = crop_html(_page(_lines("を、次のア～エより一つ選" + "あ" * 17, "び、記号で答えなさい。")), _region())
    assert "\n" not in html
