from utils import clamp

def test_clamp_lower():
    assert clamp(-5, 0, 10) == 0

def test_clamp_in_range():
    assert clamp(5, 0, 10) == 5
