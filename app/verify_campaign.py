"""Read-only acceptance check for a Keitaro test campaign."""

import argparse
import asyncio
import json
import sys

from .config import settings
from .keitaro import api, UpstreamError


def _id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _country_filter_matches(filters, country):
    if not isinstance(filters, list) or len(filters) != 1:
        return False
    entry = filters[0]
    if not isinstance(entry, dict) or entry.get("name") != "country" or entry.get("mode") != "accept":
        return False
    value = entry.get("payload")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = [value]
    return value == [country]


def audit_campaign(campaign, streams, *, name, country, group_id, source_id, domain_id, offer_ids):
    issues, warnings = [], []
    if campaign.get("name") != name or not name.startswith(settings.campaign_prefix):
        issues.append("Название или тестовый префикс кампании не совпадает")
    if campaign.get("state") != "active":
        issues.append("Кампания не активна")
    if _id(campaign.get("group_id")) != group_id:
        issues.append("Группа кампании отличается от ожидаемой")
    if _id(campaign.get("traffic_source_id")) != source_id:
        issues.append("Источник трафика отличается от ожидаемого")

    remote_domain = campaign.get("domain_id")
    if remote_domain is None:
        warnings.append("Keitaro не вернул domain_id: выбранный домен проверьте в админке")
    elif _id(remote_domain) != domain_id:
        issues.append("Домен кампании отличается от ожидаемого")

    if not isinstance(streams, list) or len(streams) != 2:
        issues.append("Ожидаются ровно два потока")
        return issues, warnings
    geo = next((s for s in streams if s.get("type") == "regular"), None)
    fallback = next((s for s in streams if s.get("type") == "default"), None)
    if geo is None or fallback is None:
        issues.append("Не найдена пара из обычного и замыкающего потоков")
        return issues, warnings
    if geo.get("schema") != "redirect" or geo.get("action_type") != "http":
        issues.append("GEO-поток не настроен как HTTP-редирект")
    if geo.get("action_payload") not in ("https://www.google.com/", "https://www.google.com"):
        issues.append("GEO-поток не ведёт на Google")
    if geo.get("state") != "active" or not _country_filter_matches(geo.get("filters"), country):
        issues.append("GEO-фильтр страны отличается от ожидаемого")
    if fallback.get("schema") != "landings" or fallback.get("state") != "active":
        issues.append("Замыкающий поток не настроен для офферов")
    if fallback.get("filters") or fallback.get("landings"):
        issues.append("Замыкающий поток имеет посторонние фильтры/лендинги")

    offers = fallback.get("offers")
    if not isinstance(offers, list) or not offers:
        issues.append("В замыкающем потоке нет офферов")
        return issues, warnings
    active = [o for o in offers if o.get("state", "active") == "active"]
    ids = [_id(o.get("offer_id")) for o in active]
    if len(active) != len(offers) or None in ids or len(ids) != len(set(ids)):
        issues.append("Неверные состояния или повторяющиеся ID офферов")
    if offer_ids and (None in ids or sorted(ids) != sorted(offer_ids)):
        issues.append("Набор офферов отличается от ожидаемого")
    try:
        shares = [int(o["share"]) for o in active]
    except (KeyError, TypeError, ValueError):
        shares = []
    if not shares or any(s < 0 or s > 100 for s in shares) or sum(shares) != 100:
        issues.append("Доли офферов в Keitaro не дают ровно 100%")
    return issues, warnings


async def run(args):
    if settings.demo_mode:
        print("Проверка реального Keitaro невозможна при DEMO_MODE=true")
        return 2
    try:
        campaign = await api.request("GET", f"campaigns/{args.campaign_id}")
        streams = await api.request("GET", f"campaigns/{args.campaign_id}/streams")
    except UpstreamError as error:
        print(f"Ошибка чтения Keitaro (HTTP {error.status}): {error.message}")
        return 2
    issues, warnings = audit_campaign(
        campaign, streams,
        name=args.name, country=args.country.upper(),
        group_id=args.group_id, source_id=args.source_id,
        domain_id=args.domain_id, offer_ids=args.offer_ids,
    )
    print(f"Кампания: #{args.campaign_id} | {campaign.get('name', '?')}")
    print(f"Потоков: {len(streams) if isinstance(streams, list) else 'неверный ответ'}")
    for issue in issues:
        print("FAIL:", issue)
    for warning in warnings:
        print("CHECK MANUALLY:", warning)
    if issues:
        print("CONFIGURATION: FAIL")
        return 2
    print("CONFIGURATION: PASS (read-only API check)")
    print("Не заменяет симуляцию трафика с IP разных стран в Keitaro.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Read-only Keitaro campaign check")
    parser.add_argument("--campaign-id", required=True, type=int)
    parser.add_argument("--name", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--group-id", required=True, type=int)
    parser.add_argument("--source-id", required=True, type=int)
    parser.add_argument("--domain-id", required=True, type=int)
    parser.add_argument("--offer-ids", nargs="+", required=True, type=int)
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
