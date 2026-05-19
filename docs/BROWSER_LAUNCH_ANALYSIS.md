# Технический анализ: проблема запуска Yandex Browser

## 1. Общее описание проблемы

При вызове команды `открой яндекс` (или `запусти яндекс браузер`) система exhibits два дефекта одновременно:

1. **Открывает второй экземпляр Яндекс Браузера**, даже если браузер уже запущен.
2. **Возвращает ошибку `❌ Не удалось открыть яндекс`**, несмотря на то что окно браузера фактически появляется на экране.

---

## 2. Участники, задействованные в сценарии

| Компонент | Файл | Роль в проблеме |
|-----------|------|----------------|
| `CommandRouter` | [`core/command_router.py`](core/command_router.py) | Маршрутизирует голосовую команду на обработчик |
| `_handle_browser_open()` | [`core/command_router.py:185`](core/command_router.py:185) | Обработчик команды `открой яндекс` |
| `YandexBrowserController.open_url()` | [`browser/yandex_controller.py:380`](browser/yandex_controller.py:380) | Открывает URL в браузере |
| `YandexBrowserController.initialize()` | [`browser/yandex_controller.py:251`](browser/yandex_controller.py:251) | Подключается к браузеру через CDP |
| `YandexBrowserController._start_browser()` | [`browser/yandex_controller.py:280`](browser/yandex_controller.py:280) | Запускает новый процесс браузера |
| `YandexBrowserController.launch_or_focus()` | [`browser/yandex_controller.py:165`](browser/yandex_controller.py:165) | Основной метод запуска/фокуса |

---

## 3. Детальный разбор сценария

### Шаг 1. Пользователь отправляет команду `открой яндекс`

Команда попадает в [`CommandRouter.route()`](core/command_router.py:59), где проверяется на соответствие паттернам.

Паттерн `browser_open` (строка 95):
```python
'browser_open': r'(открой|запусти)\s+(яндекс|браузер|youtube|ютуб|вк|vk|гугл|google)'
```

Фраза `открой яндекс` **полностью совпадает** с этим паттерном, поэтому вызывается [`_handle_browser_open()`](core/command_router.py:185), а **не** [`_handle_browser_launch_or_focus()`](core/command_router.py:199).

> **Примечание:** паттерн `browser_launch_or_focus` (`открой яндекс браузер`) не перехватывает короткую форму `открой яндекс`, потому что требует слова `браузер` после `яндекс`.

### Шаг 2. `_handle_browser_open()` вызывает `browser.open_url('https://ya.ru')`

```python
# core/command_router.py, строка 193
success = await browser.open_url(url)
```

### Шаг 3. `open_url()` вызывает `initialize()`, потому что `self.driver` is `None`

```python
# browser/yandex_controller.py, строка 382-384
if not self.driver:
    if not await self.initialize():
        return False
```

### Шаг 4. `initialize()` — корень первой проблемы

```python
# browser/yandex_controller.py, строка 258-266
try:
    self.driver = webdriver.Chrome(options=options)
    logger.info("Connected to existing Yandex Browser instance")
except:
    # Start new browser instance
    logger.info("Starting new Yandex Browser instance...")
    await self._start_browser()
    self.driver = webdriver.Chrome(options=options)
```

**Что происходит, когда Яндекс Браузер уже запущен обычным способом (без `--remote-debugging-port`):**

1. `webdriver.Chrome(options=options)` пытается подключиться к `localhost:9222`.
2. Подключение падает с ошибкой (порт не открыт, потому что браузер запущен без флага отладки).
3. Блок `except` перехватывает **любое** исключение, включая ошибку подключения.
4. Вызывается [`_start_browser()`](browser/yandex_controller.py:280) — **запускается второй экземпляр** браузера с флагом `--remote-debugging-port=9222`.
5. Затем `webdriver.Chrome(options=options)` подключается к **новому** экземпляру.

**Результат:** на экране появляется второе окно Яндекс Браузера.

### Шаг 5. Почему возвращается `❌ Не удалось открыть яндекс`

После того как `initialize()` возвращает `True`, управление возвращается в `open_url()`:

```python
# browser/yandex_controller.py, строка 357
self.driver.execute_script(f"window.open('{url}', '_blank');")
```

Если `self.driver` был успешно создан (подключён к новому экземпляру), эта строка выполняется. Но если по какой-то причине `self.driver` остался `None` или `execute_script` упал — метод возвращает `False`, и [`_handle_browser_open()`](core/command_router.py:185) формирует ответ `❌ Не удалось открыть яндекс`.

На практике это происходит потому что:
- Между запуском нового процесса и готовностью CDP-порта проходит время (~3 секунды в [`_start_browser()`](browser/yandex_controller.py:280)).
- Если `webdriver.Chrome()` вызывается раньше, чем порт открылся — падает с ошибкой, `initialize()` возвращает `False`, `open_url()` возвращает `False`.

---

## 4. Коренные причины (Root Cause Analysis)

### 4.1. Отсутствие флага `--remote-debugging-port` у уже запущенного браузера

Яндекс Браузер, запущенный пользователем вручную (через ярлык или меню Пуск), **не имеет открытого CDP-порта**. Метод `initialize()` не может к нему подключиться и ошибочно считает, что браузера нет.

### 4.2. Слишком широкий `except` в `initialize()`

