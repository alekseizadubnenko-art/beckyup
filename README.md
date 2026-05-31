# BECKYUP

> Экстренный бэкап важных данных. Настроил один раз — забыл. Воткнул свою флешку — бэкап пошёл.

```
    __              __
   / /_  ___  _____/ /____  ____  ______
  / __ \/ _ \/ ___/ //_/ / / / / / / __ \
 / /_/ /  __/ /__/ ,< / /_/ / /_/ / /_/ /
/_.___/\___/\___/_/|_|\__, /\__,_/ .___/
                     /____/     /_/
```

## Features

- **Автоматический бэкап** — подключил знакомую флешку → копирование началось
- **UUID-whitelist** — чужие флешки игнорируются
- **Выбор папок** — любые директории, не только домашние
- **Фильтр типов файлов** — документы / изображения / код / архивы или свои расширения
- **Безопасность** — без пароля / системный пароль macOS / свой bcrypt-пароль
- **Автозапуск** — LaunchAgent на macOS, стартует при входе в систему
- **Rich-терминал** — цветной вывод с ASCII-логотипом (graceful fallback без Rich)

## Requirements

- Python 3.12+
- `uv` (рекомендуется) или `pip`
- **macOS** — полноценная поддержка (основная платформа)
- **Linux** — поддержка (детектор через `lsblk`, автозапуск через `systemd`)
- **Windows** — поддержка (детектор через `ctypes` WinAPI, автозапуск через реестр)

## Install

### macOS / Linux
```bash
git clone https://github.com/alekseizadubnenko-art/beckyup.git
cd beckyup
./install.sh           # deps + alias beckyup → shell rc + инструкция
```

### Windows (PowerShell)
```powershell
git clone https://github.com/alekseizadubnenko-art/beckyup.git
cd beckyup
.\install.ps1          # deps + alias beckyup → PowerShell profile
```

После установки открой новый терминал и просто:

```bash
beckyup
```

Или вручную (без alias):

```bash
cd beckyup/backup_tool
uv sync                # или pip install -r requirements.txt
uv run python main.py
```

## Quickstart

```bash
uv run python main.py
```

Первый запуск запускает wizard:
1. Выбрать папки для бэкапа (Desktop, Projects, Documents... или свой путь)
2. Выбрать типы файлов (все / документы / изображения / код / архивы)
3. Подключить бэкап-флешку — UUID запоминается
4. Настроить безопасность (без пароля / системный / свой пароль)
5. Включить автозапуск при входе

Готово. Флешка подключена — бэкап идёт.

## Usage

```bash
uv run python main.py                           # мониторинг (фон)
uv run python main.py --wizard                  # перенастройка
uv run python main.py --source ~/Projects \
  --destination /Volumes/BACKUP                 # разовый бэкап
uv run python main.py --config custom.json      # своя конфигурация
uv run python main.py --help                    # справка
```

## Как это работает

1. `device_detector` polling точек монтирования раз в 5 секунд:
   - **macOS:** `/Volumes/` + `diskutil info` → UUID
   - **Linux:** `lsblk -J` → фильтр `/media/`, `/mnt/`, `/run/media/`
   - **Windows:** `ctypes` WinAPI → `GetLogicalDrives` + `GetVolumeInformation`
2. Появился новый UUID → проверка в whitelist
3. Если флешка знакомая → подтверждение (если настроено) → `backup_engine`
4. `backup_engine` проверяет место на диске, доступность записи, копирует через `shutil.copy2`
5. OSError (выдернули флешку, битый сектор) — ловятся пофайлово, бэкап не падает

## Безопасность

| Режим | macOS | Linux | Windows |
|---|---|---|---|
| `none` + авто | Бэкап без вопросов | Бэкап без вопросов | Бэкап без вопросов |
| `none` | osascript-диалог | zenity/kdialog/терминал | PowerShell/терминал |
| `system` | Системный пароль macOS | `pkexec` / `sudo` | UAC через PowerShell |
| `custom` | bcrypt-пароль | bcrypt-пароль | bcrypt-пароль |

## Tests

```bash
uv run python -m unittest discover tests -v
```

## Project structure

```
backup_tool/
├── main.py                    # CLI entry point
├── cli/wizard.py              # Setup wizard (questionary)
├── core/
│   ├── backup_engine.py       # Copy engine + safety checks
│   ├── device_detector.py     # USB polling (macOS/Linux/Windows)
│   └── device_monitor.py      # Thread loop + whitelist
├── config/
│   ├── manager.py             # JSON config CRUD
│   └── default_config.json    # Defaults
├── utils/
│   ├── auth.py                # Cross-platform auth dialogs
│   ├── launchagent.py         # Autostart (macOS/Linux/Windows)
│   ├── ui.py                  # Rich output + fallback
│   ├── logger.py              # File + console logging
│   └── platform.py            # OS detection
├── tests/                     # 24+ unit tests
├── install.sh                 # macOS/Linux installer
└── install.ps1                # Windows installer
```

## Contributing

PRs welcome.

- TDD: сначала тест, потом код
- Все тесты зелёные перед PR
- Опциональные зависимости — через try/except import
- UI на русском, код на английском

**Что можно улучшить:**
- Native USB-события (pyobjc, pyudev, pywin32) — вместо polling
- GUI / tray-иконка
- Инкрементальные бэкапы
- Шифрование

## License

MIT
