class DummyPredictor:
    def __init__(self):
        self.calls = 0

    def predict(self, game, competition):
        self.calls += 1
        return (1, 0)


def test_predictions_cached_across_competitions():
    predictor = DummyPredictor()
    cache = {}
    competitions = ['liga-eins', 'liga-zwei', 'liga-drei']

    # Simulate same match across competitions
    match_id = 'Home|Away|2026-01-01T12:00:00'

    for comp in competitions:
        if match_id in cache:
            tip = cache[match_id]
        else:
            tip = predictor.predict(None, comp)
            cache[match_id] = tip

    assert predictor.calls == 1
    assert cache[match_id] == (1, 0)
