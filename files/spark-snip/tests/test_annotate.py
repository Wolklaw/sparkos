"""Annotation tests: the model and renderer on generated images (no display), then the editor
window and its hand-off to the result window (needs a display, skipped without one)."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-snip-{var.lower()}-'))

from PIL import Image  # noqa: E402

from sparksnip.annotate import (Document, Item, default_width, hex_to_rgb, render,  # noqa: E402
                                step_radius)

RED, BLUE = "#ff0000", "#0000ff"
WHITE = (255, 255, 255)


def canvas(w=200, h=120, colour=WHITE):
    return Image.new("RGB", (w, h), colour)


def is_colour(px, hexcolour, tol=40):
    return all(abs(a - b) <= tol for a, b in zip(px[:3], hex_to_rgb(hexcolour)))


class RenderTests(unittest.TestCase):
    def test_no_items_is_the_same_picture(self):
        base = canvas()
        self.assertEqual(list(render(base, ()).getdata()), list(base.getdata()))

    def test_rectangle_outline_only(self):
        out = render(canvas(), [Item("rect", ((40, 30), (160, 90)), RED, 4)])
        self.assertTrue(is_colour(out.getpixel((100, 30)), RED))      # top edge
        self.assertTrue(is_colour(out.getpixel((40, 60)), RED))       # left edge
        self.assertEqual(out.getpixel((100, 60)), WHITE)              # inside stays untouched
        self.assertEqual(out.getpixel((10, 10)), WHITE)

    def test_ellipse_hits_its_edge_not_its_corner(self):
        out = render(canvas(), [Item("ellipse", ((40, 20), (160, 100)), BLUE, 4)])
        self.assertTrue(is_colour(out.getpixel((100, 20)), BLUE))
        self.assertTrue(is_colour(out.getpixel((40, 60)), BLUE))
        self.assertEqual(out.getpixel((42, 22)), WHITE)               # bounding-box corner
        self.assertEqual(out.getpixel((100, 60)), WHITE)

    def test_arrow_has_a_shaft_and_a_head_at_the_end(self):
        out = render(canvas(300, 100), [Item("arrow", ((20, 50), (260, 50)), RED, 4)])
        self.assertTrue(is_colour(out.getpixel((100, 50)), RED))      # shaft
        self.assertTrue(is_colour(out.getpixel((255, 50)), RED))      # tip
        self.assertTrue(is_colour(out.getpixel((250, 54)), RED))      # head is wider than the shaft
        self.assertEqual(out.getpixel((100, 58)), WHITE)
        self.assertEqual(out.getpixel((10, 50)), WHITE)

    def test_pen_follows_its_path(self):
        out = render(canvas(), [Item("pen", ((20, 20), (20, 100), (180, 100)), RED, 5)])
        self.assertTrue(is_colour(out.getpixel((20, 60)), RED))
        self.assertTrue(is_colour(out.getpixel((100, 100)), RED))
        self.assertEqual(out.getpixel((100, 50)), WHITE)

    def test_highlighter_lets_the_picture_show_through(self):
        base = canvas(colour=(0, 0, 0))
        out = render(base, [Item("highlight", ((20, 60), (180, 60)), "#f4c95d", 14)])
        px = out.getpixel((100, 60))
        self.assertNotEqual(px, (0, 0, 0))
        self.assertLess(px[0], 0xf4)                                   # translucent, not solid
        loop = render(base, [Item("highlight", ((20, 60), (180, 60), (20, 60)), "#f4c95d", 14)])
        self.assertEqual(loop.getpixel((100, 60)), px)                 # one stroke never stacks

    def test_text_draws_pixels_where_it_is_placed(self):
        out = render(canvas(300, 80), [Item("text", ((20, 20),), RED, 5, "Hello")])
        reds = [(x, y) for x in range(300) for y in range(80)
                if is_colour(out.getpixel((x, y)), RED, 30)]
        self.assertGreater(len(reds), 40)
        self.assertTrue(all(x >= 18 and y >= 16 for x, y in reds))
        self.assertEqual(out.getpixel((290, 70)), WHITE)

    def test_empty_text_draws_nothing(self):
        base = canvas()
        out = render(base, [Item("text", ((20, 20),), RED, 5, "  ")])
        self.assertEqual(list(out.getdata()), list(base.getdata()))

    def test_step_marker_is_a_disc_with_a_number(self):
        item = Item("step", ((60, 60),), RED, 5, "7")
        out = render(canvas(), [item])
        r = step_radius(item)
        self.assertTrue(is_colour(out.getpixel((60 + int(r) - 3, 60)), RED))
        self.assertEqual(out.getpixel((60 + int(r) + 6, 60)), WHITE)
        inner = [out.getpixel((x, y)) for x in range(50, 71) for y in range(50, 71)]
        self.assertTrue(any(p[0] > 240 and p[1] > 240 for p in inner))   # white number on red

    def test_pixelate_blocks_a_region_and_leaves_the_rest(self):
        base = Image.new("RGB", (100, 100))
        for x in range(100):
            for y in range(100):
                base.putpixel((x, y), (x * 2, y * 2, (x + y) % 256))
        out = render(base, [Item("pixelate", ((20, 20), (80, 80)), RED, 5)])      # blocks of 15
        self.assertEqual(out.getpixel((10, 10)), base.getpixel((10, 10)))
        self.assertEqual(out.getpixel((90, 90)), base.getpixel((90, 90)))
        self.assertEqual(out.getpixel((21, 21)), out.getpixel((30, 30)))           # same block
        self.assertNotEqual(out.getpixel((30, 30)), base.getpixel((30, 30)))

    def test_items_render_in_order(self):
        a = Item("rect", ((10, 10), (150, 100)), RED, 30)
        b = Item("rect", ((10, 10), (150, 100)), BLUE, 30)
        self.assertTrue(is_colour(render(canvas(), [a, b]).getpixel((10, 50)), BLUE))
        self.assertTrue(is_colour(render(canvas(), [b, a]).getpixel((10, 50)), RED))

    def test_items_partly_off_the_picture_are_clipped_not_fatal(self):
        out = render(canvas(), [Item("rect", ((-50, -50), (60, 60)), RED, 4),
                                Item("arrow", ((500, 500), (900, 900)), RED, 4),
                                Item("text", ((190, 110),), RED, 5, "far"),
                                Item("pixelate", ((150, 80), (400, 400)), RED, 5)])
        self.assertEqual(out.size, (200, 120))

    def test_full_resolution_stays_full_resolution(self):
        big = canvas(3840, 2160)
        width = default_width(big.size)
        self.assertGreaterEqual(width, 12)
        out = render(big, [Item("rect", ((100, 100), (1000, 800)), RED, width)])
        self.assertEqual(out.size, (3840, 2160))
        self.assertTrue(is_colour(out.getpixel((500, 100 + width // 2)), RED))
        self.assertEqual(out.getpixel((500, 100 + width + 4)), WHITE)

    def test_the_source_image_is_not_changed(self):
        base = canvas()
        render(base, [Item("rect", ((10, 10), (100, 100)), RED, 6)])
        self.assertEqual(base.getpixel((10, 50)), WHITE)


class DocumentTests(unittest.TestCase):
    def test_add_undo_redo(self):
        doc = Document(canvas())
        rect = Item("rect", ((10, 10), (100, 80)), RED, 4)
        self.assertFalse(doc.can_undo())
        self.assertTrue(doc.add(rect))
        self.assertTrue(doc.dirty and doc.can_undo() and not doc.can_redo())
        self.assertTrue(is_colour(doc.result().getpixel((50, 10)), RED))
        self.assertTrue(doc.undo())
        self.assertEqual(doc.result().getpixel((50, 10)), WHITE)
        self.assertTrue(doc.can_redo())
        self.assertTrue(doc.redo())
        self.assertTrue(is_colour(doc.result().getpixel((50, 10)), RED))
        self.assertFalse(doc.redo())

    def test_nothing_to_undo_or_redo(self):
        doc = Document(canvas())
        self.assertFalse(doc.undo())
        self.assertFalse(doc.redo())

    def test_a_new_mark_clears_redo(self):
        doc = Document(canvas())
        doc.add(Item("rect", ((10, 10), (100, 80)), RED, 4))
        doc.undo()
        doc.add(Item("ellipse", ((10, 10), (100, 80)), BLUE, 4))
        self.assertFalse(doc.can_redo())

    def test_empty_marks_are_ignored(self):
        doc = Document(canvas())
        self.assertFalse(doc.add(Item("rect", ((10, 10), (10, 10)), RED, 4)))
        self.assertFalse(doc.add(Item("text", ((10, 10),), RED, 4, "   ")))
        self.assertFalse(doc.add(Item("pixelate", ((300, 300), (400, 400)), RED, 4)))
        self.assertFalse(doc.can_undo())

    def test_step_numbers_count_up_and_follow_undo(self):
        doc = Document(canvas())
        self.assertEqual(doc.next_step_number(), 1)
        doc.add(Item("step", ((20, 20),), RED, 4, "1"))
        doc.add(Item("step", ((60, 20),), RED, 4, "2"))
        self.assertEqual(doc.next_step_number(), 3)
        doc.undo()
        self.assertEqual(doc.next_step_number(), 2)

    def test_crop_keeps_the_box_and_moves_marks_with_the_pixels(self):
        base = canvas(200, 120)
        base.paste((0, 200, 0), (100, 50, 140, 80))                 # a green patch
        doc = Document(base)
        doc.add(Item("rect", ((90, 40), (150, 90)), RED, 4))
        self.assertTrue(doc.crop((80, 30, 180, 100)))
        self.assertEqual(doc.size, (100, 70))
        out = doc.result()
        self.assertEqual(out.size, (100, 70))
        self.assertEqual(out.getpixel((40, 30)), (0, 200, 0))       # patch now at (20,20)-(60,50)
        self.assertTrue(is_colour(out.getpixel((40, 10)), RED))     # the rectangle's top edge
        self.assertEqual(out.getpixel((5, 60)), WHITE)

    def test_crop_is_clamped_and_undoable(self):
        doc = Document(canvas(200, 120))
        self.assertTrue(doc.crop((-40, -40, 100, 60)))
        self.assertEqual(doc.size, (100, 60))
        self.assertTrue(doc.undo())
        self.assertEqual(doc.size, (200, 120))
        self.assertTrue(doc.redo())
        self.assertEqual(doc.size, (100, 60))

    def test_useless_crops_do_nothing(self):
        doc = Document(canvas(200, 120))
        self.assertFalse(doc.crop((0, 0, 200, 120)))                # the whole picture
        self.assertFalse(doc.crop((300, 300, 400, 400)))            # outside it
        self.assertFalse(doc.crop((50, 50, 50, 90)))                # no width
        self.assertFalse(doc.can_undo())

    def test_undo_a_crop_brings_the_marks_back_in_place(self):
        doc = Document(canvas(200, 120))
        doc.add(Item("rect", ((90, 40), (150, 90)), RED, 4))
        before = list(doc.result().getdata())
        doc.crop((80, 30, 180, 100))
        doc.undo()
        self.assertEqual(list(doc.result().getdata()), before)

    def test_marks_after_a_crop_land_on_the_cropped_picture(self):
        doc = Document(canvas(200, 120))
        doc.crop((100, 0, 200, 120))
        doc.add(Item("rect", ((10, 10), (90, 100)), BLUE, 4))
        self.assertTrue(is_colour(doc.result().getpixel((50, 10)), BLUE))


def _display():
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


@unittest.skipUnless(_display(), "needs a display")
class EditorTests(unittest.TestCase):
    def setUp(self):
        from sparksnip import app as appmod
        from sparksnip.core import Monitor
        self.app = appmod.App(start_mode=None)
        self.monitor = Monitor('TEST-1', 0, 0, 1920, 1080)
        self.got = []
        self.pump()

    def tearDown(self):
        try:
            self.app.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def pump(self, n=10):
        import time
        for _ in range(n):
            self.app.root.update()
            time.sleep(0.01)

    def editor(self, image):
        from sparksnip.editor import EditorWindow
        ed = EditorWindow(self.app, image, self.monitor,
                          lambda img, action: self.got.append((img, action)),
                          lambda: self.got.append(None))
        self.pump()
        return ed

    def drag(self, ed, a, b):
        ed._press(Ev(*a))
        ed._motion(Ev(*b))
        ed._release(Ev(*b))
        self.pump()

    def test_drag_draws_at_full_resolution_when_the_view_is_scaled_down(self):
        ed = self.editor(canvas(3840, 2160))
        self.assertLess(ed.view, 1)
        ed.set_tool("rect")
        ed.set_colour(RED)
        ed.scale.set(20)
        v = ed.view
        self.drag(ed, (100 * v, 100 * v), (900 * v, 600 * v))
        ed.copy()
        image, action = self.got[0]
        self.assertEqual((action, image.size), ("copy", (3840, 2160)))
        self.assertTrue(is_colour(image.getpixel((500, 110)), RED))
        self.assertEqual(image.getpixel((500, 300)), WHITE)

    def test_shortcuts_undo_redo_and_copy(self):
        ed = self.editor(canvas())
        ed.set_tool("step")
        ed.set_colour(BLUE)
        ed._press(Ev(50 * ed.view, 50 * ed.view))
        self.assertTrue(ed.doc.can_undo())
        for seq in ("<Control-z>", "<Control-y>", "<Control-c>", "<Control-s>", "<Escape>"):
            self.assertTrue(ed.bind(seq), seq)          # key events themselves need a focused window
        ed.undo()
        self.assertFalse(ed.doc.items)
        ed.redo()
        self.assertEqual(len(ed.doc.items), 1)
        ed._shortcut(ed.copy)
        self.assertEqual(self.got[0][1], "copy")

    def test_crop_tool_shrinks_the_picture(self):
        ed = self.editor(canvas(200, 120))
        ed.set_tool("crop")
        v = ed.view
        self.drag(ed, (20 * v, 10 * v), (120 * v, 90 * v))
        self.assertEqual(ed.doc.size, (100, 80))
        ed.copy()
        self.assertEqual(self.got[0][0].size, (100, 80))

    def test_text_tool_places_typed_text(self):
        ed = self.editor(canvas(300, 100))
        ed.set_tool("text")
        ed.set_colour(RED)
        ed._press(Ev(20 * ed.view, 20 * ed.view))
        ed._entry.insert(0, "Hi")
        ed._commit_text()
        self.assertEqual(ed.doc.items[0].text, "Hi")

    def test_escape_cancels_and_a_clean_editor_does_not_ask(self):
        ed = self.editor(canvas())
        ed._escape()
        self.assertEqual(self.got, [None])

    def test_the_result_window_takes_the_annotated_picture_as_the_screenshot(self):
        from sparksnip import core
        sent = []
        self.app.clipboard.copy_image = lambda img: sent.append(img)
        popup = self.app.open_popup(canvas(200, 120), self.monitor)
        popup.show_image(None)
        self.pump()
        popup.edit()
        self.pump()
        ed = self.app.editor
        self.assertIsNotNone(ed)
        ed.set_tool("rect")
        ed.set_colour(RED)
        v = ed.view
        self.drag(ed, (20 * v, 20 * v), (100 * v, 90 * v))
        ed.copy()
        self.pump()
        self.assertIsNone(self.app.editor)
        self.assertTrue(is_colour(popup.image.getpixel((60, 20)), RED))
        self.assertIs(sent[-1], popup.image)
        with Image.open(core.latest_path()) as latest:
            self.assertTrue(is_colour(latest.convert("RGB").getpixel((60, 20)), RED))
        popup.close()

    def test_editor_text_fits(self):
        from langcheck import clipped
        ed = self.editor(canvas(800, 400))
        self.assertEqual(clipped(ed), [])


if __name__ == '__main__':
    unittest.main()
