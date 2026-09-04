---
description: "Use when editing ProgressReporter in src/crawl4md/progress.py or its tests. Covers terminal progress output and the on-disk activity log."
applyTo: "src/crawl4md/progress.py, tests/test_progress.py"
---

# ProgressReporter

Reports crawl progress to the terminal and to an on-disk activity log (CSV/TXT)
only — there is no widget or rich-display path.

## Constraints

- **Public API is a contract.** The crawler drives progress through `ProgressReporter`'s
  constructor, `set_activity`, `update_activity_label`, `update`, `finish`, and `.total`.
  Keep these names and signatures stable — changing them breaks the crawler.
- **No secrets or PII.** Activity labels and log rows must never include credentials,
  tokens, or personal data.
