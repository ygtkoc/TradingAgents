from src.services.telegram_parser import parse_telegram_signal


def test_parse_structured_long_signal():
    parsed = parse_telegram_signal(
        """
        #BTCUSDT LONG
        Entry: 66200 - 66800
        TP1: 67500
        TP2: 69000
        SL: 64800
        Lev: 10x
        """
    )

    assert parsed.symbol == "BTCUSDT"
    assert parsed.direction == "long"
    assert parsed.entry_min == 66200
    assert parsed.entry_max == 66800
    assert parsed.take_profits == [67500, 69000]
    assert parsed.stop_loss == 64800
    assert parsed.leverage == 10
    assert parsed.confidence == 1.0
    assert parsed.warnings == []


def test_parse_turkish_short_signal():
    parsed = parse_telegram_signal(
        """
        ETH short
        giris 3200/3220
        hedef 3100
        zarar kes 3290
        """
    )

    assert parsed.symbol == "ETHUSDT"
    assert parsed.direction == "short"
    assert parsed.entry_min == 3200
    assert parsed.entry_max == 3220
    assert parsed.take_profits == [3100]
    assert parsed.stop_loss == 3290
    assert parsed.warnings == []


def test_missing_stop_loss_reduces_confidence():
    parsed = parse_telegram_signal("SOL long entry 150 tp 160")

    assert parsed.symbol == "SOLUSDT"
    assert parsed.direction == "long"
    assert "missing_stop_loss" in parsed.warnings
    assert parsed.confidence < 1.0
