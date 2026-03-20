# Jira Ticket Lifecycle

How dblCheck creates, updates, and resolves Jira tickets across diagnosis runs.

---

## Core principle

Every diagnosis run creates a **new ticket** with the full current failure set. There is no "update existing ticket" path — each diagnosis is a fresh, self-contained record. When an old ticket exists, dblCheck decides whether to close it or leave it open based on whether its failures are still active.

---

## State machine: `incident.json`

`data/incident.json` tracks the current incident between runs:

```json
{
  "fingerprint":    "<sha256 of sorted failure set>",
  "failure_ids":    [["DEVICE", "check_type", "expected_value"], ...],
  "failure_count":  5,
  "jira_issue_key": "SUP-42",
  "diagnosed_at":   "2026-03-20T07:38:26Z"
}
```

- **Present** → an active incident is being tracked
- **Absent** → no current incident (all assertions pass)

The fingerprint and `failure_ids` are used on the next run to detect whether the failure set changed.

---

## Decision tree per run

```
Any failures?
├── No  → All assertions pass
│         If incident.json exists → resolve ticket, delete incident.json
│
└── Yes → Compare against previous failure set (incident.json)
          │
          ├── Identical fingerprint / no new failures
          │     Diagnosis skipped
          │     If some resolved → partial resolution comment on current ticket
          │                        update incident.json (new fingerprint, new ids)
          │
          └── New failures detected → run diagnosis → _handle_incident()
                │
                ├── No existing ticket (first failure or prior creation failed)
                │     Create new ticket → write incident.json
                │
                └── Existing ticket present
                      Create new ticket
                      │
                      ├── Any old failure still in current set?
                      │   YES → Comment on old ticket: "tracked in NEW-KEY"
                      │         Old ticket stays OPEN
                      │
                      └── All old failures gone (disjoint set)?
                          NO  → Resolve old ticket: "All tracked failures resolved."
                          Write incident.json with new ticket key
```

---

## Flow reference table

| Scenario | Old ticket | New ticket |
|---|---|---|
| First failure (no incident) | n/a | Created |
| Same failures (identical) | Unchanged | Skipped |
| Failures decrease (subset) | Partial resolution comment | Skipped |
| Any old failure still present (superset or partial overlap) | Comment with pointer (stays open) | Created |
| All old failures gone (disjoint set) | Resolved — clean close | Created |
| All assertions pass | Resolved, incident.json deleted | n/a |
| Ticket creation fails | Preserved (retry next run) | n/a |

---

## Key implementation details

- **`_handle_incident()`** (`cli/dblcheck.py`): performs ticket creation and old-ticket handling
- **`_update_incident_ids()`**: syncs `incident.json` after partial resolution (no new ticket)
- **Subset detection** (`cli/dblcheck.py` lines ~442–469): runs before diagnosis; if no new failures, skips diagnosis entirely and posts a partial resolution comment if some were resolved
- **Full resolution** (`cli/dblcheck.py` lines ~504–512): runs when zero failures remain; resolves ticket and deletes `incident.json`
- **`jira_pending`**: flag set when a previous ticket creation failed (no key in `incident.json`); forces diagnosis to run even if fingerprint is unchanged, so the ticket creation is retried
- **`previous_ids`**: `set` of `(device, type, expected)` tuples loaded from `incident.json`. `None` for legacy files without `failure_ids`. When `None`, the old ticket is resolved as a safe default.
