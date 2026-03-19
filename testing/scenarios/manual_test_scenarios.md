dblCheck — Manual Test Scenarios
=================================

Purpose: live-lab validation of the full dblCheck pipeline against real faults.
These tests are complementary to the automated suite, which covers unit, integration,
and guardrail testing. Run these by hand against a running Containerlab topology.

Prerequisites
-------------
- Containerlab topology is up, all 16 devices reachable over SSH
- dblCheck installed and configured (NETBOX_URL, vault or env creds)
- Jira configured: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
- Dashboard running (optional but recommended for SC-1 through SC-4)

Jira Logging Convention
-----------------------
Each scenario gets its own Jira ticket as a test record:
  Summary: [dblCheck-QA] SC-X: <scenario name>
  Labels:  dblcheck, manual-qa
  Priority: Medium

After running the scenario, add a comment to the ticket:
  PASS or FAIL
  Observed output (paste relevant terminal lines or note dashboard state)
  Any unexpected behavior

This is separate from the incident ticket dblCheck creates automatically.

Entry format
------------
  Setup:    what to configure or break in the lab
  Run:      the command to execute
  Check:    what to verify (output, dashboard, auto-created Jira incident)
  Jira:     expected Jira incident outcome for this run
  Restore:  how to undo the fault before the next scenario


SC-1: Interface down and cascade
---------------------------------
  Setup:    Shut the C1J-to-C2A link on both sides (interface admin down).

  Run:      dblcheck --once

  Check:    - Terminal output shows INTERFACE_UP failures for C1J and C2A on that link.
            - OSPF_NEIGHBOR failures appear on the same link (cascade from interface).
            - Dashboard shows all failures; AI diagnosis section groups them under
              one root cause ("interface admin-down") rather than diagnosing each
              OSPF failure independently.
            - incident.json is written with a jira_issue_key and a fingerprint.

  Jira:     New incident ticket auto-created by dblCheck. Summary should read:
              "dblCheck: N assertion failures — C1J, C2A"
            Body contains the AI diagnosis text. Confirm the ticket appears in Jira
            with labels "dblcheck" and "automated" and priority High.

  Restore:  Bring the C1J-C2A interface back up on both sides.
            Run dblcheck --once again to confirm all assertions pass and Jira
            receives a resolution comment ("All dblCheck assertions now pass").
            incident.json should be deleted after the clean run.


SC-2: OSPF stuck adjacency (authentication mismatch)
------------------------------------------------------
  Setup:    Add OSPF MD5 authentication on D1C's interface toward C1J only:
              ip ospf authentication message-digest
              ip ospf message-digest-key 1 md5 SECRET
            Leave C1J's side with no authentication configured.
            This causes D1C to drop C1J's unauthenticated hellos; C1J receives
            authenticated hellos it cannot validate. The adjacency stalls in INIT
            rather than going fully down.

  Run:      dblcheck --once

  Check:    - OSPF_NEIGHBOR failure for D1C/C1J shows state INIT (not DOWN or FULL).
            - Dashboard shows the failure on both devices.
            - AI diagnosis queries OSPF state on both D1C and C1J, identifies the
              one-sided auth config as the cause.

  Jira:     New incident ticket (or comment on existing if a ticket is already open).
            Body should reference both D1C and C1J and describe the authentication
            mismatch. Confirm diagnosis does not misattribute the fault to C1J as
            the "broken" side (CLAUDE.md: INIT means the problem is on the remote
            side — check its OSPF interface config).

  Restore:  Remove the authentication config from D1C's interface.


SC-3: BGP session failure (AS number mismatch)
-----------------------------------------------
  Setup:    On E1C, change the remote-as for the BGP neighbor toward IAN to an
            incorrect AS number (e.g. change 4040 to 9999).

  Run:      dblcheck --once

  Check:    - BGP_SESSION failure on E1C toward IAN; session shows Active state.
            - Dashboard shows E1C and IAN as affected.
            - AI diagnosis queries BGP state on both E1C and IAN, identifies the
              AS number mismatch (E1C configured 9999, IAN expects 4040 or vice versa).

  Jira:     New incident ticket naming both E1C and IAN in the summary.
            Diagnosis body identifies the specific AS numbers that conflict.

  Restore:  Restore the correct remote-as on E1C.


SC-4: EIGRP neighbor lost (AS number mismatch)
------------------------------------------------
  Setup:    On B2C, change the EIGRP autonomous system number to a value that does
            not match B1C (e.g. change AS 10 to AS 99).

  Run:      dblcheck --once

  Check:    - EIGRP_NEIGHBOR failure on both B1C (missing B2C) and B2C (missing B1C).
            - AI diagnosis queries EIGRP state on both devices, identifies the
              AS mismatch as the cause.
            - No interface failure should appear — the interface between B1C and B2C
              is still up.

  Jira:     New incident ticket listing B1C and B2C. Diagnosis body identifies the
            EIGRP AS mismatch.

  Restore:  Restore the correct EIGRP AS number on B2C.


SC-5: Jira incident ticket lifecycle
--------------------------------------
  This scenario walks through the full lifecycle of a dblCheck incident ticket:
  creation, fingerprint caching, updates on changed failures, and resolution.
  Use SC-1 (C1J-C2A link down) as the base fault.

  Step a — Initial failure, ticket created:
    Setup:  Shut C1J-C2A link.
    Run:    dblcheck --once
    Check:  New Jira ticket created. incident.json written with jira_issue_key
            and fingerprint. Note the issue key.

  Step b — Same failures, no Jira activity:
    Run:    dblcheck --once (no change to the topology)
    Check:  Terminal prints "Failures unchanged since last run — diagnosis skipped."
            No new Jira ticket. No new comment on the existing ticket.
            incident.json fingerprint unchanged.

  Step c — Add a related fault (fingerprint changes):
    Setup:  Also shut the D1C-C1J link (additional interface down).
    Run:    dblcheck --once
    Check:  Fingerprint changes (more failures). dblCheck re-diagnoses and adds a
            COMMENT to the SAME Jira ticket (not a new ticket). Comment includes
            updated failure count and new diagnosis covering both links.

  Step d — Add an unrelated fault (different protocol area):
    Setup:  Additionally break BGP on E1C (wrong remote-as, as in SC-3).
    Run:    dblcheck --once
    Check:  Fingerprint changes again. Another comment added to the SAME Jira ticket.
            Comment covers both the interface failures and the BGP failure.

  Step e — Partial fix (some failures remain):
    Setup:  Restore C1J-C2A link; leave D1C-C1J down and BGP broken.
    Run:    dblcheck --once
    Check:  Fingerprint changes (fewer failures). Comment added to SAME Jira ticket
            with reduced failure set diagnosis.

  Step f — All clear:
    Setup:  Restore all faults (D1C-C1J link up, BGP fixed on E1C).
    Run:    dblcheck --once
    Check:  All assertions pass. Jira receives a resolution comment on the SAME ticket:
              "All dblCheck assertions now pass. Failures resolved at <timestamp>."
            incident.json is deleted.
            On the next run with no failures, no further Jira activity occurs.

  Jira (per step):
    a — ticket created with issue key NET-XXX (or your project prefix)
    b — no Jira activity
    c — comment added to NET-XXX (related failure expansion)
    d — comment added to NET-XXX (unrelated failure added)
    e — comment added to NET-XXX (partial resolution)
    f — resolution comment added to NET-XXX; ticket can be closed manually
