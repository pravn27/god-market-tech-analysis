# Documentation map

This documentation is the source of truth for the local-only God Market Technical Analysis system.

| Area | Purpose |
| --- | --- |
| `product/` | User problem, scope, workflows, and feature catalogue |
| `architecture/` | System boundaries, components, interfaces, and decisions |
| `specifications/` | Testable behaviour for rules, dashboard, and alerts |
| `validation/` | Acceptance criteria, tests, and chart-verification evidence |
| `operations/` | Local installation, connection health, recovery, and privacy |
| `knowledge-base/` | Stable trading-method definitions used by the specifications |
| `delivery/` | GitHub Issues/Projects workflow and release evidence |

Start major features from the [product delivery roadmap](product/delivery-roadmap.md). The backend boundaries for every later epic are defined in the [Business Logic Backend foundation](architecture/business-logic-foundation.md).

## Documentation rule

No feature moves to implementation until its specification has a defined purpose, inputs, rules, failure behaviour, acceptance criteria, and validation scenarios.
