from shadow_mm.fair_value import FairValueModel, binary_up_probability


def test_binary_probability_moves_with_price_relative_to_target() -> None:
    assert binary_up_probability(101, 100, 0.001, 60) > 0.5
    assert binary_up_probability(99, 100, 0.001, 60) < 0.5


def test_rolling_external_spot_requires_frozen_minimum_sample() -> None:
    model = FairValueModel(["BTC"], minimum_volatility_samples=2)
    for second, price in enumerate((100.0, 100.1, 100.05), start=1):
        model.update_event(
            {
                "source": "coinbase_ws",
                "payload": {
                    "product_id": "BTC-USD",
                    "best_bid": str(price - 0.01),
                    "best_ask": str(price + 0.01),
                },
            },
            second * 1_000_000_000,
        )
    assert model.volatility["BTC"].sigma_per_sqrt_second(2) is not None
