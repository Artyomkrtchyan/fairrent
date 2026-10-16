# Начальный контракт данных — черновик v0

Это предложение для совместного согласования, а не реализованный API.

## Listing

`id`, `source`, `external_id`, `source_url`, `property_id` (может отсутствовать), `description`, `price_original`, `currency_original`, `price_monthly_normalized`, `currency_normalized`, `utilities_included` (true/false/unknown), `area_m2`, `rooms`, `floor`, `total_floors`, `condition`, `address`, `district_id`, `latitude`, `longitude`, `published_at`, `first_seen_at`, `last_seen_at`, `status`.

Площадь — м²; расстояния — метры; даты — ISO 8601 UTC. Неизвестные значения — null, не 0. Нормализация валюты сохраняет дату и источник курса. Сочетание source + external_id идентифицирует объявление источника; наблюдения хранятся отдельно. Точные обязательные поля фиксируются после анализа источников.

## Estimate

`listing_id`, `expected_price`, `lower_bound`, `upper_bound`, `currency`, `price_status`, `comparable_count`, `confidence_explanation`, `factors`, `model_version`, `rules_version`, `data_as_of`, `created_at`.

При `insufficient_data` цена и границы могут быть null; причина обязательна. Сигналы риска передаются отдельно от ценового статуса.

## RiskSignal и Review

RiskSignal: `id`, `listing_id`, `rule_id`, `rules_version`, `evidence`, `created_at`.

Review: `id`, `listing_id`, `signal_ids`, `status` (pending/in_review/resolved), `decision` (nullable), `reason`, `reviewed_at` (nullable). Повторная обработка одного сигнала не создаёт дубликат очереди.

## Предлагаемые API

- `GET /api/v1/listings` — фильтры и пагинация.
- `GET /api/v1/listings/{id}` — карточка.
- `GET /api/v1/listings/{id}/estimate` — оценка и объяснение.
- `GET /api/v1/market-index` — район, период, число наблюдений.
- `GET /api/v1/reviews` — очередь для проверяющего.
- `PATCH /api/v1/reviews/{id}` — решение проверяющего.

Права доступа, форматы ошибок, пагинация, синтетические ответы и OpenAPI согласуются до реализации.
