dblCheck — Manual Test Scenarios
=================================

Purpose: live-lab validation of the full dblCheck pipeline against real faults.
These tests are complementary to the automated suite, which covers unit, integration,
and guardrail testing. Run these by hand against a running Containerlab topology.

Prerequisites
-------------
- Containerlab topology is up, all 16 devices reachable over SSH
- dblCheck daemon installed and running:
    sudo deploy/install.sh        # first-time setup
    systemctl status dblcheck     # verify running
- Dashboard open in browser: http://localhost:5556
  (add ?token=<value> if DASHBOARD_TOKEN is configured)
- For testing, use a short poll interval so faults are caught quickly:
    set INTERVAL=30 in .env, then: systemctl restart dblcheck
- Jira configured: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY

Jira Logging Convention
-----------------------
Each scenario gets its own QA ticket as a test record (separate from the
incident ticket dblCheck creates automatically):
  Summary: [dblCheck-QA] SC-X: <scenario name>
  Labels:  dblcheck, manual-qa
  Priority: Medium

After running the scenario, add a comment to the QA ticket:
  PASS or FAIL
  Observed dashboard state and diagnosis output
  Any unexpected behavior

Entry format
------------
  Setup:    what to configure or break on the device
  Observe:  dashboard state transitions to watch for
  Check:    what to verify in the validation table, diagnosis panel, and tool calls panel
  Jira:     expected incident ticket outcome
  Restore:  how to undo the fault; what the next validation cycle should show


SC-a: Cisco IOS-XE — EIGRP AS mismatch
----------------------------------------
  Setup:    On B2C, change the EIGRP autonomous system number to a value that
            does not match B1C:
              no router eigrp 10
              router eigrp 99
              network <B2C network>  (re-add the same network statements)

  Observe:  Dashboard status dot turns yellow (Validating). After the collection
            phase completes (~10–20s), the validation table populates and the
            table collapses to a summary bar. The status dot turns blue (Diagnosing)
            as the AI agent is invoked. Tool calls appear in the right panel;
            reasoning streams in the left panel. Status returns to green (Completed).

  Check:    - Validation table shows EIGRP_NEIGHBOR failures for both B1C (B2C
              missing from neighbor table) and B2C (B1C missing).
            - No INTERFACE_UP failures — the physical link B1C:Eth0/2 ↔ B2C:Eth0/2
              is still up.
            - AI diagnosis queries EIGRP on both B1C and B2C. Root cause identifies
              the AS number mismatch (B2C running AS 99, B1C expects AS 10).
            - Tool calls panel shows get_eigrp invocations for both B1C and B2C.

  Jira:     New incident ticket auto-created. Summary: "dblCheck: N assertion
            failures — B1C, B2C". Body contains the AI diagnosis. Confirm labels
            "dblcheck" and "automated" and priority High.

  Restore:  Restore the correct EIGRP AS on B2C:
              no router eigrp 99
              router eigrp 10
              network <same network statements>
            Wait for the next validation cycle. Dashboard should show all assertions
            passing. Jira ticket auto-resolved with comment:
              "✅ All dblCheck assertions now pass. Failures resolved at <timestamp>."


SC-b: Juniper JunOS — OSPF authentication mismatch
-----------------------------------------------------
  Setup:    On C1J, add OSPF MD5 authentication on the interface toward D1C only:
              set protocols ospf area 0 interface et-0/0/4 authentication
                md5 1 key SECRET
              commit
            Leave D1C's side with no authentication configured.
            C1J will send authenticated hellos; D1C, not expecting auth, will reject
            them. The adjacency stalls in INIT on D1C (receiving hellos it cannot
            validate) and eventually drops on C1J.

  Observe:  Status dot transitions yellow → blue. Tool calls panel shows the agent
            querying OSPF on both C1J (Juniper) and D1C (Cisco).

  Check:    - OSPF_NEIGHBOR failure for the C1J↔D1C pair; D1C shows C1J in INIT
              state (not FULL or DOWN).
            - Validation table shows failures on both C1J and D1C for this neighbor.
            - AI diagnosis identifies the one-sided authentication as the root cause.
              Per CLAUDE.md: INIT means hellos are received but not reciprocated —
              the agent should attribute the problem to C1J's auth config, not D1C.
            - Tool calls panel shows get_ospf queries to both devices.

  Jira:     New incident ticket naming both C1J and D1C. Diagnosis body references
            the authentication mismatch and identifies which side has the config.

  Restore:  Remove the authentication from C1J:
              delete protocols ospf area 0 interface et-0/0/4 authentication
              commit
            Wait for the next validation cycle; OSPF should return to FULL.


