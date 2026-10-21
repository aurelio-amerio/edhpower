import pytest

from edhpower.config import COMPONENT_NAMES, ScoringConfig, load_config


def test_default_profiles_load_with_published_constants():
    cfg = load_config()
    assert isinstance(cfg, ScoringConfig) and cfg.config_version == 1
    assert cfg.curve.name == "edhpowerlevel-2026-08" and cfg.curve.power_curve[-1] == 1000 and cfg.curve.favor_price == 0.25
    assert cfg.curve.efficiency_limits == (0.65, 1.1) and cfg.curve.land == 0.6 and cfg.curve.reserved == 0.2
    assert cfg.components.name == "v1" and set(cfg.components.parts) == set(COMPONENT_NAMES)
    assert abs(sum(p.weight for p in cfg.components.parts.values()) - 1.0) < 1e-9
    assert cfg.tipping.threshold == 0.8 and cfg.tipping.max_turn == 7
    assert cfg.stamp() == {"config_version": 1, "curve_profile": "edhpowerlevel-2026-08", "components_profile": "v1", "sim_version": 3}


def test_unknown_profile_names_are_errors():
    with pytest.raises(ValueError, match="curve profile 'nope'"):
        load_config(curve_profile="nope")
    with pytest.raises(ValueError, match="components profile 'nope'"):
        load_config(components_profile="nope")


def test_weights_must_sum_to_one():
    from edhpower.config import _components_from
    raw = {"parts": {n: {"cap": 1, "weight": 0.5} for n in COMPONENT_NAMES}, "archetype": {}}
    with pytest.raises(ValueError, match="weights sum"):
        _components_from("bad", raw)


def _full_components_raw() -> dict:
    return {
        "parts": {n: {"cap": 1, "weight": 1 / len(COMPONENT_NAMES)} for n in COMPONENT_NAMES},
        "combo_two_card_value": 1.0,
        "combo_other_value": 0.5,
        "curve_avg_mv_best": 2.0,
        "curve_avg_mv_worst": 4.5,
        "curve_ramp_cap": 12,
        "curve_ramp_share": 0.4,
        "archetype": {},
    }


def _full_curve_raw() -> dict:
    return {
        "source": "test",
        "land": 0.6,
        "reserved": 0.2,
        "favor_price": 0.25,
        "power_curve": [0, 1],
        "pop_curve": [0, 1],
        "price_curve": [0, 1],
        "bracket_curve": [0, 1],
        "cmc_floor": 1.75,
        "cmc_ceiling": 6,
        "efficiency_limits": [0.65, 1.1],
        "basic_land_impact": 2,
        "tipping_share": 0.65,
    }


def test_components_profile_missing_scalar_raises():
    from edhpower.config import _components_from
    raw = _full_components_raw()
    del raw["curve_ramp_share"]
    with pytest.raises(KeyError):
        _components_from("bad", raw)


def test_components_profile_missing_archetype_raises():
    from edhpower.config import _components_from
    raw = _full_components_raw()
    del raw["archetype"]
    with pytest.raises(KeyError):
        _components_from("bad", raw)


def test_components_profile_missing_part_raises():
    from edhpower.config import _components_from
    raw = _full_components_raw()
    del raw["parts"][COMPONENT_NAMES[0]]
    with pytest.raises(ValueError, match="lacks parts"):
        _components_from("bad", raw)


def test_curve_profile_missing_source_raises():
    from edhpower.config import _curve_from
    raw = _full_curve_raw()
    del raw["source"]
    with pytest.raises(KeyError):
        _curve_from("bad", raw)


def test_sim_and_narrative_sections_load_with_required_reads():
    cfg = load_config()
    s = cfg.sim
    assert s.version == 3 and s.iterations == 20000 and s.max_turn == 12
    assert s.opening_hand == 7 and (s.mulligan_min_lands, s.mulligan_max_lands) == (2, 5)
    assert s.mana_threshold == 7 and s.threat_mv == 7 and s.life_per_opponent == 40 and s.opponents == 3
    assert s.metalcraft_count == 3 and s.max_two_card_lines == 8 and s.max_three_card_lines == 6
    assert "infinite damage" in s.lethal_features and all(f == f.lower() for f in s.lethal_features)
    n = cfg.narrative
    assert n.lowest_components == 2 and n.scorer_gap == 2.0 and n.idle_share == 0.25
    assert cfg.stamp() == {"config_version": 1, "curve_profile": "edhpowerlevel-2026-08", "components_profile": "v1", "sim_version": 3}


def test_config_sim_v3_fields():
    cfg = load_config()
    assert cfg.sim.version == 3 and cfg.sim.life_per_opponent == 40 and cfg.sim.opponents == 3
    assert not hasattr(cfg.sim, "lethal_damage")
    assert cfg.narrative.unmodelled_share == 0.25


def test_missing_sim_key_raises(monkeypatch, tmp_path):
    import tomllib
    from importlib import resources
    raw = tomllib.loads(resources.files("edhpower.data").joinpath("scoring.toml").read_text(encoding="utf-8"))
    del raw["sim"]["life_per_opponent"]
    from edhpower import config as config_mod
    with pytest.raises(KeyError):
        config_mod._sim_from(raw["sim"])


def test_sim_payoffs_block_loads_and_compiles():
    import re
    s = load_config().sim
    names = [r for r, _ in s.payoff_resources]
    assert names == ["mana", "death", "etb", "tokens", "counters", "storm", "draw", "self_mill", "landfall", "lifegain"]
    assert all(isinstance(p, re.Pattern) for _, p in s.payoff_resources)
    assert s.payoff_converts["mana"] == ("mana_sink",)
    assert s.payoff_converts["tokens"] == ("go_wide", "etb_damage", "token_drain")
    assert s.payoff_converts["landfall"] == ("landfall_payoff", "landfall_tokens")
    assert s.payoff_chained == {"landfall_tokens": ("go_wide", "token_drain", "etb_damage")}
    assert s.payoff_hand_ok == frozenset({"mana"})
    assert s.lock_only.match("Prevent all damage that would be dealt to you")
    assert s.lock_only.match("Lock") and not s.lock_only.match("Infinite colorless mana")
    assert s.payoff_resources[0][1].search("infinite colorless mana")


def test_bad_payoff_pattern_raises_value_error():
    import tomllib
    from importlib import resources
    from edhpower import config as config_mod
    raw = tomllib.loads(resources.files("edhpower.data").joinpath("scoring.toml").read_text(encoding="utf-8"))
    raw["sim"]["payoffs"]["resources"][0]["pattern"] = "infinite (mana"
    with pytest.raises(ValueError, match="payoff pattern"):
        config_mod._sim_from(raw["sim"])


def test_convert_target_must_be_a_known_category_name():
    import tomllib
    from importlib import resources
    from edhpower import config as config_mod
    raw = tomllib.loads(resources.files("edhpower.data").joinpath("scoring.toml").read_text(encoding="utf-8"))
    raw["sim"]["payoffs"]["converts"]["mana"] = ["mana_sinkk"]
    with pytest.raises(ValueError, match="unknown payoff category"):
        config_mod._sim_from(raw["sim"])


def test_forge_config_pinned():
    import re
    f = load_config().forge
    assert re.fullmatch(r"[0-9a-f]{40}", f.commit) and f.min_interval == 0.1


def test_config_mass_return_min_lands():
    cfg = load_config()
    assert cfg.sim.mass_return_min_lands == 4 and cfg.sim.version == 3
