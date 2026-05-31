# BECKYUP — Snapshot & Integrity

> Дата: 2026-05-31
> Статус: Черновик

## 1. Terms

| Термин | Значение |
|---|---|
| Blob | Файл на флешке, названный по sha256 содержимого |
| Snapshot / снепшот | JSON-манифест, который мапит пути файлов на их blob-хеши |
| Identity | age-ключ для подписи снепшотов |
| Store | `.beckyup/` на флешке — корень системы хранения |

## 2. Storage layout

```
<BACKUP_DRIVE>/
  .beckyup/
    verify-key        # age public key — лежит на флешке для верификации
    blobs/
      a1b2c3...       # файл, сохранённый под именем = sha256
      d4e5f6...
    snapshots/
      2026-05-31_120000.json        # manifest (plain)
      2026-05-31_120000.json.sig    # age signature
      2026-08-15_090000.json
      2026-08-15_090000.json.sig
```

Blob-хранилище content-addressed:
- Имя файла = hex-строка sha256 его содержимого
- Если два снепшота ссылаются на один blob — физически файл один
- Блобы никогда не удаляются (append-only storage)

## 3. Snapshot manifest

```json
{
  "version": 1,
  "created_at": "2026-08-15T09:00:00+03:00",
  "source_paths": ["/Users/alex/Projects"],
  "files": {
    "Projects/foo.py": {
      "sha256": "a1b2c3d4e5f6...",
      "size": 1234,
      "mtime_source": "2026-08-14T18:30:00+03:00"
    },
    "Projects/bar.txt": {
      "sha256": "f6g7h8i9j0...",
      "size": 567,
      "mtime_source": "2026-08-15T08:00:00+03:00"
    }
  },
  "signature": "age1...encrypted_base64..."
}
```

- `files` — плоский словарь относительных путей → метаданные
- `signature` — age-signature всего manifest
- Подпись верифицируется публичным ключом из `.beckyup/identity`

## 4. Identity management

При первом запуске `beckyup backup`:
1. Если `.beckyup/verify-key` не существует → генерируется age-ключ (`age-keygen`)
2. Публичный ключ (age1...) сохраняется в `.beckyup/verify-key` на флешке
3. Приватный ключ (AGE-SECRET-KEY-...) сохраняется в `~/.config/backup_tool/sign-key` (только на ПК)

Верификация подписи:
- Открытым ключом с флешки (`.beckyup/verify-key`)
- Если приватного ключа нет на ПК — новые снепшоты подписать нельзя, но существующие — верифицировать можно

## 5. CLI design

### beckyup backup
Новый снепшот + dedup-копирование.

Когда флешка знакомая (UUID в whitelist) и бэкап запущен:
1. Просканировать source-директории
2. Для каждого файла: sha256 → проверить, есть ли blob на флешке
3. Если есть — скип; если нет — скопировать в blobs/
4. Записать манифест в snapshots/
5. Подписать манифест age-ключом

### beckyup snapshots
Интерактивно через questionary:

```
=== Снепшоты на BACKUP (SanDisk Extreme) ===
#    Дата                Файлов    Размер данных
1    2026-05-31 12:00    1 234     45.2 MB
2    2026-08-15 09:00    1 567     12.8 MB
3    2027-02-10 18:30    2 001     8.3 MB
[D] Diff    [R] Restore    [V] Verify    [Q] Выход
```

### beckyup restore
1. Выбор диска (если несколько знакомых)
2. Выбор снепшота из списка
3. Выбор директории для восстановления (по умолчанию оригинал)
4. Распаковка: прочитать манифест → для каждого файла прочитать blob → скопировать по пути

### beckyup diff
1. Выбор диска
2. Выбор снепшота A из списка
3. Выбор снепшота B из списка
4. Вывод таблицы:

```
=== Changes from 2026-05-31 → 2026-08-15 ===
 ADDED    (12)  Projects/new_feature.py, ...
 MODIFIED (3)   Projects/foo.py, ...
 DELETED  (1)   Projects/old_script.py

=== foo.py diff ===
  a1b2c3d4 → f6g7h8i9  (sha256 изменился)
  Размер: 1234 → 1456
  Изменён: 2026-05-31 → 2026-08-14
```

### beckyup verify
1. Найти последний снепшот на диске
2. Проверить age-подпись
3. Для каждого файла из манифеста: прочитать blob, сверить sha256
4. Результат: "✓ Подпись верна, 1537/1537 файлов целы" или "✗ Ошибка: файл X повреждён"

## 6. Backup engine changes

`core/backup_engine.py`:
- `run_backup()` вместо `shutil.copy2` вызывает новый `_snapshot_backup()`
- `_snapshot_backup()`:
  - `_scan_files() → list[(relative_path, full_path, sha256, size, mtime)]`
  - `_dedup_copy(blob_store, sha256, full_path) → bool` — копирует только если blob нет
  - `_write_manifest(snapshots_dir, files, identity) → (manifest_path, sig_path)`
  - `_sign_manifest(manifest_str, identity_key) → str`

Новый модуль `core/snapshot.py`:
- `SnapshotManager(backup_path)` — загружает/пишет снепшоты
- `list_snapshots() → list[SnapshotMeta]`
- `load_snapshot(snapshot_id) → Snapshot`
- `restore(snapshot, destination)`
- `diff(snapshot_a, snapshot_b) → DiffResult`
- `verify(snapshot) → bool`

## 7. Integrity verification flow

```
backup:
  sha256(file) → write blob → add to manifest
  manifest.json → age sign → manifest.json + manifest.json.sig

verify:
  age verify(manifest.json, manifest.json.sig, identity) → check
  for each file in manifest:
    read blob → sha256 == manifest.sha256?
    if mismatch → CORRUPTED
```

## 8. Out of scope

- Шифрование blobs (на дороге — поверх этой архитектуры)
- Tray-иконка / notifier
- Авто-очистка старых снепшотов (сначала надо накопить историю)
- Windows-specific: age подпись через WSL или встроенный age.exe
- GC мёртвых blobs (ни один снепшот не ссылается) — опасная операция, потом

## 9. Dependencies

Обязательные: `age` (CLI), `hashlib` (встроенный)

Опциональные: `pyrage` (Python bindings для age, без внешнего CLI)

`requirements.txt`:
```
questionary>=2.0,<3.0
rich>=15.0,<16.0
bcrypt>=5.0,<6.0
pyrage>=1.2,<2.0       # age signing — опционально
```

## 10. Testing

- `test_snapshot_manager.py`:
  - Создание манифеста из списка файлов
  - Загрузка и парсинг манифеста
  - Dedup: второй проход не копирует уже существующие blobs
  - Diff: added / modified / deleted
  - Verify: корректный манифест проходит, повреждённый — нет
  - Age-подпись: stub на `subprocess.run(["age", ...])`