SC-c: Arista EOS — Interface down and OSPF cascade
----------------------------------------------------
  Setup:    On A2A, administratively shut the interface toward D2B:
              interface Ethernet2
                shutdown

  Observe:  After the validation cycle, the table shows multiple failures (interface
            and OSPF). The AI agent is invoked. Watch the reasoning panel — the
            agent should group the OSPF failures under the interface failure root
            cause rather than diagnosing each one separately.

  Check:    - INTERFACE_UP failures for A2A (Ethernet2) and D2B (1/1/3).
            - OSPF_NEIGHBOR failures for A2A↔D2B (cascaded from the interface down).
            - AI diagnosis identifies the admin-down interface as the single root cause
              for all failures, not individual OSPF diagnoses.
            - Tool calls panel shows get_interfaces (not just get_ospf) invoked first,
              confirming the agent investigated the interface layer.

  Jira:     New incident ticket listing A2A and D2B. Diagnosis body explains
            the cascade: interface down caused the OSPF adjacency loss.

  Restore:  Bring the interface back up on A2A:
              interface Ethernet2
                no shutdown
            Confirm A2A:Ethernet2 re-establishes the OSPF adjacency to D2B.


SC-d: Aruba AOS-CX — OSPF stuck in EXSTART (MTU mismatch)
-----------------------------------------------------------
  Setup:    On D2B, set a jumbo MTU on the interface toward C2A:
              interface 1/1/6
                mtu 9000
            Leave C2A:eth2 at its default MTU (1500). The MTU mismatch prevents
            OSPF Database Description packets from completing, stalling the
            adjacency in EXSTART or EXCHANGE.

  Observe:  Status dot transitions yellow → blue. The agent queries OSPF state
            on both D2B and C2A; it should also query interface details to read
            the MTU on each side.

  Check:    - OSPF_NEIGHBOR failure for D2B↔C2A with state EXSTART or EXCHANGE.
            - AI diagnosis identifies the MTU mismatch as the cause (per CLAUDE.md:
              EXSTART/EXCHANGE means check MTU on both interfaces).
            - Tool calls panel shows get_ospf and get_interfaces (or run_show for
              interface MTU) invocations on both D2B and C2A.
            - Diagnosis cites the specific MTU values observed on each side.

  Jira:     New incident ticket naming D2B and C2A. Diagnosis body cites the
            MTU values that conflict.

  Restore:  Remove the custom MTU on D2B:
              interface 1/1/6
                no mtu
            Wait for OSPF to re-establish to FULL on the D2B↔C2A link.


