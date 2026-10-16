# План настройки GitHub

## Выполнено 16 октября 2026

- Приватный репозиторий: https://github.com/Artyomkrtchyan/fairrent
- Приватный связанный проект: https://github.com/users/Artyomkrtchyan/projects/4
- Подготовленные документы, структура модулей и шаблоны отправлены в main.
- Board: Backlog → Ready → In Progress → Review → Done.
- Planning: таблица с исполнителями, статусом, Area, Priority и Phase.
- Area: Data / DB, ML / Ontology, Backend, Frontend, Infra, Docs / QA.
- Priority: P0, P1, P2. Phase: Foundation, MVP, Intelligence, Release.
- Репозиторий fairrent выбран по умолчанию для новых задач проекта.
- Доска пустая: задачи и назначения ожидают распределения ролей командой.

Ниже сохранён план дальнейших настроек. Отдельное представление By Area, labels, milestones и защита main пока не настроены. Доступ команды будет настроен после получения usernames.

Имя репозитория: `fairrent`. Видимость: private.

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
