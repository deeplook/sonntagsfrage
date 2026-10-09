import unittest
from fractions import Fraction

from elections.animation import animation_timing, party_color


class PartyColorTests(unittest.TestCase):
    def test_state_poll_party_name_variants_keep_party_colors(self) -> None:
        expected = {
            "CDU": "#343b4a",
            "Grüne": "#43a56b",
            "Linke": "#ad4b8e",
            "BVB/FW": "#e48a3f",
            "Plus Brandenburg": "#6851a3",
            "Tierschutzpartei": "#36a6a0",
        }
        for party, color in expected.items():
            with self.subTest(party=party):
                self.assertEqual(party_color(party), color)

    def test_unknown_party_keeps_neutral_fallback(self) -> None:
        self.assertEqual(party_color("New Local List"), "#8895a7")

    def test_glide_duration_does_not_depend_on_poll_count(self) -> None:
        brandenburg_frames, brandenburg_rate, brandenburg_steps = animation_timing(78, 60, True)
        federal_frames, federal_rate, federal_steps = animation_timing(760, 60, True)
        brandenburg_transition = brandenburg_steps / float(Fraction(brandenburg_rate))
        federal_transition = federal_steps / float(Fraction(federal_rate))
        self.assertAlmostEqual(brandenburg_transition, 0.08, places=2)
        self.assertAlmostEqual(federal_transition, 0.08, places=2)
        self.assertEqual(brandenburg_frames, 3000)
        self.assertGreater(federal_frames, 3000)

if __name__ == "__main__":
    unittest.main()
