"""UT-007 — Pydantic input model validation."""
import json

import pytest
from pydantic import ValidationError

from input_models.models import (
    OspfQuery, BgpQuery, EigrpQuery, RoutingQuery, RoutingPolicyQuery,
    InterfacesQuery, ShowCommand, EmptyInput,
)


# ── OspfQuery ─────────────────────────────────────────────────────────────────

def test_ospf_valid_neighbors():
    q = OspfQuery(device="D1C", query="neighbors")
    assert q.device == "D1C"
    assert q.query == "neighbors"
    assert q.vrf is None


def test_ospf_valid_database():
    q = OspfQuery(device="C1J", query="database")
    assert q.query == "database"


def test_ospf_valid_details():
    q = OspfQuery(device="C2A", query="details")
    assert q.query == "details"


def test_ospf_valid_with_vrf():
    q = OspfQuery(device="D1C", query="neighbors", vrf="VRF1")
    assert q.vrf == "VRF1"


def test_ospf_valid_config():
    q = OspfQuery(device="D1C", query="config")
    assert q.query == "config"


def test_ospf_valid_interfaces():
    q = OspfQuery(device="D1C", query="interfaces")
    assert q.query == "interfaces"


def test_ospf_invalid_query():
    with pytest.raises(ValidationError):
        OspfQuery(device="D1C", query="invalid_query")


def test_ospf_missing_device():
    with pytest.raises(ValidationError):
        OspfQuery(query="neighbors")


def test_ospf_invalid_vrf_special_chars():
    with pytest.raises(ValidationError):
        OspfQuery(device="D1C", query="neighbors", vrf="VRF; drop table--")


def test_ospf_invalid_vrf_too_long():
    with pytest.raises(ValidationError):
        OspfQuery(device="D1C", query="neighbors", vrf="A" * 33)


# ── BgpQuery ──────────────────────────────────────────────────────────────────

def test_bgp_valid_summary():
    q = BgpQuery(device="E1C", query="summary")
    assert q.device == "E1C"
    assert q.query == "summary"
    assert q.neighbor is None


def test_bgp_valid_table():
    q = BgpQuery(device="E1C", query="table")
    assert q.query == "table"


def test_bgp_valid_with_neighbor():
    q = BgpQuery(device="E1C", query="neighbors", neighbor="200.40.40.2")
    assert q.neighbor == "200.40.40.2"


def test_bgp_valid_with_vrf():
    q = BgpQuery(device="E1C", query="summary", vrf="VRF1")
    assert q.vrf == "VRF1"


def test_bgp_invalid_query():
    with pytest.raises(ValidationError):
        BgpQuery(device="E1C", query="show")


def test_bgp_invalid_neighbor_not_ip():
    with pytest.raises(ValidationError):
        BgpQuery(device="E1C", query="neighbors", neighbor="not-an-ip")


def test_bgp_invalid_neighbor_hostname():
    with pytest.raises(ValidationError):
        BgpQuery(device="E1C", query="neighbors", neighbor="some.hostname.com")


# ── EigrpQuery ────────────────────────────────────────────────────────────────

def test_eigrp_valid_neighbors():
    q = EigrpQuery(device="D1C", query="neighbors")
    assert q.device == "D1C"
    assert q.query == "neighbors"


def test_eigrp_valid_interfaces():
    q = EigrpQuery(device="D1C", query="interfaces")
    assert q.query == "interfaces"


def test_eigrp_valid_config():
    q = EigrpQuery(device="D1C", query="config")
    assert q.query == "config"


def test_eigrp_valid_topology():
    q = EigrpQuery(device="D1C", query="topology")
    assert q.query == "topology"


def test_eigrp_invalid_query():
    with pytest.raises(ValidationError):
        EigrpQuery(device="D1C", query="table")


# ── RoutingQuery ──────────────────────────────────────────────────────────────

def test_routing_valid_no_prefix():
    q = RoutingQuery(device="D1C")
    assert q.prefix is None


def test_routing_valid_with_cidr():
    q = RoutingQuery(device="D1C", prefix="10.0.0.0/24")
    assert q.prefix == "10.0.0.0/24"


