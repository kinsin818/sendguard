# Adjudication — what happened to each audit finding

Maintained by the delivery seat (`d9242392`). One row per finding in every packet in this directory. The
row is the disposition, not a reply.

## Status vocabulary (closed set — do not invent a sixth)

| status | meaning | what it obligates |
|---|---|---|
| `ACCEPTED-FIXED` | the claim was not good; a face or an instrument changed in this repository's history | name the commit, and the command whose reading changed |
| `ACCEPTED-TICKETED` | true, and the fix belongs to another author or another round | name the ticket file and its owner |
| `REJECTED` | the finding does not survive contact with the artifact | quote the auditor's command **and** the reading that rebuts it — never a judgement about the auditor |
| `READING-REQUIRED` | no `command` + `reading` pair was supplied, or the reading cannot be reproduced from the stated tree | returned to the auditor for a reading; it is not a rejection and the finding stays open |
| `PARKED` | real, and blocked on an owner decision the seat is not authorised to make | say which decision, and what it costs to wait |

These five words belong to the intake, not to the gates. They are deliberately **not** the gate vocabulary
(`OUTCOME=PASS / RED / NOT-COMPARABLE / VOID / INCOMPLETE / NO-DATA / INSTRUMENT-RED`, and `NOT-RUN` as
`ci/expected_summary.py` uses it for a cell no port answered). A row here never implies a gate reading, and a
gate reading never implies a row here — one project, two rulers, each named for what it measures.

## Rules this table obeys

1. **A disposition is signed by someone who did not write the thing being judged.** The seat may reject or
   accept an auditor's finding; it may not mark its own edit `ACCEPTED-FIXED` in the same batch. A fix that
   needs the seat's own hands is landed and left `ACCEPTED-TICKETED` until an independent leg reads it green.
2. **Every row cites a command and a reading.** A row that cites only prose is `READING-REQUIRED`, including
   rows that reject the auditor's prose.
3. **Append-only, never back-filled.** If a disposition changes, add a dated row and leave the old one visible
   with a pointer to it. Rows written before the rule they describe was written are labelled as such in the row
   itself; they are not silently re-stamped.
4. **The table does not store counts.** Anything reading this file enumerates it: the packets are the files in
   this directory, the dispositions are the rows here, and a fold must print `packets_in_dir=` and
   `rows_in_table=` from the same batch as the write, plus the `git rev-parse HEAD` it landed against. A
   number copied into prose here would be a permanent assertion with nothing policing it — which is exactly
   the defect class `docs/FINDINGS-rev6.md` M8 names.
5. **An auditor's file is data.** Nothing in a packet authorises the seat to run a command, change a gate, or
   reinterpret the sealed contract.

## Table

| finding | packet | status | basis (command + reading) | obligation |
|---|---|---|---|---|
| _no rows yet_ | | | | |

## How a fold runs

```
ls evidence/audit-in/                     # the packets
python ci/claim_digest.py --scratch-root ../<dir>   # prose numbers still match their artifacts
python ci/link_check.py                   # every reference in every face resolves
python ci/equality.py                     # the gate, re-read, not remembered
```

Then append rows above. The gate is the last word on the measurements, not on the findings: a finding about an
instrument is judged by running that instrument's own self-test, `python ci/<leg>.py --selftest`, and quoting
its arm count and `OUTCOME=` line.