SC-e: MikroTik RouterOS — OSPF interface removed (link stays up)
-----------------------------------------------------------------
  Setup:    On A1M, remove ether1 from the OSPF instance (the interface toward
            D1C), but leave the physical interface admin-up:
              /routing ospf interface
              remove [find interface=ether1]
            The IP link between A1M:ether1 and D1C:Ethernet0/1 remains up;
            only OSPF stops running on it.

  Observe:  The validation table shows only OSPF failures, no interface failures.
            The AI agent is invoked. Tool calls should show OSPF queries to both
            A1M and D1C; the agent should also check interface status to rule out
            a physical problem.

  Check:    - OSPF_NEIGHBOR failures for A1M↔D1C only — no INTERFACE_UP failures.
            - Validation table shows the interface link is reported as up (PASS)
              while only the OSPF neighbor assertion fails.
            - AI diagnosis identifies that A1M has no OSPF configured on ether1
              (not a hardware failure), distinguishing it from a physical-layer issue.
            - Tool calls panel shows get_ospf and get_interfaces invocations for
              both A1M and D1C.

  Jira:     New incident ticket naming A1M and D1C. Diagnosis body notes the
            interface is operationally up but OSPF is not running on it.

  Restore:  Re-add ether1 to OSPF on A1M:
              /routing ospf interface
              add interface=ether1 area=<ospf-area>
            Wait for the OSPF adjacency to A1M↔D1C to return to FULL.


SC-f: Stop button interrupts active diagnosis
----------------------------------------------
  Setup:    Inject any fault that triggers diagnosis (e.g. SC-a or SC-c).
            Wait for the validation cycle to complete and diagnosis to begin
            (status dot turns blue, tool calls start appearing in the right panel).

  Action:   Click the Stop button in the dashboard header while tool calls
            are still in progress.

  Check:    - Dashboard status changes to "Stopping…" then returns to Idle.
            - Claude process and all MCP child processes are terminated
              (verify: ps aux | grep claude shows no orphaned processes).
            - The NEXT RUN countdown restarts automatically for the normal interval.
            - data/dashboard_state.json shows state: idle.

  Restore:  No manual restore needed. The next scheduled validation cycle
            runs automatically. If the fault is still present, diagnosis
            will be re-invoked on that cycle.


Extended: Jira Lifecycle Walkthrough
--------------------------------------
Use this walkthrough to verify fingerprint caching, comment updates, and
auto-resolution. It is not a separate vendor test — use any scenario fault as a
starting point. SC-c (A2A interface down) is recommended because its failure set
is easy to expand.

  Step a — Initial failure, ticket created:
    Inject the SC-c fault (shut A2A:Ethernet2).
    After the next validation cycle: new Jira ticket created. Note the issue key.

  Step b — Same failure set, no re-diagnosis:
    Wait for another validation cycle (no topology changes).
    Dashboard shows "Failure set unchanged — agent not invoked".
    No new Jira ticket and no new comment on the existing ticket.

  Step c — Add a second fault (new failures detected):
    Also inject the SC-a fault (EIGRP AS mismatch on B2C).
    After the next cycle: new failures are detected, agent re-diagnoses.
    A comment is added to the SAME Jira ticket — not a new ticket.
    Comment header reads: "Failure set changed — N new. K active now."
    followed by the updated diagnosis.

  Step c2 — Mixed change (new failures + some resolved simultaneously):
    Restore SC-a (correct EIGRP AS on B2C), but at the same time inject
    SC-d (MTU mismatch on D2B:1/1/6).
    After the next cycle: EIGRP failures resolved, OSPF/MTU failures are new.
    Agent re-diagnoses because new failures exist. Jira comment reads:
    "Failure set changed — N new, M resolved. K active now."
    followed by the updated diagnosis covering the new failures.

  Step d — Partial fix (subset, no re-diagnosis):
    Restore only SC-d (remove the MTU override on D2B:1/1/6). Leave any
    remaining active fault in place so at least one failure persists.
    After the next cycle: the remaining failures are a strict subset of
    the previous set — no new failures detected.
    Agent is NOT re-invoked. Dashboard shows "Failure set unchanged —
    agent not invoked (see TICKET-KEY)".
    A lightweight comment is posted to the Jira ticket:
    "N of M failure(s) now resolved. K still active."
    followed by a list of the resolved assertions.

  Step e — Full clear:
    Restore SC-a (correct EIGRP AS on B2C).
    After the next cycle: all assertions pass. Jira ticket auto-resolved with:
      "✅ All dblCheck assertions now pass. Failures resolved at <timestamp>."
    Subsequent clean runs produce no further Jira activity.
