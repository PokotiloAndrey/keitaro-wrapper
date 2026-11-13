import asyncio
import hashlib
import json
import secrets
import uuid
from pathlib import Path
import pycountry
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from .config import settings
from .db import Session, Draft, Operation
from .keitaro import api, UpstreamError
from .shares import redistribute

security = HTTPBasic()


def auth(c: HTTPBasicCredentials = Depends(security)):
    if not settings.app_password:
        raise HTTPException(503, "Задайте APP_PASSWORD в .env")
    if not (
        secrets.compare_digest(c.username.encode(), settings.app_user.encode())
        and secrets.compare_digest(c.password.encode(), settings.app_password.encode())
    ):
        raise HTTPException(
            401, "Неверный логин или пароль", headers={"WWW-Authenticate": "Basic"}
        )


app = FastAPI(title="Keitaro Workshop", dependencies=[Depends(auth)])
lock = asyncio.Lock()


@app.middleware("http")
async def protect(request: Request, call_next):
    if (
        request.method in ("POST", "PUT", "PATCH", "DELETE")
        and request.headers.get("X-Requested-With") != "KeitaroWrapper"
    ):
        return JSONResponse(
            {"detail": "Отсутствует заголовок X-Requested-With"}, status_code=403
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(UpstreamError)
async def upstream_error(request, exc):
    return JSONResponse(
        {"detail": exc.message, "upstream_status": exc.status}, status_code=502
    )


@app.get("/")
async def home():
    return FileResponse(Path(__file__).parent / "static/index.html")


@app.get("/app.js")
async def javascript():
    return FileResponse(
        Path(__file__).parent / "static/app.js", media_type="text/javascript"
    )


class CreateCampaign(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    country: str
    offer_id: int = Field(gt=0)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    traffic_source_id: int = Field(gt=0)
    request_id: uuid.UUID

    @field_validator("country")
    @classmethod
    def country_code(cls, v):
        v = v.strip().upper()
        if not pycountry.countries.get(alpha_2=v):
            raise ValueError("Нужен ISO-код страны, например DE")
        return v

    @field_validator("name")
    @classmethod
    def name_value(cls, v):
        if not v.strip():
            raise ValueError("Введите название")
        return v.strip()


@app.get("/api/catalogs")
async def catalogs():
    values = await asyncio.gather(
        *(
            api.request("GET", p)
            for p in ["domains", "groups?type=campaigns", "traffic_sources", "offers"]
        )
    )
    return {
        "demo": settings.demo_mode,
        "prefix": settings.campaign_prefix,
        **dict(zip(["domains", "groups", "sources", "offers"], values)),
    }


@app.get("/api/campaigns")
async def campaigns():
    return [
        x
        for x in await api.request("GET", "campaigns")
        if x["name"].startswith(settings.campaign_prefix)
    ]


async def owned(cid):
    row = await api.request("GET", f"campaigns/{cid}")
    if not row["name"].startswith(settings.campaign_prefix):
        raise HTTPException(403, "Разрешены только кампании с вашим тестовым префиксом")
    return row


def fingerprint(stream):
    return hashlib.sha256(
        json.dumps(stream, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def dto(row):
    return {
        "stream_id": row.stream_id,
        "campaign_id": row.campaign_id,
        "revision": row.revision,
        "offers": row.offers,
        "name": row.baseline.get("name", ""),
    }


@app.post("/api/campaigns")
async def create_campaign(body: CreateCampaign):
    async with lock:
        with Session() as db:
            opid = str(body.request_id)
            old = db.get(Operation, opid)
            if old:
                if old.detail.get("input") != body.model_dump(mode="json"):
                    raise HTTPException(
                        409, "request_id уже использован с другими параметрами"
                    )
                if old.status == "done":
                    return old.detail["result"]
                raise HTTPException(
                    409,
                    {
                        "message": "Операция уже запускалась. Проверьте журнал и Keitaro перед повтором.",
                        "operation": old.detail,
                    },
                )
            for kind, ident in [
                ("offers", body.offer_id),
                ("domains", body.domain_id),
                ("traffic_sources", body.traffic_source_id),
            ]:
                await api.request("GET", f"{kind}/{ident}")
            groups = await api.request("GET", "groups?type=campaigns")
            if not any(int(x["id"]) == body.group_id for x in groups):
                raise HTTPException(422, "Группа кампаний не найдена")
            op = Operation(
                id=opid,
                kind="create",
                status="started",
                detail={"input": body.model_dump(mode="json")},
            )
            db.add(op)
            db.commit()
            campaign = None
            try:
                name = (
                    body.name
                    if body.name.startswith(settings.campaign_prefix)
                    else settings.campaign_prefix + body.name
                )
                campaign = await api.request(
                    "POST",
                    "campaigns",
                    {
                        "name": name,
                        "alias": "t" + uuid.uuid4().hex[:15],
                        "type": "position",
                        "state": "disabled",
                        "domain_id": body.domain_id,
                        "group_id": str(body.group_id),
                        "traffic_source_id": body.traffic_source_id,
                    },
                )
                op.detail = {**op.detail, "campaign_id": campaign["id"]}
                db.commit()
                common = {
                    "campaign_id": campaign["id"],
                    "state": "active",
                    "collect_clicks": True,
                }
                await api.request(
                    "POST",
                    "streams",
                    {
                        **common,
                        "name": "GEO → Google",
                        "type": "regular",
                        "position": 1,
                        "schema": "redirect",
                        "action_type": "http",
                        "action_payload": "https://www.google.com/",
                        "filters": [
                            {
                                "name": "country",
                                "mode": "accept",
                                "payload": [body.country],
                            }
                        ],
                    },
                )
                await api.request(
                    "POST",
                    "streams",
                    {
                        **common,
                        "name": "Offers",
                        "type": "default",
                        "position": 2,
                        "schema": "landings",
                        "action_type": "http",
                        "landings": [],
                        "offers": [
                            {"offer_id": body.offer_id, "share": 100, "state": "active"}
                        ],
                    },
                )
                campaign = await api.request(
                    "PUT", f"campaigns/{campaign['id']}", {"state": "active"}
                )
                op.status = "done"
                op.detail = {**op.detail, "result": campaign}
                db.commit()
                return campaign
            except UpstreamError:
                op.status = "incomplete"
                db.commit()
                raise


@app.get("/api/campaigns/{cid}/streams")
async def streams(cid: int):
    await owned(cid)
    return await api.request("GET", f"campaigns/{cid}/streams")


@app.post("/api/campaigns/{cid}/streams/{sid}/fetch")
async def fetch(cid: int, sid: int):
    async with lock:
        await owned(cid)
        stream = await api.request("GET", f"streams/{sid}")
        if int(stream["campaign_id"]) != cid:
            raise HTTPException(404, "Поток не принадлежит кампании")
        if stream.get("schema") != "landings":
            raise HTTPException(422, "Этот поток не содержит редактора офферов")
        with Session() as db:
            row = db.get(Draft, sid)
            if row:
                return dto(row)
            row = Draft(
                stream_id=sid,
                campaign_id=cid,
                baseline=stream,
                offers=[{**x, "locked": False} for x in stream.get("offers", [])],
                revision=1,
            )
            db.add(row)
            db.commit()
            return dto(row)


class OfferEdit(BaseModel):
    offer_id: int = Field(gt=0)
    share: int = Field(ge=0, le=100)
    state: str = "active"
    locked: bool = False

    @field_validator("state")
    @classmethod
    def valid_state(cls, v):
        if v not in ("active", "disabled"):
            raise ValueError("Неверное состояние")
        return v


class DraftEdit(BaseModel):
    revision: int = Field(ge=1)
    offers: list[OfferEdit] = Field(max_length=100)


class Revision(BaseModel):
    revision: int = Field(ge=1)


def get_draft(db, sid, revision):
    row = db.get(Draft, sid)
    if not row:
        raise HTTPException(404, "Загрузите поток")
    if row.revision != revision:
        raise HTTPException(
            409, "Черновик изменился в другой вкладке. Загрузите его заново."
        )
    return row


@app.put("/api/drafts/{sid}")
async def edit(sid: int, body: DraftEdit):
    async with lock:
        with Session() as db:
            row = get_draft(db, sid, body.revision)
            await owned(row.campaign_id)
            try:
                rows = redistribute([x.model_dump() for x in body.offers])
            except ValueError as e:
                raise HTTPException(422, str(e))
            row.offers = rows
            row.revision += 1
            db.commit()
            return dto(row)


@app.post("/api/drafts/{sid}/cancel")
async def cancel(sid: int, body: Revision):
    async with lock:
        with Session() as db:
            row = get_draft(db, sid, body.revision)
            await owned(row.campaign_id)
            db.delete(row)
            db.commit()
            return {"ok": True}


@app.post("/api/drafts/{sid}/push")
async def push(sid: int, body: Revision):
    async with lock:
        with Session() as db:
            row = get_draft(db, sid, body.revision)
            await owned(row.campaign_id)
            current = await api.request("GET", f"streams/{sid}")
            if fingerprint(current) != fingerprint(row.baseline):
                raise HTTPException(
                    409,
                    "Поток изменён в Keitaro. Отмените черновик и загрузите актуальные данные.",
                )
            try:
                rows = redistribute(row.offers)
            except ValueError as e:
                raise HTTPException(422, str(e))
            for offer in rows:
                if offer["state"] == "active":
                    await api.request("GET", f"offers/{offer['offer_id']}")
            payload = {
                "offers": [
                    {k: x[k] for k in ("offer_id", "share", "state")} for x in rows
                ]
            }
            op = Operation(
                id=str(uuid.uuid4()),
                kind="push",
                status="started",
                detail={"stream_id": sid},
            )
            db.add(op)
            db.commit()
            try:
                await api.request("PUT", f"streams/{sid}", payload)
                saved = await api.request("GET", f"streams/{sid}")
                wanted = sorted(
                    (x["offer_id"], x["share"], x["state"]) for x in payload["offers"]
                )
                actual = sorted(
                    (int(x["offer_id"]), int(x["share"]), x.get("state", "active"))
                    for x in saved.get("offers", [])
                )
                if wanted != actual:
                    raise UpstreamError(
                        502, "Проверка после записи не совпала. Обновите поток."
                    )
                op.status = "done"
                db.delete(row)
                db.commit()
                return saved
            except UpstreamError:
                op.status = "unknown"
                db.commit()
                raise


@app.get("/api/operations")
async def operations():
    with Session() as db:
        return [
            {"id": x.id, "kind": x.kind, "status": x.status, "detail": x.detail}
            for x in db.scalars(
                select(Operation).order_by(Operation.created_at.desc()).limit(30)
            )
        ]
