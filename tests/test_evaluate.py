"""python3 -m unittest tests.test_evaluate  — LLM 호출 없음."""
import json
import unittest
from pathlib import Path

from ncp_maps.evaluate import (
    COMPLEX_KINDS, LANE_SHIFT_KINDS, classify, evaluate_routes, route_metrics,
)
from ncp_maps.narrate import parse_partial, validate_narration

FIX = json.loads((Path(__file__).parent / "fixtures" / "route_sample.json").read_text(encoding="utf-8"))
TRIP = {"origin": "죽전역", "goal": "강남역", "via": None}


class Classify(unittest.TestCase):
    def test_trap_ic_in_target_is_left_turn(self):
        # 방면 대상에 IC 가 있어도 동작은 좌회전이다
        self.assertEqual(classify({"instructions": "'판교IC(서울·청계·송파)' 방면으로 좌회전"}), "left")

    def test_exit_after_at(self):
        self.assertEqual(classify({"instructions": "서초IC에서 '양재역' 방면으로 오른쪽 고속도로 출구"}), "hwy_exit")

    def test_overpass_left(self):
        self.assertEqual(classify({"instructions": "만당주유소앞삼거리에서 '서울, 판교' 방면으로 왼쪽 고가차도 진입"}), "overpass")

    def test_sideroad(self):
        self.assertEqual(classify({"instructions": "'강남역, 성남' 방면으로 지하차도 오른쪽 옆길"}), "sideroad")

    def test_branch(self):
        self.assertEqual(classify({"instructions": "금토분기점에서 '서울, 양재' 방면으로 오른쪽 방향"}), "branch")

    def test_code_wins_over_text(self):
        self.assertEqual(classify({"type": 88, "instructions": "아무 말"}), "goal")

    def test_unknown_is_other(self):
        self.assertEqual(classify({"instructions": "정체불명 문구"}), "other")


class Metrics(unittest.TestCase):
    def setUp(self):
        self.route = FIX["routes"][0]
        self.m = route_metrics(self.route)

    def test_total_excludes_goal_and_via(self):
        kinds = [classify(g) for g in self.route["guides"]]
        expect = sum(1 for k in kinds if k not in ("goal", "via"))
        self.assertEqual(self.m["maneuver_total"], expect)

    def test_lane_shift_definition(self):
        kinds = [classify(g) for g in self.route["guides"]]
        self.assertEqual(self.m["lane_shift_count"], sum(1 for k in kinds if k in LANE_SHIFT_KINDS))

    def test_complex_points_have_steps_and_kinds(self):
        for cp in self.m["complex_points"]:
            self.assertIn(cp["kind"], COMPLEX_KINDS)
            self.assertEqual(classify(self.route["guides"][cp["step"]]), cp["kind"])

    def test_highway_ratio_is_bounded(self):
        self.assertGreaterEqual(self.m["highway_ratio"], 0)
        self.assertLessEqual(self.m["highway_ratio"], 1.0)


class Evaluate(unittest.TestCase):
    def setUp(self):
        self.ev = evaluate_routes(FIX["routes"], TRIP)

    def test_ranks_are_dense_and_start_at_1(self):
        ranks = sorted({r["comfort"]["rank"] for r in self.ev["routes"]})
        self.assertEqual(ranks, list(range(1, len(ranks) + 1)))

    def test_identical_routes_share_rank(self):
        import copy
        twin = [copy.deepcopy(FIX["routes"][0]), copy.deepcopy(FIX["routes"][0])]
        twin[1]["option"] = "clone"
        ev = evaluate_routes(twin, TRIP)
        self.assertEqual([r["comfort"]["rank"] for r in ev["routes"]], [1, 1])
        self.assertTrue(all(r["comfort"]["tied"] for r in ev["routes"]))
        self.assertIn("공동 1위", ev["routes"][0]["facts"][-1]["text"])

    def test_most_comfortable_has_rank_1(self):
        best = self.ev["comparison"]["most_comfortable"]
        r = next(r for r in self.ev["routes"] if r["id"] == best)
        self.assertEqual(r["comfort"]["rank"], 1)

    def test_fact_ids_unique_and_prefixed(self):
        ids = [f["id"] for r in self.ev["routes"] for f in r["facts"]]
        self.assertEqual(len(ids), len(set(ids)))
        for r in self.ev["routes"]:
            for f in r["facts"]:
                self.assertTrue(f["id"].startswith(r["rid"] + ".F"))

    def test_complex_facts_carry_step(self):
        for r in self.ev["routes"]:
            for f in r["facts"]:
                if f["kind"] == "complex":
                    self.assertIn("step", f)

    def test_hazards_slot_present_and_empty(self):
        for r in self.ev["routes"]:
            self.assertEqual(r["hazards"], [])


