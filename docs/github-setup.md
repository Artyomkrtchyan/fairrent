# План настройки GitHub

Статус: локальная заготовка. Репозиторий и GitHub Project ещё не созданы.

Предлагаемое имя репозитория: `fairrent`. Начальная видимость — private, если команда не выберет другую.

## Доска FairRent

Колонки Status: Backlog, Ready, In Progress, Review, Done.

Поля: Area (Data/DB, ML/Ontology, Backend, Frontend, Infra, Docs/QA), Priority (P0, P1, P2), Phase (Foundation, MVP, Intelligence, Release), Assignees, Depends on (ссылки на задачи).

Представления: Board по Status; Table со всеми полями; By Area с группировкой по направлению. Сначала создать пустую доску; задачи участников добавить после распределения.

## Настройки репозитория

- Основная ветка main.
- Labels: area:data, area:db, area:ml, area:ontology, area:backend, area:frontend, area:infra, area:docs, type:feature, type:bug, type:research, blocked.
- Этапы: Foundation, End-to-end MVP, Model and Ontology, Release and Demo; сроки назначить командой.
- Правило main: Pull Request, один независимый review, закрытые обсуждения; обязательные CI-проверки добавить после появления реальных проверок. Доступность защиты зависит от плана и видимости репозитория.
- Доступ участников настроить после получения GitHub usernames.

Не отмечать настройки выполненными без проверки на GitHub.
