from pathlib import Path

from scribd_downloader.browser import PROFILE_DIR, launch_options, print_preferences


def test_persistent_launch_uses_local_profile() -> None:
    options = launch_options(guest=False, headless=True)
    assert options["persistent_context"] is True
    assert options["user_data_dir"] == str(PROFILE_DIR)
    assert options["main_world_eval"] is True


def test_guest_launch_has_no_profile() -> None:
    options = launch_options(guest=True, headless=True)
    assert "persistent_context" not in options
    assert "user_data_dir" not in options


def test_print_preferences_target_partial_file(tmp_path: Path) -> None:
    output = tmp_path / ".book.partial.pdf"
    preferences = print_preferences(output)
    assert preferences["print.always_print_silent"] is True
    assert preferences["print.print_to_filename"] == str(output.resolve())
    assert preferences["print.save_as_pdf.use_page_rule_size_as_paper_size.enabled"] is True
