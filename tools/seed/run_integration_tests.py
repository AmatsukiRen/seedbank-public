"""User entry: isolated offline provider/credential/UI regressions."""
import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path


def block_network(event, _args):
    if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
        raise RuntimeError("Provider regressions must stay offline")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    followup = parser.add_mutually_exclusive_group()
    followup.add_argument("--reply-followup", action="store_true", help="Only the three corrected reply delivery cases")
    followup.add_argument("--observation-status-followup", action="store_true", help="Only the corrected runtime counter case")
    options = parser.parse_args()
    sys.addaudithook(block_network)
    with tempfile.TemporaryDirectory(prefix="seedbank-provider-regression-") as directory:
        os.environ.update(HOME=directory, USERPROFILE=directory,
                          APPDATA=str(Path(directory) / "Roaming"),
                          LOCALAPPDATA=str(Path(directory) / "Local"),
                          QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", SEEDBANK_LANG="zh_CN")
        names = ["test_provider_presets", "test_api_credentials", "test_channels", "test_channel_continuity", "test_observing", "test_workbuddy_transport", "test_runtime_self", "test_qq_group_reply", "test_qq_security",
                 "test_quick.QuickTest.test_first_launch_without_model_offers_selection_instead_of_loading",
                 "test_quick.QuickTest.test_clearing_model_preserves_other_preferences_and_survives_reopen",
                 "test_avatar_expression", "test_presentation", "test_live2d_model", "test_live2d_motion", "test_live2d_lifecycle",
                 "test_quick.QuickTest.test_avatar_mood_changes_expression_without_restarting_hand_gesture",
                 "test_quick.QuickTest.test_avatar_automatic_expression_stops_when_hidden_reduced_or_dormant",
                 "test_quick.QuickTest.test_avatar_does_not_force_a_happy_face_after_a_sad_conversation",
                 "test_quick.QuickTest.test_focused_moods_do_not_show_loading_on_entry_or_ambient_ticks",
                 "test_quick.QuickTest.test_background_pulse_and_status_read_do_not_show_loading_expression",
                 "test_quick.QuickTest.test_loading_expression_only_lasts_for_an_accepted_conversation",
                 "test_quick.QuickTest.test_reply_text_expression_and_gesture_arrive_together",
                 "test_quick.QuickTest.test_reply_animation_is_not_replayed_by_history_or_duplicate_request",
                 "test_quick.QuickTest.test_reply_animation_stops_on_hide_reduced_motion_dormancy_or_next_message",
                 "test_quick.QuickTest.test_channel_settings_are_offline_until_explicit_start",
                 "test_quick.QuickTest.test_provider_presets_update_compatibility_and_clear_old_credentials",
                 "test_quick.QuickTest.test_provider_options_show_in_each_language_without_calls",
                 "test_quick.QuickTest.test_api_key_is_masked_and_saved_outside_life_pack",
                 "test_quick.QuickTest.test_api_key_draft_clears_when_provider_changes",
                 "test_quick.QuickTest.test_codex_settings_draft_fields_and_usage_do_not_contact_model",
                 "test_quick.QuickTest.test_all_pages_load_without_qml_errors"]
        if options.reply_followup:
            names = ["test_presentation.PresentationTest.test_reply_cue_survives_carrier_and_request_replay_without_another_call",
                     "test_quick.QuickTest.test_loading_expression_only_lasts_for_an_accepted_conversation",
                     "test_quick.QuickTest.test_reply_animation_stops_on_hide_reduced_motion_dormancy_or_next_message"]
        elif options.observation_status_followup:
            names = ["test_runtime_self.RuntimeSelfTest.test_ignored_duplicate_and_failed_delivery_have_truthful_counters"]
        else:
            # Include all UI flows, including the complete locale/size matrix,
            # instead of repeatedly testing a hand-picked subset of QuickTest.
            names = [name for name in names if not name.startswith("test_quick.")] + ["test_quick"]
        result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
