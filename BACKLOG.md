# Backlog

Working queue. The next unchecked item is the one being built. An item stays
unchecked and picks up a `status:` note if it spans more than one working
session — finishing something half-built takes priority over starting the next
one.

Rules of thumb applied to every item:

- one job per tool, done properly, rather than a suite of half-features
- standard library unless a dependency earns its place
- tests that assert a real property, not that the code ran
- a README that says what the tool is *not* for
- any published factor, threshold or rate gets a citation and a vintage

---

## Done

- [x] **001 — market-sizer** · Top-down and bottom-up sizing side by side with a closed-form inversion: for each assumption, the value that would make the two agree, and an explicit infeasible verdict where no value can. Provenance is mandatory; staleness is reported. 49 tests.

## Queue

- [ ] **002 — dcf-lab** · Driver-based DCF with a WACC build-up, Gordon and exit-multiple terminal values, and a sensitivity grid that shows how little of the answer comes from the forecast period.
- [ ] **003 — scenario-engine** · Scenarios as named parameter overlays over a base model: run them all, report the spread rather than a point estimate.
- [ ] **004 — tidy-export** · Turn a messy spreadsheet export — merged headers, repeated labels, footnote rows — into a tidy table, and report what it had to discard.
- [ ] **005 — peer-benchmark** · Peer comparison tables with normalisation, outlier handling, and quartiles that state their own sample size.
- [ ] **006 — cohort-retention** · Cohort tables and retention curves from a transaction log, with the survivorship traps flagged rather than hidden.
- [ ] **007 — tornado** · One-at-a-time sensitivity and tornado ordering over any model function, including the interactions the method cannot see.
- [ ] **008 — waterfall** · Bridge charts from any two-period dataset with the arithmetic checked rather than hand-typed.
- [ ] **009 — assumption-log** · Extract hardcoded numbers from a model, register them with a source and a review date, and report which have gone stale.
- [ ] **010 — survey-weights** · Post-stratification and raking, reporting design effect and effective sample size so nobody quotes a margin of error that does not exist.
- [ ] **011 — benford-check** · Screen a set of reported figures against Benford's law and flag what deserves a second look, with an honest note on the method's false-positive rate. Moved here from `esg-toolkit`, whose queue it predated: the method is general analysis rather than anything to do with emissions.
