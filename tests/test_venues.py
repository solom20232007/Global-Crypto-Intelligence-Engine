from gcie.venues import VENUES, VENUE_BY_ID, get_venues


def test_registry_covers_required_regions():
    regions = {venue.region for venue in VENUES}
    assert {"south_korea", "offshore_global", "japan", "united_states"} <= regions


def test_korean_venues_are_krw_spot_sources():
    korean = get_venues(region="south_korea")
    assert {"upbit", "bithumb", "coinone", "korbit"} <= {
        venue.venue_id for venue in korean
    }
    assert all("spot" in venue.market_types for venue in korean)


def test_derivatives_registry_includes_oi_and_funding():
    for venue_id in ("binance", "okx", "bybit", "bitget", "mexc"):
        venue = VENUE_BY_ID[venue_id]
        assert "open_interest" in venue.data_families
        assert "funding" in venue.data_families


def test_china_linked_venues_are_not_mislabelled_as_mainland_domestic():
    assert VENUE_BY_ID["htx"].region == "offshore_global"
    assert "mainland-China" in VENUE_BY_ID["htx"].notes


def test_filters_are_deterministic():
    tier_one = get_venues(tier=1)
    assert tier_one
    assert all(venue.tier == 1 for venue in tier_one)
    assert get_venues(market_type="perpetual")