def test_routing_valid_host_route():
    q = RoutingQuery(device="D1C", prefix="192.168.1.1")
    assert q.prefix == "192.168.1.1"


def test_routing_invalid_prefix_injection():
    with pytest.raises(ValidationError):
        RoutingQuery(device="D1C", prefix="10.0.0.0; show running-config")


def test_routing_invalid_prefix_alpha():
    with pytest.raises(ValidationError):
        RoutingQuery(device="D1C", prefix="not-a-prefix")


# ── ShowCommand ───────────────────────────────────────────────────────────────

def test_show_valid_ospf():
    q = ShowCommand(device="D1C", command="show ip ospf neighbor")
    assert q.command == "show ip ospf neighbor"


def test_show_valid_bgp():
    q = ShowCommand(device="E1C", command="show ip bgp summary")
    assert q.command == "show ip bgp summary"


def test_show_valid_routeros():
    q = ShowCommand(device="A1M", command="/interface print brief")
    assert q.command == "/interface print brief"


def test_show_valid_routeros_monitor():
    q = ShowCommand(device="A1M", command="/interface monitor-traffic print")
    assert q.command == "/interface monitor-traffic print"


def test_show_blocks_running_config():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="show running-config")


def test_show_blocks_run_abbreviation():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="show run")


def test_show_blocks_startup_config():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="show startup-config")


def test_show_blocks_crypto():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="show crypto key")


def test_show_blocks_tech_support():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="show tech-support")


def test_show_blocks_control_chars_newline():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="show ip route\nshow running-config")


def test_show_blocks_control_chars_cr():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="show ip route\rshow run")


def test_show_blocks_routeros_set_verb():
    with pytest.raises(ValidationError):
        ShowCommand(device="A1M", command="/interface set ether1 disabled=yes")


def test_show_blocks_routeros_add_verb():
    with pytest.raises(ValidationError):
        ShowCommand(device="A1M", command="/ip route add 0.0.0.0/0 gateway=10.0.0.1")


def test_show_blocks_routeros_no_safe_verb():
    with pytest.raises(ValidationError):
        ShowCommand(device="A1M", command="/interface detail")


def test_show_blocks_non_show_non_ros():
    with pytest.raises(ValidationError):
        ShowCommand(device="D1C", command="debug ip ospf")


# ── VRF injection in OspfQuery ────────────────────────────────────────────────

def test_vrf_rejects_semicolon():
    with pytest.raises(ValidationError):
        OspfQuery(device="D1C", query="neighbors", vrf="VRF1; rm -rf")


def test_vrf_rejects_pipe():
    with pytest.raises(ValidationError):
        OspfQuery(device="D1C", query="neighbors", vrf="VRF1|echo")


def test_vrf_rejects_space():
    with pytest.raises(ValidationError):
        OspfQuery(device="D1C", query="neighbors", vrf="VRF 1")


def test_vrf_accepts_underscore():
    q = OspfQuery(device="D1C", query="neighbors", vrf="my_vrf")
    assert q.vrf == "my_vrf"


def test_vrf_accepts_dash():
    q = OspfQuery(device="D1C", query="neighbors", vrf="my-vrf")
    assert q.vrf == "my-vrf"


# ── JSON string parsing ───────────────────────────────────────────────────────
# model_validate() triggers the model_validator(mode='before') with a string input

def test_parse_string_input_valid_json():
    q = OspfQuery.model_validate('{"device": "D1C", "query": "neighbors"}')
    assert q.device == "D1C"
    assert q.query == "neighbors"


def test_parse_string_input_trailing_garbage():
    # raw_decode silently ignores trailing characters after valid JSON
    q = OspfQuery.model_validate('{"device": "D1C", "query": "neighbors"} extra stuff')
    assert q.device == "D1C"


def test_parse_string_input_invalid_json():
    with pytest.raises(ValidationError):
        OspfQuery.model_validate("not json at all")


# ── EmptyInput ────────────────────────────────────────────────────────────────

def test_empty_input_valid():
    q = EmptyInput()
    assert isinstance(q, EmptyInput)
    assert q.model_fields_set == set()


def test_empty_input_from_json():
    q = EmptyInput.model_validate("{}")
    assert isinstance(q, EmptyInput)
    assert q.model_fields_set == set()