```python
except:  # ловит ВСЕ исключения, включая ошибки CDP-подключения
```

Блок `except` не различает:
- "браузер не установлен" (файл `browser.exe` не найден)
- "браузер запущен, но CDP-порт не открыт" (соединение отклонено)
- "браузер запущен с CDP, но порт занят другим процессом"

Все эти случаи приводят к одному и тому же действию — запуску нового экземпляра.

### 4.3. Отсутствие проверки на дубликат процесса в `_start_browser()`

Метод [`_start_browser()`](browser/yandex_controller.py:280) не проверяет, запущен ли уже процесс `browser.exe`. Он вызывает `subprocess.Popen()` без условий, что гарантирует создание второго экземпляра.

### 4.4. Несоответствие паттернов распознавания команд

Команда `открой яндекс` попадает в обработчик `browser_open` (открытие URL), а не в `browser_launch_or_focus` (запуск/фокус). Это означает, что даже после исправления `launch_or_focus()`, команда `открой яндекс` не будет использовать новую логику, пока паттерн не будет исправлен.

---

## 5. Последствия дефекта

| Последствие | Описание |
|-------------|----------|
| Два экземпляра браузера | Один запущен пользователем, второй — скриптом. Дублирует память, сессии, cookies |
| Потеря сессии пользователя | Новый экземпляр не имеет доступа к сессии уже запущенного браузера |
| Неверный ответ ассистента | Пользователь слышит `❌ Не удалось открыть яндекс`, хотя окно появилось |
| Потенциальный конфликт портов | Два процесса на порту 9222 вызывают неопределённое поведение Selenium |
| Увеличение времени отклика | Запуск нового процесса занимает 3–5 секунд |

---

## 6. Предлагаемое решение

### 6.1. Исправить `initialize()` — не запускать браузер при ошибке CDP

```python
async def initialize(self):
    options = Options()
    options.add_experimental_option("debuggerAddress", f"localhost:{self.debug_port}")

    try:
        self.driver = webdriver.Chrome(options=options)
        logger.info("Connected to existing Yandex Browser via CDP")
    except Exception as e:
        logger.warning(f"CDP connection failed ({e}), browser may be running without debug port")
        # НЕ запускаем новый экземпляр здесь — это делает launch_or_focus()
        return False

    await self._connect_cdp()
    await self._update_tabs()
    return True
```

### 6.2. Исправить паттерн `browser_open` в `command_router.py`

Перенести `открой яндекс` из `browser_open` в `browser_launch_or_focus`, или добавить приоритет проверки:

```python
# browser_open должен НЕ перехватывать "открой яндекс"
'browser_open': r'(открой|запусти)\s+(youtube|ютуб|вк|vk|гугл|google)',
'browser_launch_or_focus': r'(открой|запусти|активируй|переключи)\s+(яндекс\s+браузер|браузер\s+яндекс|яндекс)',
```

### 6.3. Добавить проверку на дубликат в `_start_browser()`

```python
async def _start_browser(self):
    if self.is_browser_running():
        logger.warning("Yandex Browser is already running, refusing to start duplicate")
        return  # Не запускаем второй экземпляр
    # ... остальная логика запуска
```

### 6.4. Исправить `open_url()` — возвращать осмысленный результат

```python
async def open_url(self, url: str) -> bool:
    if not self.driver:
        initialized = await self.initialize()
        if not initialized:
            # Пробуем launch_or_focus как fallback
            result = await self.launch_or_focus()
            if not result['success']:
                return False
    # ... открытие URL
```

---

## 7. Рекомендуемая архитектура после исправления

```
┌─────────────────────────────────────────────────────────┐
│                  Пользовательская команда                 │
│              "открой яндекс" / "запусти браузер"          │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              CommandRouter._parse_command()               │
│  Паттерн browser_launch_or_focus перехватывает команду   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│         YandexBrowserController.launch_or_focus()         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Шаг 1: psutil.process_iter() — есть ли процесс?  │   │
│  │   ДА → focus_browser_window()                     │   │
│  │       Успех → return {focused}                    │   │
│  │       Неудача → return {running, no focus}        │   │
│  │   НЕТ → переход к Шагу 2                         │   │
│  └──────────────────────────────────────────────────┘   │
│                            │                             │
│                            ▼                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Шаг 2: _start_browser() — запустить новый         │   │
│  │   (с проверкой is_browser_running() внутри)       │   │
│  │   Подождать 3 сек → CDP порт открылся             │   │
│  │   webdriver.Chrome(debuggerAddress)                │   │
│  │   focus_browser_window()                           │   │
│  │   return {launched}                               │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 8. Текущее состояние (после исправления коммита 53b7318)

Исправлена критическая ошибка в [`launch_or_focus()`](browser/yandex_controller.py:165): при найденном процессе и неудаче фокуса метод теперь сразу возвращает результат, не доходя до CDP-попытки и перезапуска.

**Оставшиеся неисправленные проблемы:**

| Проблема | Статус |
|----------|--------|
| `initialize()` запускает дубликат при отсутствии CDP-порта | ⚠️ Открыта |
| Паттерн `browser_open` перехватывает `открой яндекс` | ⚠️ Открыта |
| `_start_browser()` не проверяет дубликат процесса | ⚠️ Открыта |
| `open_url()` не имеет fallback на `launch_or_focus()` | ⚠️ Открыта |
