"""P0-тесты чистого ядра вьюпорта пин-окна (viewport.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import viewport


class TestClampOffset:
    def test_content_bigger_clamps_to_bounds(self):
        # вьюпорт 100, контент 300: offset в [0, 200]
        assert viewport.clamp_offset((-50, 500), (100, 100), (300, 300)) == (0, 200)
        assert viewport.clamp_offset((150, 60), (100, 100), (300, 300)) == (150, 60)

    def test_content_smaller_centers(self):
        # контент меньше вьюпорта — центровка (отрицательный offset)
        ox, oy = viewport.clamp_offset((0, 0), (200, 200), (100, 80))
        assert ox == (100 - 200) / 2
        assert oy == (80 - 200) / 2
        # центровка не зависит от желаемого offset
        assert viewport.clamp_offset((999, -999), (200, 200), (100, 80)) == (ox, oy)

    def test_content_equal_view(self):
        assert viewport.clamp_offset((10, -10), (100, 100), (100, 100)) == (0, 0)


class TestCenterOn:
    def test_point_lands_in_view_center(self):
        ox, oy = viewport.center_on((500, 300), (200, 200), (2000, 2000))
        assert (500 - ox, 300 - oy) == (100, 100)  # точка ровно в центре

    def test_clamped_at_frame_edge(self):
        # точка у левого края кадра — вьюпорт прижат к нулю, центр не достижим
        ox, oy = viewport.center_on((10, 10), (200, 200), (2000, 2000))
        assert (ox, oy) == (0, 0)


class TestInitialView:
    FRAME = (3840, 1080)  # два монитора
    AVAIL = (1500, 800)

    def test_small_selection_zoom_100_window_fits_selection(self):
        # небольшая рамка: зум 1:1 (без растяжения), вьюпорт — рамка ~75%
        vw, vh, zoom, offset = viewport.initial_view(
            (1000, 300, 400, 200), self.FRAME, self.AVAIL)
        assert zoom == 1.0
        assert (vw, vh) == (round(400 / 0.75), round(200 / 0.75))
        # рамка по центру вьюпорта
        ox, oy = offset
        assert (1000 + 200) - ox == vw / 2
        assert (300 + 100) - oy == vh / 2

    def test_big_selection_zooms_down_never_up(self):
        # рамка больше avail: зум < 1 и рамка целиком видна (занимает ~75%)
        vw, vh, zoom, _offset = viewport.initial_view(
            (500, 100, 3000, 900), self.FRAME, self.AVAIL)
        assert (vw, vh) == self.AVAIL
        assert zoom < 1.0
        assert 3000 * zoom == pytest.approx(0.75 * vw, abs=1)
        assert 900 * zoom <= vh

    def test_zoom_never_exceeds_100_percent(self):
        # рамка крошечная, вьюпорта много — растяжения нет
        _, _, zoom, _ = viewport.initial_view((100, 100, 24, 24), self.FRAME, self.AVAIL)
        assert zoom == 1.0

    def test_offset_stays_within_frame(self):
        # рамка у правого нижнего края кадра — вьюпорт не вылезает за кадр
        vw, vh, zoom, offset = viewport.initial_view(
            (3740, 980, 100, 100), self.FRAME, self.AVAIL)
        ox, oy = offset
        assert 0 <= ox <= self.FRAME[0] * zoom - vw
        assert 0 <= oy <= self.FRAME[1] * zoom - vh

    def test_rejects_nonpositive_sizes(self):
        with pytest.raises(ValueError):
            viewport.initial_view((0, 0, 0, 100), self.FRAME, self.AVAIL)
        with pytest.raises(ValueError):
            viewport.initial_view((0, 0, 100, 100), self.FRAME, (0, 800))


class TestScrollBars:
    """Полосы прокрутки вьюпорта: видимость и синхронизация."""

    THICK = 10

    def _bars(self, view, content, offset=(0, 0)):
        return viewport.scroll_bars(view, content, offset,
                                    thickness=self.THICK)

    def test_hidden_when_frame_fits(self):
        bars = self._bars((800, 600), (800, 600))
        assert not bars.vertical and not bars.horizontal
        assert (bars.view_w, bars.view_h) == (800, 600)
        assert (bars.max_v, bars.max_h) == (0, 0)

    def test_hidden_when_frame_smaller(self):
        # кадр меньше окна — центровка, ползунков нет
        bars = self._bars((800, 600), (400, 300), offset=(-200, -150))
        assert not bars.vertical and not bars.horizontal
        assert (bars.value_v, bars.value_h) == (0, 0)

    def test_both_visible_when_frame_bigger(self):
        bars = self._bars((800, 600), (1200, 900))
        assert bars.vertical and bars.horizontal
        # видимая полоса ужимает вьюпорт — кадр под ней не рисуется
        assert bars.view_w == 800 - self.THICK
        assert bars.view_h == 600 - self.THICK
        assert bars.max_v == 900 - bars.view_h
        assert bars.max_h == 1200 - bars.view_w

    def test_vertical_only(self):
        # кадр шире вьюпорта с запасом на полосу — горизонталь не нужна
        bars = self._bars((800, 600), (700, 900))
        assert bars.vertical and not bars.horizontal
        assert bars.view_h == 600  # высота цела: горизонтальной полосы нет
        assert bars.view_w == 800 - self.THICK  # вертикаль съела ширину

    def test_horizontal_only(self):
        bars = self._bars((800, 600), (900, 500))
        assert bars.horizontal and not bars.vertical
        assert bars.view_w == 800  # ширина цела: вертикальной полосы нет
        assert bars.view_h == 600 - self.THICK

    def test_narrow_overshoot_adds_second_bar(self):
        # кадр шире окна всего на 4 px, но появившаяся вертикаль делает
        # горизонталь нужной — иначе кадр остался бы обрезан справа
        bars = self._bars((800, 600), (795, 900))
        assert bars.vertical and bars.horizontal

    def test_values_follow_offset(self):
        bars = self._bars((800, 600), (1200, 900), offset=(120, 80))
        assert (bars.value_h, bars.value_v) == (120, 80)

    def test_values_clamped_to_range(self):
        bars = self._bars((800, 600), (1200, 900), offset=(9999, 9999))
        assert (bars.value_h, bars.value_v) == (bars.max_h, bars.max_v)

    def test_bars_take_exactly_their_thickness(self):
        # кадр шире окна чуть меньше, чем на толщину полосы: появляется
        # вторая полоса, и обе забирают ровно свою толщину — краевого
        # зазора нет, полосы прижаты к краю окна
        bars = self._bars((800, 600), (795, 900))
        assert bars.vertical and bars.horizontal
        assert bars.view_w == 800 - self.THICK
        assert bars.view_h == 600 - self.THICK
