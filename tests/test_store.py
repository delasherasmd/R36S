import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))

import store  # noqa: E402


class FakeGame(object):
    def __init__(self, path, name, fav=False):
        self.path = path
        self.name = name
        self.sortname = name.lower()
        self.es_favorite = fav
        self.es_playcount = 0
        self.es_lastplayed = 0


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.st = store.Store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def reload(self):
        self.st.save()
        self.st = store.Store(self.tmp)

    def test_lists_and_priority(self):
        st = self.st
        self.assertTrue(st.create("RPG", pinned=True))
        self.assertTrue(st.create("Pendientes"))
        self.assertFalse(st.create("rpg"))  # sin duplicados
        self.assertEqual(st.priority("Pendientes"), 2)
        self.assertTrue(st.move("Pendientes", -1))
        self.assertEqual(st.category_names(), ["Pendientes", "RPG"])
        self.assertTrue(st.move_to("RPG", 0))
        self.assertEqual(st.category_names(), ["RPG", "Pendientes"])
        self.assertEqual(st.pinned_names(), ["RPG"])
        self.reload()
        self.assertEqual(self.st.category_names(), ["RPG", "Pendientes"])
        self.assertTrue(self.st.is_pinned("RPG"))

    def test_games_priority_keeps_missing_games(self):
        st = self.st
        st.create("L")
        for p in ("/a", "/b", "/missing", "/c"):
            st.add("L", p)
        visible = ["/a", "/b", "/c"]  # /missing no esta en la tarjeta ahora mismo
        self.assertTrue(st.move_game("L", visible, "/c", -2))
        self.assertEqual(st.games_in("L"), ["/c", "/a", "/b", "/missing"])
        self.assertTrue(st.move_game("L", ["/c", "/a", "/b"], "/b", index=0))
        self.assertEqual(st.games_in("L")[:3], ["/b", "/c", "/a"])
        self.assertFalse(st.move_game("L", ["/b"], "/b", -1))

    def test_rename_delete_toggle(self):
        st = self.st
        st.create("A")
        st.create("B")
        self.assertFalse(st.rename("A", "b"))
        self.assertTrue(st.rename("A", "Acción"))
        self.assertTrue(st.toggle("Acción", "/x"))
        self.assertEqual(st.categories_of("/x"), ["Acción"])
        self.assertFalse(st.toggle("Acción", "/x"))
        self.assertTrue(st.delete("B"))
        self.assertEqual(st.category_names(), ["Acción"])

    def test_favorites_order(self):
        st = self.st
        a, b, c = FakeGame("/a", "A", fav=True), FakeGame("/b", "B"), FakeGame("/c", "C")
        st.toggle_favorite(c)
        st.toggle_favorite(b)
        games = [a, b, c]
        order = [g.path for g in st.favorites_ordered(games)]
        # los de ES (a) se anaden al final la primera vez
        self.assertEqual(order, ["/c", "/b", "/a"])
        self.assertTrue(st.move_favorite(order, "/a", index=0))
        self.assertEqual([g.path for g in st.favorites_ordered(games)], ["/a", "/c", "/b"])
        st.toggle_favorite(c)  # quitar
        self.assertEqual([g.path for g in st.favorites_ordered(games)], ["/a", "/b"])
        self.reload()
        self.assertEqual([g.path for g in self.st.favorites_ordered(games)], ["/a", "/b"])

    def test_fix_paths_after_moving_roms(self):
        st = self.st
        st.create("L")
        st.add("L", "/roms/snes/Chrono.sfc")
        st.add("L", "/roms/gba/Gone.gba")
        st.data["fav_order"] = ["/roms/snes/Chrono.sfc"]
        by_path = {"/roms2/snes/Chrono.sfc": None}
        self.assertTrue(st.fix_paths(by_path))
        self.assertEqual(st.games_in("L"), ["/roms2/snes/Chrono.sfc", "/roms/gba/Gone.gba"])
        self.assertEqual(st.data["fav_order"], ["/roms2/snes/Chrono.sfc"])

    def test_backup_used_when_file_corrupted(self):
        st = self.st
        st.create("Primera")
        st.save()
        st.create("Segunda")
        st.dirty = True
        st.save()  # library.json.bak contiene 'Primera'
        with open(os.path.join(self.tmp, "library.json"), "w") as f:
            f.write("{roto")
        st2 = store.Store(self.tmp)
        self.assertEqual(st2.category_names(), ["Primera"])

    def test_history(self):
        with open(os.path.join(self.tmp, "history.log"), "w") as f:
            f.write("1700000000\t600\t/roms/a.sfc\n1700001000\t3\t/roms/a.sfc\nbad line\n"
                    "1700002000\t3600\t/roms/b.sfc\n")
        st = store.Store(self.tmp)
        a = FakeGame("/roms/a.sfc", "a")
        self.assertEqual(st.playtime(a), 600)
        self.assertEqual(st.play_count(a), 1)
        self.assertEqual(st.last_played(a), 1700001000)

    def test_es_collections_roundtrip(self):
        st = self.st
        coll = os.path.join(self.tmp, "collections")
        os.makedirs(coll)
        with open(os.path.join(coll, "custom-Arcade.cfg"), "w") as f:
            f.write("/roms/mame/sf2.zip\n~/x.zip\n/roms/unknown.zip\n")
        n = st.import_from_es(coll, "/home/ark", {"/roms/mame/sf2.zip", "/home/ark/x.zip"})
        self.assertEqual(n, 2)
        self.assertEqual(st.games_in("Arcade"), ["/roms/mame/sf2.zip", "/home/ark/x.zip"])
        st.create("Mis/RPG")
        st.add("Mis/RPG", "/roms/snes/ct.sfc")
        self.assertEqual(st.export_to_es(coll), 2)
        with open(os.path.join(coll, "custom-Mis-RPG.cfg")) as f:
            self.assertEqual(f.read(), "/roms/snes/ct.sfc\n")

    def test_saved_file_is_readable_json(self):
        self.st.create("Lista")
        self.st.save()
        with open(os.path.join(self.tmp, "library.json")) as f:
            d = json.load(f)
        self.assertEqual(d["categories"][0]["name"], "Lista")


if __name__ == "__main__":
    unittest.main()