class Validate(unittest.TestCase):
    def setUp(self):
        self.ev = evaluate_routes(FIX["routes"], TRIP)
        r0 = self.ev["routes"][0]
        self.rid = r0["id"]
        self.good_id = r0["facts"][0]["id"]
        self.some_step = next((cp["step"] for cp in r0["metrics"]["complex_points"]), None)

    def _narr(self, basis, step):
        return {"routes": [{
            "id": self.rid,
            "overview": [{"text": "a", "basis": basis}],
            "verdict": {"text": "b", "basis": [self.good_id]},
            "comfort_note": {"text": "c", "basis": ["GK"]},
            "cautions": [],
            "roadview_picks": [{"step": step, "reason": "x"}],
        }], "comparison": {"summary": []}}

    def test_unknown_basis_marked_unverified_not_dropped(self):
        v = validate_narration(self._narr(["R9.F99"], 0), self.ev)
        s = v["routes"][0]["overview"][0]
        self.assertTrue(s["unverified"]); self.assertEqual(s["text"], "a")

    def test_gk_is_verified_and_flagged(self):
        v = validate_narration(self._narr(["GK"], 0), self.ev)
        s = v["routes"][0]["overview"][0]
        self.assertFalse(s["unverified"]); self.assertTrue(s["general_knowledge"])

    def test_empty_basis_is_unverified(self):
        v = validate_narration(self._narr([], 0), self.ev)
        self.assertTrue(v["routes"][0]["overview"][0]["unverified"])

    def test_roadview_pick_with_bad_step_dropped(self):
        v = validate_narration(self._narr([self.good_id], 9999), self.ev)
        self.assertEqual(v["routes"][0]["roadview_picks"], [])
        self.assertEqual(v["routes"][0]["dropped_picks"], 1)

    def test_roadview_pick_with_complex_step_kept(self):
        if self.some_step is None:
            self.skipTest("픽스처에 복잡 분기 없음")
        v = validate_narration(self._narr([self.good_id], self.some_step), self.ev)
        self.assertEqual(len(v["routes"][0]["roadview_picks"]), 1)


class PartialJson(unittest.TestCase):
    def test_open_string_is_dropped(self):
        self.assertEqual(parse_partial('{"a":[{"text":"x","basis":[]},{"text":"y'),
                         {"a": [{"text": "x", "basis": []}]})

    def test_nothing_closed_yet(self):
        self.assertIsNone(parse_partial('{"comparison":{"headline":{"text":"abc'))

    def test_brace_and_escaped_quote_inside_string(self):
        raw = r'{"s":[{"t":"a}]{\"q"},'
        self.assertEqual(parse_partial(raw), {"s": [{"t": 'a}]{"q'}]})

    def test_complete_document(self):
        self.assertEqual(parse_partial('{"a":{"b":[1,2]}}'), {"a": {"b": [1, 2]}})

    def test_internal_route_id_replaced_by_label(self):
        ev = evaluate_routes(FIX["routes"], TRIP)
        r0 = ev["routes"][0]
        v = validate_narration({"comparison": {"headline": {"text": f"빠른길({r0['id']})로 가. {r0['id']} 추천", "basis": ["GK"]},
                                               "summary": []}, "routes": []}, ev)
        self.assertNotIn(r0["id"], v["comparison"]["headline"]["text"])

    def test_headline_counted_in_stats(self):
        ev = evaluate_routes(FIX["routes"], TRIP)
        fid = ev["routes"][0]["facts"][0]["id"]
        v = validate_narration({"comparison": {"headline": {"text": "h", "basis": [fid]}, "summary": []},
                                "routes": []}, ev)
        self.assertFalse(v["comparison"]["headline"]["unverified"])
        self.assertEqual(v["stats"]["sentences"], 1)


if __name__ == "__main__":
    unittest.main()
