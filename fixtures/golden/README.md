# Golden snapshots

These files pin what the domain produces, byte for byte. Each scenario file is a fixed sequence of steps, with fixed timestamps and ids, and a snapshot after every step:

- the stored file;
- the validation notes;
- the current Markdown and JSON exports;
- the changes since the last review.

`validation.json` holds stored projects and model outputs, each with the outcome validation must produce.

Two tests read them. `apps/api/tests/domain/test_goldens.py` replays every scenario and compares every snapshot exactly. `apps/api/tests/adapters/test_persistence.py` loads each scenario's final stored file, and checks that it saves and exports exactly as written.

## Updating

A failing snapshot test means that stored records, exports, or validation changed. If the change is intended, regenerate the snapshots from `apps/api`, then review the diff before you commit it:

```sh
uv run --frozen python -m tests.goldens
```

The command rewrites each scenario's snapshots and each validation outcome from the current code. It keeps the steps, the descriptions, and the inputs. To add a scenario, add a file with its `name`, `description`, `steps`, and an empty `snapshots` list, then run the command.
