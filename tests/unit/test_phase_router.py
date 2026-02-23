from kernel.use_cases.route_phase import RoutedPhase


def test_routed_phase_shape() -> None:
    routed = RoutedPhase(phase="1.1-Bootstrap", blocked_code=None, reason="ok", next_action="continue")
    assert routed.phase == "1.1-Bootstrap"
