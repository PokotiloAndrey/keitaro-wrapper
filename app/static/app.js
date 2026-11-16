let catalog,
  currentCampaign,
  requestId = crypto.randomUUID();
const $ = (id) => document.getElementById(id);
function message(text, error = false) {
  $("status").textContent = text;
  $("status").className = error ? "error" : "";
}
async function api(path, method = "GET", data) {
  const r = await fetch("/api" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "KeitaroWrapper",
    },
    body: data ? JSON.stringify(data) : undefined,
  });
  const result = await r.json();
  if (!r.ok)
    throw Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail),
    );
  return result;
}
async function busy(fn) {
  const buttons = [...document.querySelectorAll("button")];
  buttons.forEach((b) => (b.disabled = true));
  try {
    await fn();
  } catch (e) {
    message(e.message, true);
  } finally {
    buttons.forEach((b) => (b.disabled = false));
    updateReadiness();
  }
}
function blockers() {
  return (catalog?.missing || []).filter(k => k !== "domains" || !$("base-domain").checked);
}
function updateReadiness() {
  $("create-submit").disabled = !catalog || blockers().length > 0;
  $("domain").disabled = $("base-domain").checked || !catalog?.domains.length;
  $("domain").required = !$("base-domain").checked;
}
function readinessMessage() {
  const labels = {domains:"домен", groups:"группа кампаний", sources:"источник трафика", offers:"оффер"};
  const missing = blockers();
  const failures = Object.entries(catalog.errors || {}).map(([k, v]) => `${labels[k]}: HTTP ${v.status}`);
  if (missing.length) {
    message("Нет доступных данных: " + missing.map(k => labels[k]).join(", ") +
      (failures.length ? ". Ошибки: " + failures.join("; ") : "") +
      ". Проверьте доступы в Keitaro, затем нажмите «Обновить списки». Редактор существующих кампаний доступен отдельно.", true);
  } else message($("base-domain").checked
    ? "Выбран базовый домен трекера. Используйте этот вариант, если он согласован для задания."
    : "Готово. Создайте кампанию или откройте существующую.");
}
$("base-domain").onchange = () => { updateReadiness(); if (catalog) readinessMessage(); };
function option(select, value, text) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = text;
  select.append(o);
}
function fill(id, rows) {
  const previous = $(id).value;
  const available = rows.filter((x) => x.state !== "deleted");
  $(id).replaceChildren();
  option($(id), "", available.length ? "Выберите…" : "Нет доступных записей в Keitaro");
  $(id).disabled = !available.length;
  for (const x of available)
    option($(id), x.id, `#${x.id} ${x.name}`);
  if (available.some(x => String(x.id) === previous)) $(id).value = previous;
}
async function campaigns() {
  fill("campaign", await api("/campaigns"));
}
async function init() {
  await busy(async () => {
    catalog = await api("/catalogs");
    for (const [id, key] of [
      ["offer", "offers"],
      ["domain", "domains"],
      ["group", "groups"],
      ["source", "sources"],
    ])
      fill(id, catalog[key]);
    $("prefix").textContent = "Префикс: " + catalog.prefix;
    $("mode").textContent = catalog.demo
      ? "ДЕМО · данные в памяти"
      : "Keitaro API";
    $("mode").className = catalog.demo ? "badge" : "";
    $("base-domain-label").textContent = "Базовый домен: " + catalog.base_domain;
    readinessMessage();
    try { await campaigns(); } catch (e) { message("Не удалось загрузить кампании: " + e.message, true); }
  });
}
$("create").onsubmit = (e) => {
  e.preventDefault();
  busy(async () => {
    const r = await api("/campaigns", "POST", {
      name: $("name").value,
      country: $("country").value,
      offer_id: +$("offer").value,
      domain_id: $("base-domain").checked ? null : +$("domain").value,
      use_base_domain: $("base-domain").checked,
      group_id: +$("group").value,
      traffic_source_id: +$("source").value,
      request_id: requestId,
    });
    requestId = crypto.randomUUID();
    await campaigns();
    $("campaign").value = r.id;
    await openCampaign();
    message("Кампания создана: " + r.name);
  });
};
$("refresh").onclick = () => busy(campaigns);
$("reload-catalogs").onclick = init;
$("open").onclick = () => busy(openCampaign);
async function openCampaign() {
  currentCampaign = +$("campaign").value;
  if (!currentCampaign) throw Error("Выберите кампанию");
  const streams = await api(`/campaigns/${currentCampaign}/streams`);
  $("streams").replaceChildren();
  for (const stream of streams) {
    const card = document.createElement("article");
    $("streams").append(card);
    if (stream.schema === "landings") {
      const draft = await api(
        `/campaigns/${currentCampaign}/streams/${stream.id}/fetch`,
        "POST",
        {},
      );
      renderDraft(card, draft);
    } else {
      const h = document.createElement("h2");
      h.textContent = stream.name;
      card.append(h);
    }
  }
}
function button(text, fn) {
  const b = document.createElement("button");
  b.textContent = text;
  b.onclick = () => busy(fn);
  return b;
}
function renderDraft(card, draft) {
  card.replaceChildren();
  card.classList.toggle("pending", Boolean(draft.dirty));
  const h = document.createElement("h2");
  h.textContent = draft.name + ` · #${draft.stream_id}` + (draft.dirty ? " · Не опубликовано" : " · Сохранено");
  card.append(h);
  const tools = document.createElement("div");
  tools.className = "toolbar";
  const push = button("Применить в Keitaro", async () => {
    await api(`/drafts/${draft.stream_id}/push`, "POST", {
      revision: draft.revision,
    });
    await openCampaign();
    message("Изменения записаны и проверены в Keitaro.");
  });
  push.className = "primary";
  tools.append(
    push,
    button("Отменить черновик", async () => {
      await api(`/drafts/${draft.stream_id}/cancel`, "POST", {
        revision: draft.revision,
      });
      await openCampaign();
    }),
  );
  const total = document.createElement("span");
  total.className = "total";
  total.textContent =
    "Итого: " +
    draft.offers
      .filter((x) => x.state !== "disabled")
      .reduce((s, x) => s + x.share, 0) +
    "%";
  tools.append(total);
  card.append(tools);
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const title of ["Оффер", "Доля %", "Закрепить", "Действие"]) {
    const th = document.createElement("th");
    th.textContent = title;
    head.append(th);
  }
  table.append(head);
  async function save(rows) {
    const updated = await api(`/drafts/${draft.stream_id}`, "PUT", {
      revision: draft.revision,
      offers: rows.map((x) => ({
        offer_id: x.offer_id,
        share: x.share,
        state: x.state || "active",
        locked: x.locked || false,
      })),
    });
    renderDraft(card, updated);
    message("Черновик сохранён. Для отправки нажмите «Применить».");
  }
  for (const row of draft.offers) {
    const tr = document.createElement("tr");
    if (row.state === "disabled") tr.className = "disabled";
    const name = document.createElement("td");
    name.textContent =
      `#${row.offer_id} ` +
      (catalog.offers.find((x) => +x.id === +row.offer_id)?.name || "Оффер");
    const cell = document.createElement("td");
    const n = document.createElement("input");
    n.type = "number";
    n.min = 0;
    n.max = 100;
    n.step = 1;
    n.value = row.share;
    n.disabled = row.state === "disabled";
    n.setAttribute("aria-label", "Доля оффера " + row.offer_id);
    n.onchange = () =>
      busy(() =>
        save(
          draft.offers.map((x) =>
            x.offer_id === row.offer_id
              ? { ...x, share: +n.value, locked: true }
              : x,
          ),
        ),
      );
    cell.append(n);
    const fixed = document.createElement("td");
    const pin = document.createElement("input");
    pin.type = "checkbox";
    pin.checked = row.locked;
    pin.disabled = row.state === "disabled";
    pin.setAttribute("aria-label", "Закрепить оффер " + row.offer_id);
    pin.onchange = () =>
      busy(() =>
        save(
          draft.offers.map((x) =>
            x.offer_id === row.offer_id ? { ...x, locked: pin.checked } : x,
          ),
        ),
      );
    fixed.append(pin);
    const action = document.createElement("td");
    action.append(
      button(row.state === "disabled" ? "Вернуть" : "Убрать", () =>
        save(
          draft.offers.map((x) =>
            x.offer_id === row.offer_id
              ? {
                  ...x,
                  state: x.state === "disabled" ? "active" : "disabled",
                  locked: false,
                }
              : x,
          ),
        ),
      ),
    );
    tr.append(name, cell, fixed, action);
    table.append(tr);
  }
  card.append(table);
  const add = document.createElement("div");
  add.className = "toolbar";
  add.style.marginTop = "16px";
  const select = document.createElement("select");
  select.setAttribute("aria-label", "Добавить оффер");
  const search = document.createElement("input");
  search.placeholder = "Поиск оффера по ID или названию";
  search.setAttribute("aria-label", "Поиск оффера");
  search.oninput = () => {
    const query = search.value.toLowerCase().trim();
    for (const opt of select.options) opt.hidden = Boolean(opt.value) && !opt.textContent.toLowerCase().includes(query);
    if (select.selectedOptions[0]?.hidden) select.value = "";
  };
  add.append(search);
  option(select, "", "Выберите оффер…");
  for (const x of catalog.offers.filter(
    (x) =>
      x.state !== "deleted" && !draft.offers.some((o) => +o.offer_id === +x.id),
  ))
    option(select, x.id, `#${x.id} ${x.name}`);
  add.append(
    select,
    button("Добавить", async () => {
      if (!select.value) throw Error("Выберите оффер");
      await save([
        ...draft.offers,
        { offer_id: +select.value, share: 0, state: "active", locked: false },
      ]);
    }),
  );
  card.append(add);
}
$("logs").onclick = () =>
  busy(async () => {
    $("journal").textContent = JSON.stringify(
      await api("/operations"),
      null,
      2,
    );
  });
init();
