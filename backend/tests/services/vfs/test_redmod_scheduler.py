from rippermod_manager.schemas.deploy import RedmodDeployResult
from rippermod_manager.services.vfs import deploy_service, redmod_scheduler


def test_compile_job_records_the_result_and_its_time(session, make_game, monkeypatch):
    game = make_game()
    monkeypatch.setattr(
        deploy_service,
        "redmod_deploy",
        lambda _g: RedmodDeployResult(ran=False, skipped_reason="REDmod binary not found"),
    )
    redmod_scheduler._compile_job(game.id)
    st = redmod_scheduler.redmod_status(game.id)
    assert st.state == "idle"
    assert st.last_result is not None
    assert st.last_result.skipped_reason == "REDmod binary not found"
    assert st.last_finished_at is not None


def test_status_is_idle_with_no_result_for_an_unknown_game():
    st = redmod_scheduler.redmod_status(4242)
    assert st.state == "idle" and st.last_result is None and st.last_finished_at is None


def test_request_redmod_compile_hands_the_game_id_to_the_runner(
    session, make_game, background_requests
):
    game = make_game()
    assert redmod_scheduler.request_redmod_compile(game) is True
    assert background_requests["redmod"] == [game.id]


def _fail_if_called(_g):
    raise AssertionError("redmod_deploy must not run")


def test_compile_requested_before_undeploy_is_skipped(session, make_game, monkeypatch):
    game = make_game()
    monkeypatch.setattr(deploy_service, "redmod_deploy", _fail_if_called)
    redmod_scheduler.request_redmod_compile(game)
    redmod_scheduler.mark_undeployed(game.id)

    redmod_scheduler._compile_job(game.id)

    st = redmod_scheduler.redmod_status(game.id)
    assert st.last_result is not None
    assert st.last_result.ran is False
    assert st.last_result.skipped_reason == "Game was undeployed after this compile was requested"


def test_compile_requested_after_undeploy_runs(session, make_game, monkeypatch):
    game = make_game()
    ran: list[int] = []

    def fake_deploy(g):
        ran.append(g.id)
        return RedmodDeployResult(ran=True, success=True)

    monkeypatch.setattr(deploy_service, "redmod_deploy", fake_deploy)
    redmod_scheduler.request_redmod_compile(game)
    redmod_scheduler.mark_undeployed(game.id)
    redmod_scheduler.request_redmod_compile(game)

    redmod_scheduler._compile_job(game.id)

    assert ran == [game.id]
