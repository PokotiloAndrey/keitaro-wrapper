import argparse
import asyncio
from sqlalchemy import inspect, text
from .config import settings
from .db import engine
from .main import catalogs


async def check(use_base_domain=False):
    problems = []
    if not settings.app_password or settings.app_password == 'change-this-before-running':
        problems.append('Задайте собственный APP_PASSWORD в .env')
    if not settings.demo_mode and not settings.keitaro_api_key:
        problems.append('Не задан KEITARO_API_KEY')
    tables = set(inspect(engine).get_table_names())
    if not {'drafts', 'operations', 'alembic_version'} <= tables:
        problems.append('Выполните миграции: python -m alembic upgrade head')
    else:
        with engine.connect() as connection:
            if connection.execute(text('SELECT version_num FROM alembic_version')).scalar() != '001':
                problems.append('Миграции не актуальны: python -m alembic upgrade head')
    print('Режим: ' + ('демо' if settings.demo_mode else 'Keitaro API'))
    data = await catalogs()
    labels = {'domains': 'Домены', 'groups': 'Группы', 'sources': 'Источники', 'offers': 'Офферы'}
    for key, label in labels.items():
        print(f'{label}: {len(data[key])}')
        if key in data['errors']:
            err = data['errors'][key]
            print(f'  HTTP {err["status"]}: {err["message"]}')
        if key in data['missing'] and not (key == 'domains' and use_base_domain):
            problems.append(f'{label}: нет доступных записей')
    if use_base_domain:
        print('Базовый домен выбран явно; согласуйте его использование для задания.')
    for problem in problems:
        print('Не готово: ' + problem)
    if not problems:
        print('Чтение справочников и локальная конфигурация проверены. Права записи и редиректы проверяются при создании тестовой кампании.')
    return 2 if problems else 0


def main():
    parser = argparse.ArgumentParser(description='Проверка конфигурации и чтения Keitaro без изменения кампаний')
    parser.add_argument('--base-domain', action='store_true')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(check(args.base_domain)))


if __name__ == '__main__':
    main()
