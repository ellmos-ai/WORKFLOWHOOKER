from workflowhooker.protocol import ProjectState


def test_project_state_defaults_are_all_clean():
    state = ProjectState()
    assert state.has_lock is False
    assert state.git_dirty is False
    assert state.uncommitted_files == 0
    assert state.lock_files == ()
    assert state.changed_top_level_dirs == ()
