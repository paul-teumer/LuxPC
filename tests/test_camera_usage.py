from autobrightness import camera_usage


def test_display_name_of_desktop_application_path():
    assert camera_usage._display_name("C:#Users#pault#AppData#Roaming#Zoom#bin#Zoom.exe") == "Zoom.exe"


def test_display_name_of_packaged_application():
    assert camera_usage._display_name("MSTeams_8wekyb3d8bbwe") == "MSTeams"


def test_own_entry_matches_registry_notation():
    assert "\\" not in camera_usage.own_entry_name()
    assert camera_usage.own_entry_name().endswith(".exe")


def test_listing_does_not_raise_and_excludes_given_entry():
    every_application = camera_usage.applications_using_camera(excluded_entry="-")
    assert isinstance(every_application, list)
