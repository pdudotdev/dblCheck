"""Compare assertions against collected device state → pass/fail/error."""
from validation.assertions import (
    Assertion, AssertionType, AssertionResult,
    EvaluatedAssertion, DeviceState,
)


def evaluate(
    assertions: list[Assertion],
    state: dict[str, DeviceState],
) -> list[EvaluatedAssertion]:
    """Evaluate each assertion against live device state."""
    results = []
    for a in assertions:
        ds = state.get(a.device, DeviceState(errors=["Device not in collection"]))
        results.append(_evaluate_one(a, ds))
    return results


def _evaluate_one(a: Assertion, ds: DeviceState) -> EvaluatedAssertion:
    if a.type == AssertionType.INTERFACE_UP:
        return _eval_interface(a, ds)
    if a.type == AssertionType.OSPF_NEIGHBOR:
        return _eval_ospf_neighbor(a, ds)
    if a.type == AssertionType.OSPF_ROUTER_ID:
        return _eval_ospf_router_id(a, ds)
    if a.type == AssertionType.OSPF_AREA_TYPE:
        return _eval_ospf_area_type(a, ds)
    if a.type == AssertionType.OSPF_DEFAULT_ORIG:
        return _eval_ospf_default_orig(a, ds)
    if a.type == AssertionType.BGP_SESSION:
        return _eval_bgp_session(a, ds)
    return EvaluatedAssertion(a, AssertionResult.ERROR, detail=f"Unknown assertion type: {a.type}")


# ─── Per-type evaluators ─────────────────────────────────────────────────────

def _eval_interface(a: Assertion, ds: DeviceState) -> EvaluatedAssertion:
    if ds.interfaces is None:
        return EvaluatedAssertion(a, AssertionResult.ERROR, detail=_collection_error(ds, "interfaces"))

    actual = ds.interfaces.get(a.interface)
    if actual is None:
        # Try abbreviated interface name match (e.g. "Gi2" -> "GigabitEthernet2")
        actual = _fuzzy_interface_match(a.interface, ds.interfaces)

    if actual is None:
        return EvaluatedAssertion(
            a, AssertionResult.FAIL,
            actual="not found",
            detail=f"Interface {a.interface} not found in device output",
        )
    if actual == a.expected:
        return EvaluatedAssertion(a, AssertionResult.PASS, actual=actual)
    return EvaluatedAssertion(
        a, AssertionResult.FAIL,
        actual=actual,
        detail=f"Expected {a.expected}, got {actual}",
    )


def _eval_ospf_neighbor(a: Assertion, ds: DeviceState) -> EvaluatedAssertion:
    if ds.ospf_neighbors is None:
        return EvaluatedAssertion(a, AssertionResult.ERROR, detail=_collection_error(ds, "ospf_neighbors"))

    # Match by local interface name — avoids router-id vs interface-IP ambiguity
    on_intf = [n for n in ds.ospf_neighbors
               if _interface_matches(n.get("interface", ""), a.interface)]

    if not on_intf:
        return EvaluatedAssertion(
            a, AssertionResult.FAIL,
            actual="no neighbor on interface",
            detail=f"No OSPF neighbor found on {a.interface}",
        )

    full = [n for n in on_intf if n["state"] == "FULL"]
    if full:
        return EvaluatedAssertion(a, AssertionResult.PASS, actual="FULL")

    actual_state = on_intf[0]["state"]
    return EvaluatedAssertion(
        a, AssertionResult.FAIL,
        actual=actual_state,
        detail=f"OSPF neighbor on {a.interface} is {actual_state}, expected FULL",
    )


def _eval_ospf_router_id(a: Assertion, ds: DeviceState) -> EvaluatedAssertion:
    if ds.ospf_details is None:
        return EvaluatedAssertion(a, AssertionResult.ERROR, detail=_collection_error(ds, "ospf_details"))

    actual = ds.ospf_details.get("router_id", "")
    if not actual:
        return EvaluatedAssertion(
            a, AssertionResult.FAIL,
            actual="not found",
            detail="OSPF router-id not found in device output",
        )
    if actual == a.expected:
        return EvaluatedAssertion(a, AssertionResult.PASS, actual=actual)
    return EvaluatedAssertion(
        a, AssertionResult.FAIL,
        actual=actual,
        detail=f"Expected router-id {a.expected}, got {actual}",
    )


