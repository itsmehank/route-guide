"""python3 -m unittest tests.test_briefing  — 출발 전 브리핑(준비 지점 후보). LLM·네트워크 없음."""
import json
import unittest
from pathlib import Path

from ncp_maps.briefing import build_briefing, josa, place_name, sign_target
from ncp_maps.hazards import on_route

FIX = json.loads((Path(__file__).parent / "fixtures" / "route_sample.json").read_text(encoding="utf-8"))


class Clues(unittest.TestCase):
    def test_sign_target(self):
        self.assertEqual(sign_target("금토분기점에서 '서울, 양재' 방면으로 오른쪽 방향"), "서울, 양재")

    def test_place_name(self):
        self.assertEqual(place_name("서초IC에서 '양재역' 방면으로 오른쪽 고속도로 출구"), "서초IC")
        self.assertIsNone(place_name("유턴"))

    def test_josa(self):
        self.assertEqual(josa("‘금곡교차로’", "을", "를"), "‘금곡교차로’를")
        self.assertEqual(josa("‘판교역’", "을", "를"), "‘판교역’을")
        self.assertEqual(josa("‘양재IC’", "을", "를"), "‘양재IC’를")


class Briefing(unittest.TestCase):
    def setUp(self):
        self.b = build_briefing(FIX["routes"][0], None, None)
        self.items = self.b["items"]

    def test_items_in_route_order(self):
        idx = [it["path_index"] for it in self.items]
        self.assertEqual(idx, sorted(idx))

    def test_candidates_far_to_near_and_end_with_approach(self):
        for it in self.items:
            d = [c["dist_m"] for c in it["candidates"]]
            self.assertEqual(d, sorted(d, reverse=True), it["instruction"])
            self.assertEqual(it["candidates"][-1]["role"], "approach")

    def test_highway_branch_gets_sign_marks(self):
        it = next(x for x in self.items if "금토분기점" in x["instruction"])
        self.assertEqual([c["dist_m"] for c in it["candidates"][:3]], [2000, 1000, 500])
        self.assertIn("서울, 양재", it["candidates"][0]["say"])

    def test_candidates_stay_on_same_road(self):
        # 앞 안내 지점보다 먼 '예고 표지' 후보는 다른 길 위라 만들지 않는다 (연속 동작 후보만 예외)
        for it in self.items:
            room = FIX["routes"][0]["guides"][it["step"]]["distance"]
            for c in it["candidates"]:
                if c["role"] in ("sign", "prep"):
                    self.assertLess(c["dist_m"], room, it["instruction"])

    def test_segments_cover_whole_route(self):
        segs = self.b["segments"]
        self.assertEqual(len(segs), len(self.items) + 1)       # 출발→1, …, 마지막→도착
        self.assertEqual(segs[0]["from"], -1)
        self.assertIsNone(segs[-1]["to"])
        total = sum(sg["km"] for sg in segs)
        self.assertAlmostEqual(total, FIX["routes"][0]["distance_km"], delta=0.6)

    def test_segment_steps_exclude_checkpoints(self):
        texts = {it["instruction"] for it in self.items if it["type"] == "maneuver"}
        for sg in self.b["segments"]:
            for st in sg["steps"]:
                self.assertNotIn(st["text"], texts)

    def test_short_gap_becomes_combo(self):
        it = next(x for x in self.items if "금곡교차로" in x["instruction"])
        self.assertEqual(it["candidates"][0]["role"], "combo")



class OnRoute(unittest.TestCase):
    SEC = [{"pointIndex": 0, "pointCount": 10, "name": "경부고속도로"},
           {"pointIndex": 10, "pointCount": 10, "name": "강남대로"}]

    def test_side_road_child_accident_dropped_on_expressway(self):
        # 실측 사례: 경부고속도로 247m 옆 서초초교 어린이 사고다발
        self.assertFalse(on_route({"type": "accident_schoolzone", "distance_m": 247, "path_index": 5}, self.SEC))
        self.assertFalse(on_route({"type": "frequentzoneChild", "distance_m": 10, "path_index": 5}, self.SEC))

    def test_on_expressway_accident_kept(self):
        self.assertTrue(on_route({"type": "frequentzoneLg", "distance_m": 12, "path_index": 5}, self.SEC))

    def test_surface_road_threshold(self):
        self.assertTrue(on_route({"type": "frequentzoneLg", "distance_m": 40, "path_index": 15}, self.SEC))
        self.assertFalse(on_route({"type": "frequentzoneLg", "distance_m": 150, "path_index": 15}, self.SEC))


if __name__ == "__main__":
    unittest.main()
