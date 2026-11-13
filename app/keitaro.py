import copy
import httpx
from .config import settings


class UpstreamError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Keitaro:
    async def request(self, method, path, payload=None):
        if not settings.keitaro_api_key:
            raise UpstreamError(503, "Не задан KEITARO_API_KEY")
        try:
            async with httpx.AsyncClient(
                base_url=settings.keitaro_url.rstrip("/") + "/admin_api/v1/",
                headers={"Api-Key": settings.keitaro_api_key},
                timeout=25,
                follow_redirects=False,
            ) as client:
                response = await client.request(method, path, json=payload)
        except httpx.HTTPError:
            raise UpstreamError(
                502,
                "Сетевая ошибка Keitaro. Результат записи может быть неизвестен; обновите данные перед повтором.",
            ) from None
        if not response.is_success:
            raise UpstreamError(
                response.status_code,
                f"Keitaro вернул HTTP {response.status_code}. Проверьте права, параметры и доступность API.",
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise UpstreamError(
                502, "Keitaro вернул не JSON. Проверьте адрес и защиту сервера."
            ) from None


class DemoKeitaro:
    def __init__(self):
        self.data = {
            "campaigns": [],
            "streams": [],
            "offers": [
                {"id": i, "name": f"Демо-оффер {i}", "state": "active"}
                for i in range(1, 5)
            ],
            "domains": [{"id": 1, "name": "demo.example"}],
            "groups": [{"id": 1, "name": "Тестовая группа", "type": "campaigns"}],
            "traffic_sources": [{"id": 1, "name": "Демо-источник"}],
        }
        self.seq = 100

    async def request(self, method, path, payload=None):
        parts = path.split("?")[0].split("/")
        kind = parts[0]
        if kind == "campaigns" and len(parts) == 3:
            return copy.deepcopy(
                [x for x in self.data["streams"] if x["campaign_id"] == int(parts[1])]
            )
        if method == "GET":
            if len(parts) == 1:
                return copy.deepcopy(self.data[kind])
            result = next(
                (x for x in self.data[kind] if x["id"] == int(parts[1])), None
            )
            if result is None:
                raise UpstreamError(404, "Объект не найден")
            return copy.deepcopy(result)
        if method == "POST":
            self.seq += 1
            row = {**copy.deepcopy(payload), "id": self.seq}
            self.data[kind].append(row)
            return copy.deepcopy(row)
        if method == "PUT":
            row = next(x for x in self.data[kind] if x["id"] == int(parts[1]))
            row.update(copy.deepcopy(payload))
            return copy.deepcopy(row)
        raise UpstreamError(405, "Метод недоступен")


api = DemoKeitaro() if settings.demo_mode else Keitaro()
