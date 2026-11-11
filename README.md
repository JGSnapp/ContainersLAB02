# Лабораторная работа №2 — Docker

Сборка и запуск образа приложения [assist-py](https://github.com/FilBTi/assist-py) на FastAPI: оптимизация зависимостей, настройка `.dockerignore`, проверка здоровья контейнера, диагностика ошибок и тегирование образов.

## Вводные

| Параметр | Значение |
|---|---|
| Студент | Костенко Кирилл Денисович |
| ИСУ | 474308 |
| Префикс | `kostenko` |
| Порт | `5438` |
| Учебный секретный ключ | `secret08kostenko` |

Нужны запущенный Docker Desktop с Linux-контейнерами и свободный порт `5438`. Команды ниже рассчитаны на PowerShell и выполняются из папки `assist-py`.

- `assist-py/Dockerfile` — базовая сборка.
- `assist-py/Dockerfile.optimized` — установка Python-зависимостей без кеша pip, установка curl и HEALTHCHECK.
- `assist-py/.dockerignore` — исключения из контекста сборки.
- `images/` — скриншоты выполнения работы.

## Как запустить

Из корня Lab02 перейди в папку приложения, соберите образ и запустите контейнер:

```powershell
cd .\assist-py
docker build -t kostenko-assistant:final -f Dockerfile.optimized .
docker run -d --name kostenko-assistant-final -p 5438:5438 -e APP_OWNER=kostenko -e APP_SECRET=secret08kostenko kostenko-assistant:final
```

Приложение доступно по адресу http://localhost:5438, документация API — http://localhost:5438/docs.

## Основные команды проверки

```powershell
# Главная страница, персонализация и здоровье приложения
curl.exe http://localhost:5438/
curl.exe http://localhost:5438/me
curl.exe http://localhost:5438/health

# Создание и чтение заметки (--% используется в PowerShell)
curl.exe --% -X POST http://localhost:5438/notes -H "Content-Type: application/json" -d "{\"text\":\"ЛР2: сборка образа\"}"
curl.exe http://localhost:5438/notes

# Получение персонального флага
curl.exe http://localhost:5438/secret/secret08kostenko

# Статус контейнера после первых проверок здоровья
Start-Sleep -Seconds 40
docker ps --filter "name=kostenko-assistant-final" --format "table {{.Names}}\t{{.Status}}"

# Логи приложения и результаты HEALTHCHECK
docker logs kostenko-assistant-final
docker inspect --format "{{range .State.Health.Log}}{{println .Output}}{{end}}" kostenko-assistant-final
```

Ожидаемые результаты: `owner: kostenko` в `/me`, флаг `LAB2_SUCCESS_KOSTENKO` и статус контейнера `healthy`. Заметки хранятся в памяти приложения и теряются при его перезапуске.

## Сборка версий и теги

```powershell
# Базовый и оптимизированный образы
docker build -t kostenko-assistant:v1 .
docker build -t kostenko-assistant:v2 -f Dockerfile.optimized .

# Версия с .dockerignore, собранная базовым Dockerfile
docker build -t kostenko-assistant:v3 .

# Теги финального образа
docker tag kostenko-assistant:final kostenko-assistant:1.0.0
docker tag kostenko-assistant:final "kostenko-assistant:$(Get-Date -Format yyyyMMdd)"

# Список образов и размеры
docker images --filter "reference=kostenko-assistant" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

В ходе лабораторной v2 собирался до добавления curl и HEALTHCHECK: размер уменьшился с 285 до 258 МБ по DISK USAGE. Сборка v2 из текущего финального Dockerfile.optimized уже включает эти дополнения, поэтому её размер может отличаться от исходного сравнения.

## Повторный запуск и обновление

Для запуска существующего остановленного контейнера:

```powershell
docker start kostenko-assistant-final
```

После изменения Dockerfile сначала успешно пересобери образ, затем пересоздай контейнер:

```powershell
docker build -t kostenko-assistant:final -f Dockerfile.optimized .
docker stop kostenko-assistant-final
docker rm kostenko-assistant-final
docker run -d --name kostenko-assistant-final -p 5438:5438 -e APP_OWNER=kostenko -e APP_SECRET=secret08kostenko kostenko-assistant:final
```

Если порт занимает контейнер первого этапа, останови его командой `docker stop kostenko-assistant-1`. Ошибка `curl: not found` в HEALTHCHECK означает, что curl отсутствует внутри используемого образа: проверь успешность сборки и пересоздай контейнер из обновлённого образа.

## Хранение данных

Данные БД хранятся в Docker volume kostenko-pgdata.
Было проверенно, что данные сохраняются при удалении и пересоздании контейнера PostgreSQL.

Для изоляции сервисов используется сеть kostenko-backend.
В ней ассистент подключается к контейнеру с БД kostenko-postgres.

Создание volume и сети:

```powershell
docker volume create kostenko-pgdata
docker network create kostenko-backend
```

Запуск БД:

```powershell
docker run -d `
  --name kostenko-postgres `
  --network kostenko-backend `
  -e POSTGRES_USER=user_08 `
  -e POSTGRES_PASSWORD=pgpass_08 `
  -e POSTGRES_DB=kostenko08 `
  -v kostenko-pgdata:/var/lib/postgresql/data `
  postgres:15
```

Запуск ассистента:

```powershell
docker run -d `
  --name kostenko-assistant `
  --network kostenko-backend `
  -p 8008:8008 `
  -e APP_OWNER=kostenko `
  -e APP_SECRET=secret08kostenko `
  -e DATABASE_URL="postgresql://user_08:pgpass_08@kostenko-postgres:5432/kostenko08" `
  -v "${PWD}\config:/app/config:ro" `
  kostenko-assistant:v3
```

Проверка заметок:
```powershell
curl.exe http://localhost:8008/notes
```