def _eval_ospf_area_type(a: Assertion, ds: DeviceState) -> EvaluatedAssertion:
    if ds.ospf_details is None:
        return EvaluatedAssertion(a, AssertionResult.ERROR, detail=_collection_error(ds, "ospf_details"))

    areas = ds.ospf_details.get("areas", {})
    actual = areas.get(a.area)
    if actual is None:
        return EvaluatedAssertion(
            a, AssertionResult.FAIL,
            actual="not found",
            detail=f"Area {a.area} not found in OSPF details",
        )
    if actual.lower() == a.expected.lower():
        return EvaluatedAssertion(a, AssertionResult.PASS, actual=actual)
    return EvaluatedAssertion(
        a, AssertionResult.FAIL,
        actual=actual,
        detail=f"Area {a.area} type is {actual}, expected {a.expected}",
    )


def _eval_ospf_default_orig(a: Assertion, ds: DeviceState) -> EvaluatedAssertion:
    if ds.ospf_details is None:
        return EvaluatedAssertion(a, AssertionResult.ERROR, detail=_collection_error(ds, "ospf_details"))

    actual = ds.ospf_details.get("default_originate", False)
    if actual:
        return EvaluatedAssertion(a, AssertionResult.PASS, actual=True)
    return EvaluatedAssertion(
        a, AssertionResult.FAIL,
        actual=False,
        detail="default-information originate not found in OSPF config",
    )


def _eval_bgp_session(a: Assertion, ds: DeviceState) -> EvaluatedAssertion:
    if ds.bgp_summary is None:
        return EvaluatedAssertion(a, AssertionResult.ERROR, detail=_collection_error(ds, "bgp_summary"))

    match = next((n for n in ds.bgp_summary if n.get("neighbor_ip") == a.neighbor_ip), None)
    if match is None:
        return EvaluatedAssertion(
            a, AssertionResult.FAIL,
            actual="not found",
            detail=f"BGP neighbor {a.neighbor_ip} not found in summary",
        )
    actual_state = match.get("state", "Unknown")
    if actual_state == a.expected:
        return EvaluatedAssertion(a, AssertionResult.PASS, actual=actual_state)
    return EvaluatedAssertion(
        a, AssertionResult.FAIL,
        actual=actual_state,
        detail=f"Expected {a.expected}, got {actual_state}",
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _collection_error(ds: DeviceState, query: str) -> str:
    """Return a descriptive error message when device state is missing."""
    relevant = [e for e in ds.errors if query in e]
    if relevant:
        return relevant[0]
    if ds.errors:
        return ds.errors[0]
    return f"{query} data not collected"


def _interface_matches(actual_name: str, expected_name: str) -> bool:
    """Match interface names, handling abbreviation differences.

    e.g. "GigabitEthernet2" matches "Gi2", "Ethernet1/3" matches "Et1/3"
    """
    if actual_name == expected_name:
        return True
    # Normalize: lowercase, remove spaces
    a = actual_name.lower().replace(" ", "")
    e = expected_name.lower().replace(" ", "")
    if a == e:
        return True
    # Try abbreviated match: take the number suffix and compare
    a_num = "".join(c for c in a if c.isdigit() or c == "/")
    e_num = "".join(c for c in e if c.isdigit() or c == "/")
    if a_num and e_num and a_num == e_num:
        # Also check that the first letter(s) of the type match
        a_prefix = a[:2]
        e_prefix = e[:2]
        return a_prefix == e_prefix
    return False


def _fuzzy_interface_match(expected: str, interfaces: dict[str, str]) -> str | None:
    """Try to find an interface in the dict that matches the expected name."""
    for intf_name in interfaces:
        if _interface_matches(intf_name, expected):
            return interfaces[intf_name]
    return None
