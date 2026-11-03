from __future__ import annotations

import os
import gc
import tempfile
import time
import tkinter as tk
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk
from unittest import mock

from PIL import Image, ImageTk

from seedbank.desktop import render
from seedbank.desktop.app import CompanionWindow
from seedbank.desktop.dates import DateList
from seedbank.desktop.pet import PetStage
from seedbank.desktop.theme import PALETTES, Theme, style_native_widgets
from seedbank.desktop.widgets import Button, Card, Input, MessageBubble, PillScrollbar, Scroll, Select, Toggle, reader, set_reader
from seedbank.desktop.wizard import SetupWizard
from seedbank.i18n import set_locale
from seedbank.pack import hatch


EGG = Path(__file__).resolve().parents[2] / "eggs" / "dafeiyu.egg"


class QuietActivityNoticeTest(unittest.TestCase):
    def test_private_activity_refreshes_without_speech_notification(self):
        window = SimpleNamespace(_set_busy=mock.Mock(), apply_snapshot=mock.Mock(), notify=mock.Mock())
        CompanionWindow._on_clock(window, {"snapshot": {"revision": 2},
                                          "spoken": {"reply": "", "learningChanges": 1}})
        window.apply_snapshot.assert_called_once_with({"revision": 2})
        window.notify.assert_not_called()
        CompanionWindow._on_clock(window, {"spoken": {"reply": "我有一个想法。"}})
        window.notify.assert_called_once()


class RenderingTest(unittest.TestCase):
    def panel(self, size, theme="cream", **options):
        colors = PALETTES[theme]
        return render.panel_image(size, background=colors["background"], fill=colors["surface"],
                                  border=colors["border"], shadow=colors["shadow"], **options)

    def test_rounded_edges_have_blended_pixels_in_all_themes(self):
        for theme in PALETTES:
            with self.subTest(theme=theme):
                panel = self.panel((220, 150), theme)
                self.assertEqual(panel.size, (220, 150))
                self.assertGreater(len(panel.crop((0, 0, 28, 28)).getcolors(784)), 12)
                self.assertEqual(panel.getpixel((0, 0))[:3], tuple(bytes.fromhex(PALETTES[theme]["background"][1:])))
                self.assertEqual(panel.getpixel((110, 75))[:3], tuple(bytes.fromhex(PALETTES[theme]["surface"][1:])))

    def test_nine_slice_does_not_stretch_corners(self):
        small = self.panel((120, 100))
        large = self.panel((1000, 700))
        self.assertEqual(small.crop((0, 0, 28, 28)).tobytes(), large.crop((0, 0, 28, 28)).tobytes())
        self.assertEqual(small.crop((92, 72, 120, 100)).tobytes(), large.crop((972, 672, 1000, 700)).tobytes())

    def test_panel_strips_match_full_surface_pixels(self):
        for theme in PALETTES.values():
            for size in ((8, 8), (16, 12), (400, 200), (1000, 700)):
                for focused in (False, True):
                    options = dict(background=theme["background"], fill=theme["surface"],
                                   border=theme["primary"] if focused else theme["surface"],
                                   shadow=theme["background"], border_width=2 if focused else 1)
                    rebuilt = Image.new("RGBA", size, theme["surface"])
                    strips = render.panel_strips(size, **options)
                    for horizontal, vertical, strip in strips:
                        rebuilt.paste(strip, (horizontal, vertical))
                    self.assertEqual(rebuilt.tobytes(), render.panel_image(size, **options).tobytes())
                    if size == (1000, 700):
                        self.assertLess(sum(strip.width * strip.height for _, _, strip in strips), 150000)

    def test_glass_rim_keeps_native_text_surface_flat_and_corners_unstretched(self):
        for key, colors in PALETTES.items():
            with self.subTest(theme=key):
                options = {"glaze": colors["glass_glow"], "refraction": colors["glass_refraction"]}
                small = self.panel((220, 150), key, **options)
                large = self.panel((1000, 700), key, **options)
                self.assertEqual(small.getpixel((110, 75))[:3], tuple(bytes.fromhex(colors["surface"][1:])))
                self.assertEqual(small.crop((0, 0, 28, 28)).tobytes(), large.crop((0, 0, 28, 28)).tobytes())
                self.assertNotEqual(small.tobytes(), self.panel((220, 150), key).tobytes())
                for size in ((8, 8), (16, 12), (46, 46), (240, 80)):
                    self.assertEqual(self.panel(size, key, border_width=2, **options).size, size)

    def test_small_surfaces_and_focus_outline(self):
        for size in ((8, 8), (16, 12), (20, 46), (46, 46), (180, 53)):
            with self.subTest(size=size):
                self.assertEqual(self.panel(size, radius=16, border_width=2).size, size)

    def test_all_icons_have_antialiased_alpha(self):
        for name in ("home", "book", "heart", "leaf", "settings", "photo", "send", "moon", "plus", "search", "chevron_down"):
            for size in (18, 20, 25, 30):
                with self.subTest(name=name, size=size):
                    picture = render.icon_image(name, size, "#7150A5")
                    levels = set(picture.getchannel("A").tobytes())
                    self.assertIn(0, levels)
                    self.assertTrue(any(0 < level < 255 for level in levels))

    def test_character_fits_continuously_without_pixel_skipping(self):
        # A smooth 8-bit ramp can round to exactly the same pixels for nearest
        # and Lanczos at some ratios. Fine detail makes lost filtering visible.
        original = Image.new("RGBA", (240, 260))
        original.putdata([(255, 255, 255, 255) if (x + y) % 2 else (0, 0, 0, 255)
                          for y in range(260) for x in range(240)])
        for size in ((210, 228), (250, 269), (255, 270), (320, 480)):
            with self.subTest(size=size):
                fitted = render.fit_character(original, *size)
                self.assertLessEqual(fitted.width, size[0] - 19)
                self.assertLessEqual(fitted.height, size[1] * .84 + 1)
                self.assertAlmostEqual(fitted.width / fitted.height, original.width / original.height, delta=.01)
                if fitted.size != original.size:
                    self.assertFalse(fitted.tobytes() == original.resize(fitted.size, Image.Resampling.NEAREST).tobytes(),
                                     "Fine detail was resized without filtering")

    def test_stage_and_energy_bar_sizes(self):
        for theme in PALETTES:
            for size in ((210, 180), (280, 300), (420, 450)):
                self.assertEqual(render.stage_image(size, Theme(theme)).size, size)
            for energy in (0, .01, .5, 1):
                picture = render.meter_image((240, 24), energy, "#FFFFFF", "#EEEEEE", "#7150A5")
                self.assertEqual(picture.size, (240, 24))

    def test_font_sizes_remain_legible(self):
        self.assertEqual(Theme().font(12)[1], -13)
        self.assertEqual(Theme().font()[1], -16)
        self.assertLess(Theme(scale=1.15).font()[1], Theme().font()[1])

    def test_scrollbar_thumb_is_smooth_with_transparent_gutter(self):
        for theme in PALETTES.values():
            thumb = render.scrollbar_thumb_image((16, 36), theme["scroll_thumb"])
            alpha = thumb.getchannel("A")
            self.assertEqual(alpha.getpixel((0, 18)), 0)
            self.assertGreaterEqual(alpha.getpixel((8, 18)), 250)
            self.assertTrue(any(0 < value < 255 for value in alpha.tobytes()))
        self.assertIsNone(render.scrollbar_thumb_image((16, 36), None).getbbox())

    def test_switch_states_and_theme_previews(self):
        for key in PALETTES:
            theme = Theme(key)
            off = render.switch_image((44, 26), theme, False)
            on = render.switch_image((44, 26), theme, True)
            self.assertNotEqual(off.tobytes(), on.tobytes())
            self.assertTrue(any(0 < value < 255 for value in on.getchannel("A").tobytes()))
            self.assertEqual(render.theme_preview_image((200, 54), theme).size, (200, 54))

    def test_theme_preview_handles_intermediate_layout_sizes(self):
        for size in ((9, 54), (16, 54), (25, 54), (40, 20), (200, 54)):
            for key in PALETTES:
                self.assertEqual(render.theme_preview_image(size, Theme(key)).size, size)

    def test_scrollbar_grows_on_hover_without_changing_hit_area(self):
        normal = render.scrollbar_thumb_image((18, 36), "#9A86B6")
        active = render.scrollbar_thumb_image((18, 36), "#7150A5", active=True)
        self.assertEqual(normal.size, active.size)
        normal_bounds = normal.getchannel("A").point(lambda value: 255 if value > 128 else 0).getbbox()
        active_bounds = active.getchannel("A").point(lambda value: 255 if value > 128 else 0).getbbox()
        self.assertLess(normal_bounds[2] - normal_bounds[0], active_bounds[2] - active_bounds[0])

    def test_theme_text_contrast(self):
        def luminance(color):
            channels = [int(color[offset:offset + 2], 16) / 255 for offset in (1, 3, 5)]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
            return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))

        for key, colors in PALETTES.items():
            pairs = [(foreground, background) for foreground in ("text", "muted", "primary")
                     for background in ("surface", "background", "soft", "stage", "mint", "peach", "field", "navigation")]
            for foreground, background in pairs + [("on_primary", "primary")]:
                with self.subTest(theme=key, foreground=foreground, background=background):
                    light, dark = sorted((luminance(colors[foreground]), luminance(colors[background])), reverse=True)
                    self.assertGreaterEqual((light + .05) / (dark + .05), 4.5)


