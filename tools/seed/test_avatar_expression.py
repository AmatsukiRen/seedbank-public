"""User-run presentation regressions; no native renderer or real life pack."""
import unittest
from unittest.mock import Mock, call

from seedbank.quick.avatar_expression import EXPRESSIONS, ExpressionPlayback, choose_expression, mood_style


class AvatarExpressionTest(unittest.TestCase):
    def test_known_moods_and_negative_words_keep_their_meaning(self):
        for mood, expected in (("开心", "happy"), ("不开心", "sad"), ("失落", "sad"),
                               ("认真", "idle"), ("好奇", "idle"), ("紧张", "nervous"),
                               ("生气", "angry"), ("害羞", "warm"), (" SAD ", "sad")):
            with self.subTest(mood=mood):
                self.assertEqual(mood_style(mood), expected)

    def test_quiet_tired_and_unknown_moods_do_not_invent_emotion(self):
        for mood in ("平静", "安静", "有点困", "疲惫", "发呆", "未知心情", None):
            self.assertEqual(choose_expression(mood_style(mood)), "idle")

    def test_low_energy_softens_positive_display_without_reversing_sadness(self):
        self.assertEqual(mood_style("开心", .1), "warm")
        self.assertEqual(mood_style("专注", .1), "idle")
        self.assertEqual(mood_style("失落", .1), "sad")
        for value in (None, "invalid", float("nan"), float("inf")):
            self.assertEqual(mood_style("开心", value), "happy")

    def test_choice_is_limited_to_current_mood_and_avoids_repetition(self):
        self.assertEqual(choose_expression("happy", "happy"), "warm")
        self.assertEqual(choose_expression("happy", "warm"), "happy")
        for style in ("sad", "nervous", "angry"):
            self.assertEqual(choose_expression(style, "happy"), style)

    def test_loading_expression_is_never_chosen_as_an_ambient_mood(self):
        for mood in ("好奇", "认真", "专注", "思考", "curious", "focused", "thinking"):
            with self.subTest(mood=mood):
                self.assertEqual(choose_expression(mood_style(mood)), "idle")
        self.assertEqual(choose_expression("think", "happy"), "idle")

    def test_same_expression_does_not_restart_each_frame(self):
        player, model = ExpressionPlayback(), Mock()
        for _ in range(100):
            player.update(model, "sad", set(EXPRESSIONS.values()))
        model.ResetExpressions.assert_called_once()
        model.SetExpression.assert_called_once_with("SeedSad")
        model.StartMotion.assert_not_called()

    def test_return_to_neutral_clears_expression_without_touching_gesture(self):
        player, model = ExpressionPlayback(), Mock()
        for state in ("happy", "idle", "idle", "nervous"):
            player.update(model, state, set(EXPRESSIONS.values()))
        self.assertEqual(model.ResetExpressions.call_count, 3)
        self.assertEqual(model.SetExpression.call_args_list, [call("SeedHappy"), call("SeedNervous")])
        model.StartMotion.assert_not_called()

    def test_custom_model_missing_expression_falls_back_without_random_costumes(self):
        player, model = ExpressionPlayback(), Mock()
        for state in ("happy", "sad", "think", "idle"):
            player.update(model, state, {"Costume", "HeartEyes"})
        model.ResetExpressions.assert_called_once()
        model.SetExpression.assert_not_called()


if __name__ == "__main__":
    unittest.main()
