# beckyup — Session Context

## Project
Экстренный бэкап на флешку. Python 3.12+, age CLI для подписи.

## Stack
Python, unittest, questionary (optional), rich (optional), age (external CLI)

## Active Branch
`feat/snapshots` — content-addressed snapshots с dedup + age-signing

## Branch History
main → feat/snapshots (7 commits, 49 tests, clean)

## Session 2026-05-31

### Done
- `core/snapshot.py`: identity (age-keygen), sign/verify (age encrypt/decrypt), sha256 helpers, SnapshotManager (scan→dedup→manifest→diff→restore→verify)
- `cli/snapshot_ui.py`: questionary pickers + fallback, diff display
- `core/backup_engine.py`: run_backup() → snapshot flow
- `main.py`: --snapshots, --restore, --diff, --verify, --version
- `tests/test_snapshot.py`: 25 tests, 5 classes
- Version: `v0.2.0` (pyproject.toml + `__init__.py`)

### Key Decisions
- age encrypt/decrypt вместо --sign/--verify (Go age v1.3.1 нет этих флагов)
- Манифесты именуются по timestamp с микросекундами (%Y-%m-%d_%H%M%S_%f)
- questionary опционален — fallback через input() при отсутствии
- store (ключи + blobs + manifests) на флешке, не на ПК

### Known Gaps
- .DS_Store в git — убрать
- CI нужен age CLI для тестов подписи
- spec sec 4: приватный ключ должен быть на ПК (~/.config/backup_tool/sign-key), не на флешке

### Next
- merge feat/snapshots → main (после code review)
- CI: установка age через brew/apt
- убрать .DS_Store из git