class DesktopControlsTest(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.addCleanup(gc.collect)
        self.workspace = tempfile.TemporaryDirectory(prefix="seedbank-ui-test-")
        self.addCleanup(self.workspace.cleanup)
        home = str(Path(self.workspace.name) / "home")
        self.environment = mock.patch.dict(os.environ, {"USERPROFILE": home, "HOME": home, "SEEDBANK_LANG": "zh"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.addCleanup(self.root.destroy)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)

    def layout(self, width=1180, height=820):
        self.root.attributes("-alpha", 0)
        if os.name == "nt":
            self.root.attributes("-disabled", True)
        self.root.geometry(f"{width}x{height}+0+0")
        self.root.deiconify()
        self.root.update()
        self.root.update_idletasks()

    def app(self):
        pack = Path(self.workspace.name) / "审视测试.life"
        hatch(pack, EGG, "测试")
        app = CompanionWindow(self.root, pack, "stub")
        app._cancel_timers()
        self.root.unbind("<Configure>")

        def close():
            app._closed = True
            app._cancel_timers()
            app._executor.shutdown(wait=True)
            app.session.close()

        self.addCleanup(close)
        return app

    def descendants(self, parent):
        for child in parent.winfo_children():
            if getattr(child, "active", True) is False:
                continue
            yield child
            yield from self.descendants(child)

    def test_buttons_keep_keyboard_action_and_disabled_state(self):
        calls = []
        for theme in PALETTES:
            button = Button(self.root, Theme(theme), "发送", lambda: calls.append(theme), primary=True, icon_name="send")
            button.pack()
            button.invoke()
            self.assertEqual(calls[-1], theme)
            button.set_enabled(False)
            count = len(calls)
            button.invoke()
            self.assertEqual(len(calls), count)
            button.set_enabled(True)
            button.set_selected(True)
            button._focus(True)
            button._hover(True)
            button.destroy()
            self.root.update()
        self.assertFalse(self.errors)

    def test_cards_and_missing_character_fallback(self):
        card = Card(self.root, Theme())
        card.pack()
        with mock.patch.object(card, "winfo_width", return_value=400), mock.patch.object(card, "winfo_height", return_value=200):
            card._paint()
            self.assertEqual(card._image.width(), 400)
        stage = PetStage(card.body, Theme(reduced_motion=True), asset_path=Path(self.workspace.name) / "missing")
        stage.pack()
        self.layout()
        self.assertFalse(stage._available)
        self.assertTrue(stage.find_withtag("placeholder"))
        stage.stop()
        self.root.update()
        self.assertFalse(self.errors)

    def test_scroll_content_width_is_bounded_before_first_map(self):
        scroll = Scroll(self.root, Theme())
        self.assertEqual(float(scroll.canvas.itemcget(scroll.item, "width")), 1)

    def test_large_cards_do_not_allocate_full_surface_tk_images(self):
        card = Card(self.root, Theme())
        with mock.patch.object(card, "winfo_width", return_value=1000), \
                mock.patch.object(card, "winfo_height", return_value=800):
            card._paint()
            self.assertIsNone(card._image)
            self.assertEqual(len(card._border_images), 4)
            self.assertLess(sum(picture.width() * picture.height() for picture in card._border_images), 160000)

    def test_content_panels_and_buttons_have_no_glaze_or_drop_shadow(self):
        theme = Theme.load(self.root)
        self.root.configure(bg=theme.color("background"))
        card = Card(self.root, theme)
        card.pack(fill="both", expand=True)
        button = Button(card.body, theme, "记忆", lambda: None, selected=True, variant="tab")
        button.pack()
        self.layout()
        with mock.patch("seedbank.desktop.widgets.panel_image", wraps=render.panel_image) as paint, \
                mock.patch("seedbank.desktop.widgets.panel_strips", wraps=render.panel_strips) as strips:
            card._paint_state = None
            card._paint()
            options = (strips.call_args or paint.call_args).kwargs
            self.assertEqual(options["shadow"], options["background"])
            self.assertEqual(options["border"], options["fill"])
            self.assertFalse(options.get("glaze"))
            card.set_focus(True)
            self.assertEqual((strips.call_args or paint.call_args).kwargs["border"], theme.color("primary"))
            button._paint_state = None
            button._paint()
            options = paint.call_args.kwargs
            self.assertEqual(options["shadow"], options["background"])
            self.assertFalse(options.get("glaze"))
        self.assertFalse(self.errors)

    def test_flat_fields_and_switch_rows_keep_their_native_actions(self):
        theme = Theme.load(self.root)
        self.root.configure(bg=theme.color("background"))
        style_native_widgets(self.root, theme)
        value = tk.StringVar(self.root)
        search = Input(self.root, theme, value, icon_name="search")
        search.pack(fill="x")
        choice = Select(self.root, theme, values=("first", "second"), state="readonly")
        choice.pack(fill="x")
        enabled = tk.BooleanVar(self.root)
        toggle = Toggle(self.root, theme, "包含已放下的记忆", enabled)
        toggle.pack(fill="x")
        self.layout()
        self.assertFalse(search.outlined)
        self.assertFalse(choice.outlined)
        self.assertEqual(search.control.cget("bg"), theme.color("field"))
        self.assertEqual(choice.body.cget("bg"), theme.color("field"))
        self.assertEqual(toggle.body.cget("bg"), self.root.cget("bg"))
        elements = ttk.Style(self.root).layout(toggle.control.cget("style"))[0][1]["children"]
        self.assertEqual(elements[0][1]["side"], "right")
        toggle.control.invoke()
        self.assertTrue(enabled.get())
        self.assertFalse(self.errors)

    def test_memory_records_share_one_flat_group(self):
        app = self.app()
        app.snapshot["memories"] = [
            {"id": "first", "day": 1, "text": "第一条记忆"},
            {"id": "second", "day": 2, "text": "第二条记忆"},
            {"id": "forgotten", "day": 3, "text": "已放下的记忆", "forgotten": True},
        ]
        app.show_page("memory")
        self.layout(860, 640)
        self.assertEqual(len(app.page.memory_rows), 2)
        groups = [widget for widget in app.page.body.frame.winfo_children() if isinstance(widget, Card)]
        self.assertEqual(groups, [app.page.memory_group])
        self.assertTrue(all(not isinstance(row, Card) for row in app.page.memory_rows))
        app.page.forgotten.set(True)
        app.page.filter()
        self.assertEqual(len(app.page.memory_rows), 3)
        app.page.query.set("没有匹配项")
        app.page.filter()
        self.assertEqual(app.page.memory_rows, [])
        self.assertIsNone(app.page.memory_group)
        self.assertFalse(self.errors)

    def test_button_text_has_no_native_focus_element_or_border_overlap(self):
        calls = []
        for scale in (1, 1.15):
            button = Button(self.root, Theme(scale=scale), "外观", lambda: calls.append("clicked"), selected=True)
            layout = ttk.Style(self.root).layout(button.native.cget("style"))
            self.assertEqual(button.native.winfo_class(), "TButton")
            self.assertEqual(layout, [("Button.label", {"sticky": "nswe"})])
            placement = button.native.place_info()
            self.assertGreaterEqual(int(placement["x"]), 18)
            self.assertGreaterEqual(int(placement["y"]), 9)
            self.assertLessEqual(int(placement["height"]), -20)
            count = len(calls)
            self.assertEqual(button._activate_key(), "break")
            self.assertEqual(len(calls), count + 1)
            button._focus(True)
            self.assertTrue(button.focused)
            button.destroy()
        self.root.update()
        self.assertFalse(self.errors)

    def test_scrollbar_uses_pill_elements_and_hides_full_range(self):
        calls = []
        bar = PillScrollbar(self.root, Theme(), command=lambda *args: calls.append(args))
        layout = ttk.Style(self.root).layout(bar.cget("style"))
        self.assertTrue(layout[0][0].endswith(".trough"))
        children = layout[0][1]["children"]
        self.assertEqual(len(children), 1)
        self.assertTrue(children[0][0].endswith(".thumb"))
        bar.set(0, 1)
        self.assertTrue(bar.instate(["disabled"]))
        self.assertEqual(bar._wheel(SimpleNamespace(delta=-120)), "break")
        self.assertFalse(calls)
        bar.set(.2, .6)
        self.assertFalse(bar.instate(["disabled"]))
        self.assertEqual(bar.get(), (.2, .6))
        self.assertEqual(bar._wheel(SimpleNamespace(delta=-120)), "break")
        self.assertEqual(calls, [("scroll", 3, "units")])

    def test_pages_themes_and_text_scaling_keep_drafts(self):
        pack = Path(self.workspace.name) / "测试.life"
        hatch(pack, EGG, "测试")
        app = CompanionWindow(self.root, pack, "stub")
        try:
            app.page.input.insert("1.0", "这是尚未发送的草稿")
            for theme in PALETTES:
                for large_text in (False, True):
                    app.change_appearance(desktop_theme=theme, desktop_large_text=large_text, desktop_reduced_motion=True)
                    for destination in ("diary", "memory", "life", "settings", "room"):
                        app.show_page(destination)
                        self.root.update()
                    self.assertEqual(app.page.input.get("1.0", "end-1c"), "这是尚未发送的草稿")
                    self.assertFalse(app.pet._available)
            self.assertFalse(self.errors)
        finally:
            app._closed = True
            app._cancel_timers()
            app._executor.shutdown(wait=True)
            app.session.close()

    def test_button_pressed_selected_and_focus_are_distinct(self):
        self.layout()
        button = Button(self.root, Theme(reduced_motion=True), "陪伴", lambda: None, selected=True, variant="tab")
        button.pack()
        self.root.update_idletasks()
        selected = button._image
        selected_pixels = ImageTk.getimage(selected).tobytes()
        button._focus(True)
        self.assertNotEqual(selected_pixels, ImageTk.getimage(button._image).tobytes())
        focused_colors = button._colors
        button._press(True)
        self.assertNotEqual(focused_colors, button._colors)
        button.set_enabled(False)
        self.assertFalse(button.pressed)

    def test_button_border_click_only_activates_on_release_inside(self):
        calls = []
        button = Button(self.root, Theme(), "按钮", lambda: calls.append(True))
        button.pack()
        self.layout()
        button._press(True)
        self.assertFalse(calls)
        button._release_art(SimpleNamespace(x=-1, y=10))
        self.assertFalse(calls)
        button._press(True)
        button._release_art(SimpleNamespace(x=10, y=10))
        self.assertEqual(calls, [True])

    def test_native_button_mouse_binding_invokes_once(self):
        calls = []
        button = Button(self.root, Theme(reduced_motion=True), "发送", lambda: calls.append(True), icon_name="send")
        button.pack()
        self.layout()
        button.native.event_generate("<Enter>")
        button.native.event_generate("<ButtonPress-1>", x=10, y=10)
        self.assertFalse(calls)
        self.assertTrue(button.pressed)
        button.native.event_generate("<ButtonRelease-1>", x=10, y=10)
        self.assertEqual(calls, [True])
        self.assertFalse(button.pressed)

    def test_round_inputs_selects_and_switches_keep_native_behavior(self):
        theme = Theme.load(self.root)
        style_native_widgets(self.root, theme)
        value = tk.StringVar(self.root, "草稿")
        control = Input(self.root, theme, value)
        control.pack(fill="x")
        selected = tk.BooleanVar(self.root, False)
        calls = []
        toggle = Toggle(self.root, theme, "更大的文字", selected, lambda: calls.append(selected.get()))
        toggle.pack(fill="x")
        choice = Select(self.root, theme, values=("first", "second"), state="readonly")
        choice.pack(fill="x")
        self.layout()
        control.control.insert("end", "保留")
        self.assertEqual(value.get(), "草稿保留")
        toggle.control.invoke()
        self.assertEqual(calls, [True])
        toggle.configure(state="disabled")
        toggle.control.invoke()
        self.assertEqual(calls, [True])
        choice.current(1)
        self.assertEqual(choice.get(), "second")
        self.assertFalse(self.errors)

    def test_diary_formats_headings_without_changing_literal_blocks(self):
        document = reader(self.root, Theme())
        source = "# 第一页\n\n## 对话\n- 小事\n```\n# 原样保留\n```\n"
        set_reader(document, source, markdown=True)
        self.assertEqual(document.get("1.0", "end-1c"), "第一页\n\n对话\n• 小事\n```\n# 原样保留\n```\n")
        self.assertTrue(document.tag_ranges("heading1"))
        self.assertTrue(document.tag_ranges("heading2"))
        self.assertEqual(document.cget("state"), "disabled")
        set_reader(document, source)
        self.assertEqual(document.get("1.0", "end-1c"), source)

    def test_select_wheel_scrolls_page_without_selecting_or_notifying(self):
        theme = Theme.load(self.root)
        style_native_widgets(self.root, theme)
        scroll = Scroll(self.root, theme)
        scroll.pack(fill="both", expand=True)
        value = tk.StringVar(self.root, "中文")
        choice = Select(scroll.frame, theme, textvariable=value, values=("中文", "日本語", "English"), state="readonly")
        choice.pack(fill="x")
        tk.Frame(scroll.frame, height=1600).pack(fill="x")
        changes = []
        choice.bind("<<ComboboxSelected>>", lambda event: changes.append(choice.get()))
        self.layout(860, 640)
        choice.control.event_generate("<MouseWheel>", delta=-120)
        self.root.update_idletasks()
        self.assertGreater(scroll.canvas.yview()[0], 0)
        for event in (SimpleNamespace(delta=120), SimpleNamespace(num=4), SimpleNamespace(num=5), SimpleNamespace(delta=0)):
            self.assertEqual(choice._wheel(event), "break")
        self.assertEqual(value.get(), "中文")
        self.assertFalse(changes)
        choice.current(1)
        choice.control.event_generate("<<ComboboxSelected>>")
        self.assertEqual(changes, ["日本語"])
        self.assertFalse(self.errors)

    def test_select_without_scroll_parent_ignores_wheel_and_keeps_arrow_cache(self):
        theme = Theme.load(self.root)
        style_native_widgets(self.root, theme)
        window = tk.Toplevel(self.root)
        window.withdraw()
        self.addCleanup(window.destroy)
        style_native_widgets(window, theme)
        choice = Select(window, theme, values=("first", "second"), state="readonly")
        choice.current(0)
        for direction in (-120, 0, 120):
            self.assertEqual(choice._wheel(SimpleNamespace(delta=direction)), "break")
            self.assertEqual(choice.current(), 0)
        self.assertEqual(len(self.root._desktop_select_arrows), 1)

    def test_date_list_virtualizes_rows_and_preserves_selection_while_scrolling(self):
        dates = DateList(self.root, Theme.load(self.root), [("2026-11-01", f"第 {index + 1} 天") for index in range(2000)])
        dates.pack(fill="both", expand=True)
        selected = []
        dates.bind("<<DateSelected>>", lambda event: selected.append(dates.selected))
        self.layout(280, 400)
        dates.select(0, notify=False)
        dates._key(SimpleNamespace(keysym="End"))
        self.root.update_idletasks()
        self.assertEqual(selected, [1999])
        self.assertLessEqual(len(dates.pool), dates.canvas.winfo_height() // dates.row_height + 2)
        dates._wheel(SimpleNamespace(delta=120))
        dates.yview("moveto", .3)
        self.root.update_idletasks()
        self.assertEqual(dates.selected, 1999)
        self.assertEqual(selected, [1999])
        dates._key(SimpleNamespace(keysym="Home"))
        dates._key(SimpleNamespace(keysym="Down"))
        self.root.update_idletasks()
        self.assertEqual(dates.selected, 1)
        self.assertEqual(selected, [1999, 0, 1])
        self.assertFalse(self.errors)

    def test_date_list_empty_and_diary_selection_restore(self):
        empty = DateList(self.root, Theme(), [])
        self.assertEqual(empty._key(SimpleNamespace(keysym="End")), "break")
        self.assertIsNone(empty.selected)
        empty.destroy()
        app = self.app()
        app.snapshot["days"] = [{"date": "2026-11-01", "day": 1}, {"date": "2026-11-02", "day": 2}]
        with mock.patch.object(app.session, "diary", side_effect=lambda day: f"# Day {day}\n"):
            app.show_page("diary")
            self.layout()
            app.page.dates.select(1)
            self.assertEqual(app.page.state["day"], 1)
            app.show_page("memory")
            app.show_page("diary")
            self.root.update_idletasks()
            self.assertEqual(app.page.dates.selected, 1)
            self.assertIn("Day 1", app.page.document.get("1.0", "end-1c"))
        self.assertFalse(self.errors)

    def test_inline_switch_keeps_natural_caption_width(self):
        host = tk.Frame(self.root, bg="#FFFFFF")
        host.pack(fill="both", expand=True)
        toggle = Toggle(host, Theme.load(self.root), "包含已放下的记忆", tk.BooleanVar(self.root))
        toggle.pack(anchor="w")
        self.layout()
        self.assertGreaterEqual(toggle.control.winfo_width(), 170)
        self.assertLessEqual(toggle.control.winfo_height(), 30)

    def test_short_messages_shrink_and_long_messages_wrap(self):
        host = tk.Frame(self.root, bg="#FFFFFF")
        host.pack(fill="both", expand=True)
        short = MessageBubble(host, Theme(), "主人", "你好", incoming=False)
        short.pack(fill="x")
        long = MessageBubble(host, Theme(), "很长的角色名字" * 8, "这是很长的一段对话。" * 40)
        long.pack(fill="x")
        self.layout(860, 640)
        self.assertLess(short.bubble.winfo_width(), short.winfo_width() * .5)
        self.assertLessEqual(long.bubble.winfo_width(), long.winfo_width() * .85)
        self.assertGreater(long.message.winfo_height(), short.message.winfo_height())

    def test_compatibility_stage_ignores_existing_artwork(self):
        assets = Path(self.workspace.name) / "archived-artwork"
        (assets / "idle").mkdir(parents=True)
        original = b"archived file must not be opened or modified"
        frame = assets / "idle" / "01.png"
        frame.write_bytes(original)
        with mock.patch("PIL.Image.open", side_effect=AssertionError("Old artwork was opened")), \
                mock.patch("tkinter.PhotoImage", side_effect=AssertionError("Old artwork was displayed")):
            stage = PetStage(self.root, Theme(), asset_path=assets)
            stage.pack(fill="both", expand=True)
            self.layout(400, 400)
            self.assertFalse(stage._available)
            self.assertFalse(stage.play("wave"))
            self.assertEqual({stage.type(item) for item in stage.find_all()}, {"text"})
            self.assertIn("SEEDbank", stage.itemcget(stage.find_withtag("placeholder")[0], "text"))
            stage.destroy()
        self.assertEqual(frame.read_bytes(), original)
        self.assertFalse(self.errors)

    def test_compatibility_notice_has_no_animation_timer(self):
        stage = PetStage(self.root, Theme(reduced_motion=True))
        with mock.patch.object(stage, "create_text", wraps=stage.create_text) as notice, \
                mock.patch.object(stage, "after", side_effect=AssertionError("Animation was scheduled")), \
                mock.patch.object(stage, "after_idle", side_effect=AssertionError("Animation was scheduled")):
            stage._draw()
            notice.assert_not_called()
            stage.pack(fill="both", expand=True)
            self.layout(400, 400)
            self.assertTrue(notice.called)
            stage.stop()
            notice.reset_mock()
            stage.play("idle")
            stage._draw()
            notice.assert_not_called()
            self.assertIsNone(stage._after)
            stage.resume()
            stage.resume()
            self.root.update_idletasks()
            self.assertTrue(stage._running)
            self.assertIsNone(stage._after)
            self.assertEqual(len(stage.find_all()), 1)
        self.assertFalse(self.errors)

    def test_old_sidebar_uses_the_same_notice_without_images_or_timers(self):
        from seedbank.ui.pet import _PetStage

        with mock.patch("tkinter.PhotoImage", side_effect=AssertionError("Old artwork was displayed")):
            stage = _PetStage(self.root)
            stage.pack(fill="both", expand=True)
            self.layout(400, 400)
            for action in (stage.greet, stage.happy, stage.celebrate, stage.idle,
                           stage.toggle_dance, stage.wake, stage.touch):
                action()
            stage.set_compact(True)
            self.assertFalse(stage.play("wave", loop=False))
            self.assertIsNone(stage._after)
            self.assertEqual({stage.type(item) for item in stage.find_all()}, {"text"})
            stage.destroy()
        self.assertFalse(self.errors)

    def test_unchanged_button_states_skip_images_but_focus_still_paints(self):
        button = Button(self.root, Theme(reduced_motion=True), "陪伴", lambda: None,
                        variant="navigation", icon_name="home")
        button.pack()
        self.layout()
        button._focus(False)
        with mock.patch("seedbank.desktop.widgets.panel_image", wraps=render.panel_image) as paint:
            symbol = button._symbol
            button.set_enabled(True)
            button.set_selected(False)
            button._paint()
            button._paint()
            paint.assert_not_called()
            button._focus(True)
            self.assertEqual(paint.call_count, 1)
            self.assertIs(button._symbol, symbol)
            button.set_selected(True)
            self.assertEqual(paint.call_count, 2)
            self.assertEqual(str(button.native.cget("compound")), "top")
            button.set_enabled(False)
            self.assertTrue(button.native.instate(["disabled"]))
        self.assertFalse(self.errors)

    def test_navigation_reuses_all_five_pages_and_pauses_hidden_pet(self):
        app = self.app()
        self.layout()
        room = app.page
        room.input.insert("1.0", "还没发送的草稿")
        pages = {"room": room}
        for destination in ("diary", "memory", "life", "settings"):
            app.nav_buttons[destination].invoke()
            self.root.update_idletasks()
            pages[destination] = app.page
            self.assertFalse(room.pet._running)
            self.assertIsNone(room.pet._after)
            self.assertIsNone(room.restore_id)
        for repetition in range(3):
            for destination, page in pages.items():
                app.nav_buttons[destination].invoke()
                self.root.update_idletasks()
                self.assertIs(app.page, page)
                self.assertEqual(sum(cached[1].active for cached in app._page_cache.values()), 1)
                self.assertIs(app.host.winfo_children()[-1], app.page)
                app.nav_buttons[destination].invoke()
                self.assertIs(app.page, page)
                self.assertLessEqual(len(app._page_cache), 5)
        app.navigate("room")
        self.root.update_idletasks()
        self.assertEqual(room.input.get("1.0", "end-1c"), "还没发送的草稿")
        self.assertTrue(room.pet.find_withtag("placeholder"))
        self.assertTrue(room.pet._running)
        self.assertIsNone(room.pet._after)
        self.assertFalse(self.errors)

    def test_warm_navigation_does_not_remap_entire_widget_subtrees(self):
        app = self.app()
        self.layout()
        for destination in ("diary", "memory", "life", "settings", "room"):
            app.navigate(destination)
            self.root.update()
        mappings = []
        self.root.bind("<Map>", lambda event: mappings.append(str(event.widget)), add="+")
        self.root.bind("<Unmap>", lambda event: mappings.append(str(event.widget)), add="+")
        for destination in ("diary", "memory", "life", "settings", "room"):
            app.navigate(destination)
            self.root.update()
        self.assertEqual(mappings, [])
        self.assertFalse(self.errors)

    def test_warm_room_does_not_force_another_nested_idle_flush(self):
        app = self.app()
        self.layout()
        room = app.page
        app.navigate("diary")
        self.root.update()
        with mock.patch.object(room.messages, "update_idletasks") as flush:
            app.navigate("room")
            self.root.update()
            flush.assert_not_called()

    def test_revision_only_snapshot_keeps_warm_page_cache(self):
        app = self.app()
        self.layout()
        for destination in ("diary", "memory", "life", "settings", "room"):
            app.navigate(destination)
            self.root.update()
        pages = {key: cached[1] for key, cached in app._page_cache.items()}
        snapshot = deepcopy(app.snapshot)
        snapshot["revision"] += 1
        app.apply_snapshot(snapshot)
        for destination, page in pages.items():
            app.navigate(destination)
            self.root.update()
            self.assertIs(app.page, page)
        self.assertEqual(app.snapshot["revision"], snapshot["revision"])

    def test_keyboard_traversal_cannot_enter_inactive_pages(self):
        app = self.app()
        self.layout()
        room = app.page
        app.navigate("settings")
        self.root.update()
        hidden = str(room) + "."
        focused = app.nav_buttons["settings"].native
        visited = []
        for step in range(30):
            focused = focused.tk_focusNext()
            visited.append(str(focused))
            self.assertFalse(str(focused).startswith(hidden))
        self.assertTrue(any(path.startswith(str(app.page) + ".") for path in visited))
        for step in range(30):
            focused = focused.tk_focusPrev()
            self.assertFalse(str(focused).startswith(hidden))
        app.navigate("room")
        self.root.update()
        self.assertNotEqual(str(room.input.cget("takefocus")), "0")
        focused = app.nav_buttons["room"].native
        visited = []
        for step in range(30):
            focused = focused.tk_focusNext()
            visited.append(focused)
        self.assertIn(room.input, visited)

    def test_same_day_offline_clock_does_not_flush_navigation_cache(self):
        app = self.app()
        with mock.patch("seedbank.desktop.session.maybe_initiate", return_value=None):
            app.apply_snapshot(app.session.pulse()["snapshot"])
            for destination in ("diary", "memory", "life", "settings", "room"):
                app.navigate(destination)
                self.root.update_idletasks()
            pages = {key: cached[1] for key, cached in app._page_cache.items()}
            app.apply_snapshot(app.session.pulse()["snapshot"])
        for destination, page in pages.items():
            app.navigate(destination)
            self.assertIs(app.page, page)

    def test_snapshot_invalidates_only_pages_that_depend_on_changed_data(self):
        app = self.app()
        self.layout()
        pages = {"room": app.page}
        for destination in ("diary", "memory", "life", "settings"):
            app.navigate(destination)
            pages[destination] = app.page
        snapshot = deepcopy(app.snapshot)
        snapshot["states"]["mood"]["mood"] = "新的心情"
        app.apply_snapshot(snapshot)
        self.assertIs(app.page, pages["settings"])
        self.assertTrue(pages["room"].stale)
        self.assertTrue(pages["life"].stale)
        self.assertFalse(pages["memory"].stale)
        app.navigate("memory")
        self.assertIs(app.page, pages["memory"])
        app.navigate("room")
        self.assertIsNot(app.page, pages["room"])
        self.assertFalse(self.errors)

    def test_cached_pages_invalidate_on_snapshot_and_keep_unsent_drafts(self):
        app = self.app()
        self.layout()
        room = app.page
        room.input.insert("1.0", "仍然保留")
        app.navigate("memory")
        memory = app.page
        app.navigate("life")
        snapshot = deepcopy(app.snapshot)
        snapshot["transcript"].append({"who": app.name, "text": "一条新消息"})
        snapshot["memories"].append({"id": "new", "day": 1, "text": "一条新记忆"})
        app.apply_snapshot(snapshot)
        self.assertTrue(room.stale)
        self.assertTrue(memory.stale)
        app.navigate("room")
        self.assertFalse(room.winfo_exists())
        self.assertEqual(app.page.input.get("1.0", "end-1c"), "仍然保留")
        self.assertTrue(any(isinstance(widget, tk.Label) and widget.cget("text") == "一条新消息"
                            for widget in self.descendants(app.page.messages)))
        app.navigate("memory")
        self.assertFalse(memory.winfo_exists())
        self.assertTrue(any(isinstance(widget, tk.Label) and widget.cget("text") == "一条新记忆"
                            for widget in self.descendants(app.page)))
        self.assertFalse(self.errors)

    def test_cached_navigation_moves_focus_out_of_hidden_page(self):
        app = self.app()
        self.layout()
        room = app.page
        with mock.patch.object(self.root, "focus_get", return_value=room.input), \
                mock.patch.object(app.nav_buttons["diary"].native, "focus_set") as focus:
            app.navigate("diary")
            focus.assert_called_once_with()
        self.assertFalse(room.active)
        self.assertIsNone(room.restore_timer)
        self.assertIsNone(room.restore_id)
        self.assertFalse(self.errors)

    def test_secondary_tabs_skip_same_section_but_refresh_changed_sections(self):
        app = self.app()
        app.navigate("settings")
        settings = app.page
        settings.switch("appearance")
        self.assertIs(app.page, settings)
        settings.switch("conversation")
        self.assertFalse(settings.winfo_exists())
        self.assertEqual(app.page.section_key, "conversation")
        app.navigate("life")
        life = app.page
        life.switch("growth")
        self.assertIs(app.page, life)
        life.switch("works")
        self.assertFalse(life.winfo_exists())
        self.assertEqual(app.page.state["section"], "works")
        self.assertFalse(self.errors)

    def test_cached_controls_follow_busy_state_and_discard_dead_actions(self):
        app = self.app()
        self.layout()
        app.snapshot["memories"] = [{"id": str(index), "day": 1, "text": "回忆"} for index in range(25)]
        app.navigate("memory")
        memory = app.page
        for repetition in range(4):
            memory.move(1)
            memory.move(-1)
        self.assertEqual(len(app.controls), 20)
        app.navigate("life")
        app._set_busy(True)
        app.navigate("memory")
        self.assertIs(app.page, memory)
        self.assertTrue(all(not control.enabled for control in app.controls))
        app._set_busy(False)
        self.assertTrue(all(control.enabled for control in app.controls))
        self.assertFalse(memory.previous.enabled)
        self.assertTrue(memory.next.enabled)
        self.assertFalse(self.errors)

    def test_layout_and_theme_changes_invalidate_cached_pages(self):
        app = self.app()
        self.layout()
        app.page_state.setdefault("settings", {})["section"] = "conversation"
        app.navigate("settings")
        settings = app.page
        settings.variable("model").set("未保存的模型")
        app.navigate("room")
        room = app.page
        app._compact = not app._compact
        app.navigate("settings")
        self.assertFalse(settings.winfo_exists())
        self.assertEqual(app.page.variable("model").get(), "未保存的模型")
        settings = app.page
        app.theme = Theme("night", reduced_motion=True)
        app._build_shell()
        self.assertFalse(settings.winfo_exists())
        self.assertFalse(room.winfo_exists())
        self.assertEqual(len(app._page_cache), 1)
        self.assertEqual(app.page.theme.key, "night")
        self.assertEqual(app.page.variable("model").get(), "未保存的模型")
        self.assertFalse(self.errors)

    def test_hidden_settings_discovery_invalidates_cache_without_losing_draft(self):
        app = self.app()
        app.page_state.setdefault("settings", {})["section"] = "conversation"
        app.navigate("settings")
        settings = app.page
        settings.variable("model").set("正在编辑")
        with mock.patch.object(app, "submit", return_value=True) as submit:
            settings.discover()
            callback = submit.call_args.args[1]
        app.navigate("room")
        results = [{"label": "本机", "models": ["cached-model"], "base_url": "http://localhost:1234"}]
        callback(results)
        self.assertFalse(settings.winfo_exists())
        app.navigate("settings")
        self.assertEqual(app.page.variable("model").get(), "正在编辑")
        self.assertEqual(app.page.state["models"], results)
        self.assertTrue(any(isinstance(widget, Button) and "cached-model" in widget.caption
                            for widget in self.descendants(app.page)))
        self.assertFalse(self.errors)

    def test_long_chat_restores_bottom_and_manual_scroll(self):
        app = self.app()
        app.snapshot["transcript"] = [{"who": app.name, "text": f"消息 {index}：" + "长内容" * 30} for index in range(40)]
        app.show_page("room")
        self.layout(860, 640)
        app.page._restore_scroll()
        self.assertAlmostEqual(app.page.messages.canvas.yview()[1], 1, delta=.02)
        app.page.messages.canvas.yview_moveto(.35)
        saved = app.page.messages.canvas.yview()[0]
        app.show_page("memory")
        app.show_page("room")
        self.root.update_idletasks()
        self.assertAlmostEqual(app.page.messages.canvas.yview()[0], saved, delta=.03)
        self.assertFalse(app.page.messages.bar.instate(["disabled"]))

    def test_memory_filters_pagination_and_settings_drafts(self):
        app = self.app()
        app.snapshot["memories"] = [{"id": str(index), "day": 1, "text": f"回忆 {index}", "forgotten": index == 0} for index in range(47)]
        app.show_page("memory")
        self.layout()
        self.assertTrue(app.page.next.enabled)
        self.assertFalse(app.page.previous.enabled)
        app.page.move(1)
        self.assertTrue(app.page.previous.enabled)
        app.page.query.set("不存在")
        app.page.filter()
        self.assertFalse(app.page.next.enabled)
        self.assertFalse(app.page.previous.enabled)
        app.page_state.setdefault("settings", {})["section"] = "conversation"
        app.show_page("settings")
        app.page.variable("model").set("unsaved-test-model")
        app.show_page("life")
        app.show_page("settings")
        self.assertEqual(app.page.variable("model").get(), "unsaved-test-model")
        self.assertNotEqual(app.settings_saved.get("model"), "unsaved-test-model")
        self.assertFalse(self.errors)

    def test_layout_matrix_all_pages_sections_themes_sizes_and_languages(self):
        app = self.app()
        sections = (("room", None), ("diary", None), ("memory", None),
                    ("life", "growth"), ("life", "heart"), ("life", "works"),
                    ("settings", "appearance"), ("settings", "conversation"), ("settings", "memory"), ("settings", "qq"))
        for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
            set_locale(language)
            for key in PALETTES:
                for scale in (1, 1.15):
                    for width, height in ((860, 640), (1180, 820)):
                        app.theme = Theme(key, scale, True, Theme.load(self.root).family)
                        app._compact = width < 1060 or height < 730
                        app._build_shell()
                        self.layout(width, height)
                        for destination, section in sections:
                            with self.subTest(language=language, theme=key, scale=scale, size=(width, height), page=destination, section=section):
                                if section:
                                    app.page_state.setdefault(destination, {})["section"] = section
                                app.show_page(destination)
                                self.root.update_idletasks()
                                self.assertGreaterEqual(app.navigation.winfo_y(), app.host.winfo_y() + app.host.winfo_height())
                                self.assertLessEqual(app.navigation.winfo_width(), app.shell.winfo_width())
                                for button in app.nav_buttons.values():
                                    self.assertEqual(str(button.native.cget("compound")), "top")
                                for widget in self.descendants(app.shell):
                                    if isinstance(widget, Button) and widget.winfo_ismapped():
                                        self.assertGreaterEqual(widget.native.winfo_width(), widget.native.winfo_reqwidth(),
                                                                f"button truncated: {widget.caption}")
                                    if isinstance(widget, (Input, Select)):
                                        self.assertGreater(widget.control.winfo_width(), 30)
                                    if isinstance(widget, tk.Label) and widget.winfo_ismapped():
                                        self.assertLessEqual(widget.winfo_reqwidth(), widget.winfo_width() + 4,
                                                             f"label truncated: {widget.cget('text')}")
                                        self.assertLessEqual(widget.winfo_reqheight(), widget.winfo_height() + 2,
                                                             f"label height truncated: {widget.cget('text')}")
                                    if isinstance(widget, Card) and widget.winfo_ismapped():
                                        self.assertGreaterEqual(widget.body.winfo_x(), round(widget.radius * .3) + 4)
                                        self.assertLessEqual(widget.body.winfo_x() + widget.body.winfo_width(), widget.winfo_width())
                                if destination == "room":
                                    self.assertGreaterEqual(app.page.pet.winfo_height(), 100)
                                    self.assertGreaterEqual(app.page.messages.winfo_height(), 100)
                                    self.assertGreaterEqual(app.page.input.winfo_height(), 35)
                                    self.assertGreaterEqual(app.page.companion.winfo_width(), app.host.winfo_width() * .35)
                                if destination == "diary":
                                    self.assertIsInstance(app.page.dates, DateList)
                                    self.assertEqual(int(app.page.dates.canvas.cget("highlightthickness")), 0)
                                self.assertFalse(self.errors)
        set_locale("zh_CN")

    def test_chat_offline_send_busy_and_draft_survive_navigation(self):
        app = self.app()
        self.layout()
        app.page.input.insert("1.0", "你好，今天过得怎么样？")
        app.page.send()
        self.assertTrue(app._busy)
        app.show_page("memory")
        deadline = time.monotonic() + 8
        while app._busy and time.monotonic() < deadline:
            app._poll()
            self.root.update_idletasks()
            time.sleep(.02)
        self.assertFalse(app._busy)
        app.show_page("room")
        self.root.update_idletasks()
        self.assertTrue(app.snapshot["transcript"])
        self.assertEqual(app.page.input.get("1.0", "end-1c"), "")
        self.assertFalse(self.errors)

    def test_wizard_steps_use_shared_controls_without_creating_real_pack(self):
        wizard = SetupWizard(self.root, lambda path: None)
        wizard.withdraw()
        try:
            wizard.parent_dir.set(self.workspace.name)
            for step in (0, 1, 2, 1, 0):
                wizard.step = step
                wizard.build()
                self.root.update_idletasks()
            self.assertFalse(wizard.target().exists())
            self.assertFalse(self.errors)
        finally:
            wizard.cancel()

    def test_wizard_layout_languages_and_large_text(self):
        wizard = SetupWizard(self.root, lambda path: None)
        wizard.withdraw()
        wizard.attributes("-alpha", 0)
        if os.name == "nt":
            wizard.attributes("-disabled", True)
        wizard.geometry("760x640+0+0")
        try:
            wizard.parent_dir.set(self.workspace.name)
            for language in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
                set_locale(language)
                for scale in (1, 1.15):
                    wizard.theme = Theme("cream", scale, True, Theme.load(self.root).family)
                    for step in (0, 1, 2):
                        with self.subTest(language=language, scale=scale, step=step):
                            wizard.step = step
                            wizard.build()
                            wizard.deiconify()
                            self.root.update()
                            for button in wizard.controls:
                                self.assertGreaterEqual(button.native.winfo_width(), button.native.winfo_reqwidth(), button.caption)
                            self.assertGreater(wizard.body.winfo_height(), 150)
                            self.assertFalse(self.errors)
            self.assertFalse(wizard.target().exists())
        finally:
            wizard.cancel()
            set_locale("zh_CN")


if __name__ == "__main__":
    unittest.main()
