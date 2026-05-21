# BECKYUP MVP Spec

> Дата: 2026-05-21
> Статус: Черновик

## 1. Product idea

Экстренный бэкап важных данных. Пользователь настраивает один раз (какие папки бэкапить, на какую флешку). При подключении этой флешки — бэкап запускается автоматически (или после подтверждения).

Не замена Time Machine. Это **целевой портативный снепшот**: воткнул свою флешку — получил свежую копию проектов.

## 2. User flow

```
Первый запуск:
  wizard (CLI) → выбор папок → подключить флешку → сохранить UUID → готов

Обычный запуск:
  висит в фоне → появилась знакомая флешка? → бэкап (авто/с подтверждением)
                      → чужая флешка? → игнорируем

Разовый бэкап:
  $ beckyup --source ~/Projects --destination /Volumes/FLASHKA
```

## 3. Architecture

### Components

```
main.py               — точка входа, CLI-аргументы
  ├── cli/wizard.py   — первый запуск (questionary/input)
  ├── core/
  │   ├── device_detector.py  — polling внешних дисков
  │   ├── device_monitor.py   — thread-loop, триггер бэкапа
  │   └── backup_engine.py    — копирование + проверки
  ├── config/
  │   ├── default_config.json
  │   ├── user_config.json    — сохраняется после wizard
  │   └── manager.py          — чтение/запись конфига
  └── utils/
      ├── logger.py
      └── platform.py         — helpers for OS detection
```

### device_detector — определение дисков

Интерфейс:
```python
def get_mounted_devices() -> set[(mount_path, label, uuid)]
```

Алгоритм:
1. Определить ОС (platform.py)
2. Выбрать polling-стратегию:
   - macOS: `ls /Volumes/` + `diskutil info` для UUID
   - Linux: `ls /media/<user>/` + `lsblk -o UUID`
   - Windows: `GetLogicalDrives()` + `GetVolumeInformation`
3. Отфильтровать системные:
   - macOS: исключить `/` (boot), `/System/Volumes/`, `/System/` (iOS mount)
   - Linux: исключить `/`, `/boot`, `/home`
   - Windows: исключить `C:\` (boot), `D:\` если это recovery/system reserved
   Критерий внешнего диска: не boot-диск, не системный mount
4. Получить UUID:
   - macOS: `diskutil info /Volumes/DRIVE | grep "Volume UUID"` → парсим awk
   - Linux: `lsblk -no UUID /dev/sdX1` → привязка mount point к блочному device
   - Windows: `win32api.GetVolumeInformation(path)` → volume serial number
5. Вернуть набор `(путь, метка, UUID)`

### White list UUID

UUID знакомых бэкап-дисков хранятся в `user_config.json`:
```json
{
  "backup": {
    "source_directories": ["~/Projects", "~/Desktop/__life_os"],
    "known_drive_uuids": {
      "ABC-123-DEF": "SanDisk Extreme"
    },
    "auto_confirm": false,
    "max_file_size_mb": 500
  }
}
```

Неизвестные UUID игнорируются полностью — флешка друга не триггерит бэкап.

### device_monitor — цикл мониторинга

- Отдельный поток
- Каждые N секунд (по умолчанию 5) → `device_detector.get_mounted_devices()`
- Diff с предыдущим состоянием:
  - Появился новый UUID в white list → start backup
  - Пропал UUID → очистка (опционально, лог)

### backup_engine — проверки перед копированием

Перед запуском:
1. `disk_usage(destination)` — хватает места?
2. Тестовый файл `.beckyup_healthcheck` — диск доступен для записи?
3. Если нет → ошибка пользователю, бэкап отменён

Во время копирования:
- Ловить OSError (выдернули флешку, нет места, битый сектор)
- Продолжить со следующим файлом, залогировать ошибку
- Итог: "Скопировано 12/15 файлов, 3 ошибки"

## 4. Error handling matrix

| Ситуация | Что происходит | Что видит пользователь |
|---|---|---|
| Нет места на диске | Бэкап отменён до копирования | "На диске X осталось Y ГБ, нужно Z ГБ" |
| Диск read-only | Тестовая запись падает, бэкап отменён | "Диск X доступен только для чтения" |
| Выдернули флешку | OSError при `shutil.copy2`, бэкап прерван | "Бэкап прерван. Скопировано N/M файлов" |
| Файл занят другим процессом | Пропускаем файл, логируем | "Файл X пропущен (занят другим процессом)" |
| Файл > max_file_size | Пропускаем | "Файл X пропущен (превышает лимит N МБ)" |
| Чужая флешка | UUID не в white list — игнорируем | (тишина) |

## 5. CLI interface

```
$ beckyup
  Запуск в режиме мониторинга (демон)

$ beckyup --wizard
  Принудительный запуск настройки

$ beckyup --source ~/Projects --destination /Volumes/BACKUP
  Разовый бэкап

$ beckyup --config ~/custom_config.json
  Своя конфигурация

$ beckyup --help
  Справка
```

## 6. Dependencies

Обязательные: `questionary` (CLI-формы)

Опциональные (try/except import):
- macOS: `pyobjc-framework-DiskArbitration` → native события mount/unmount
- Linux: `pyudev` → USB-события
- Windows: `pywin32` → `GetDriveType`

Все native библиотеки можно не ставить. Программа работает на polling. Native дают:
- Мгновенную реакцию на подключение (вместо задержки 5 сек)
- Точное определение removable/external

## 7. Testing

- `test_device_detector.py`:
  - Парсинг `diskutil`, `lsblk`, `GetLogicalDrives`
  - Фильтрация системных дисков
  - Формат UUID

- `test_device_monitor.py`:
  - Diff между старым и новым набором дисков
  - Триггер только для white list UUID
  - Игнорирование новых неизвестных UUID

- `test_backup_engine.py` (дополнить):
  - `disk_usage()` — достаточно места
  - `write_test()` — диск доступен для записи
  - OSError при копировании не роняет весь бэкап

## 8. Out of scope (MVP)

- GUI (Tray-иконка, уведомления)
- Шифрование
- Инкрементальные бэкапы (сейчас — честное копирование)
- Планировщик по времени (только триггер по USB)
- Сжатие
- Сетевые бэкапы (только локальные диски)
