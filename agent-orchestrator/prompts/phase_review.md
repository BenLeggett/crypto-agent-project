{task_context}

Read these files first and treat them as authoritative:
* AGENTS.md
* docs/ARCHITECTURE.md
* docs/IMPLEMENTATION_PLAN.md
* docs/TASK_QUEUE.md
* docs/PHASE_TASK_MAP.md
* docs/MANUAL_WIRING_CHECKLIST.md

We have completed the tasks mapped to the current phase.
Your job is not to implement the next task yet.
Your job is to perform a phase completion review and keep the project aligned to its intended goal:
* staged autonomous crypto trading system
* paper-trading first
* periodic operator updates through bot/chat/reporting
* future live execution only after explicit promotion and later manual wiring
* deterministic risk governor remains authoritative over hard constraints

For the current phase:
1. identify which phase is under review
2. list the tasks mapped to that phase
3. assess whether the phase deliverables from IMPLEMENTATION_PLAN.md are actually satisfied
4. assess whether the required tests for that phase exist and are sufficient
5. assess whether the acceptance criteria are truly met
6. determine whether any manual wiring is now required for honest validation:
   * none required
   * optional
   * required now
7. if manual wiring is required, list exactly:
   * what must be wired
   * why it is required now
   * what can still remain mocked
   * what should not be wired yet
8. identify any gaps, drift, or incomplete work that must be finished before the phase is considered complete
9. recommend one of:
   * phase complete, proceed
   * phase complete but do manual wiring first
   * phase not complete, finish these remaining items first

Constraints:
* do not start coding
* do not skip milestone review
* do not recommend live wiring early unless it is genuinely required
* prefer mock-mode validation unless real integration is necessary to validate the phase honestly
* keep the review concrete and tied to the docs

Return:
1. phase under review
2. completion assessment
3. manual wiring assessment
4. remaining gaps, if any
5. recommended next action
