def redistribute(offers):
    rows = [dict(x) for x in offers]
    ids = [x["offer_id"] for x in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Оффер уже добавлен")
    active = [x for x in rows if x.get("state", "active") == "active"]
    if not active:
        raise ValueError("Нельзя убрать последний активный оффер")
    fixed = [x for x in active if x.get("locked", False)]
    free = [x for x in active if not x.get("locked", False)]
    for x in fixed:
        if type(x["share"]) is not int or not 0 <= x["share"] <= 100:
            raise ValueError("Доля должна быть целым числом от 0 до 100")
    remaining = 100 - sum(x["share"] for x in fixed)
    if remaining < 0 or (not free and remaining != 0):
        raise ValueError("Закреплённые доли должны оставлять суммарно 100%")
    if free:
        q, r = divmod(remaining, len(free))
        for i, x in enumerate(free):
            x["share"] = q + (1 if i >= len(free) - r else 0)
    for x in rows:
        if x.get("state") == "disabled":
            x["share"] = 0
    return rows
