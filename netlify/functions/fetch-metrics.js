const fs = require("node:fs");
const path = require("node:path");

let Agent;
try {
  ({ Agent } = require("node:undici"));
} catch (err) {
  ({ Agent } = require("undici"));
}

const DEFAULT_BASE_URL = "https://ufevsuporte.zammad.com";
const DEFAULT_FROM_DATE = "2025-09-30";
const OPEN_STATE_QUERY = "state:new OR state:open OR state:pending reminder OR state:pending close";
const CLOSED_STATES = new Set(["closed"]);
const OPEN_STATES = new Set(
  OPEN_STATE_QUERY.replace(/state:/g, "")
    .split("OR")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean)
);

const AGENT_NAME_OVERRIDES = new Map([
  [21, "Rafaela Lapa"],
  [20, "Catarina França"],
  [19, "Paula Candeias"],
  [18, "Cátia Leal"],
  [17, "Inês Martinho"],
  [5, "Magali Morim"],
  [4, "Sandra Reis"],
  [3, "Carolina Ferreirinha"],
]);

const AGENT_IDS = new Set(AGENT_NAME_OVERRIDES.keys());

function formatStateLabel(rawState) {
  const value = (rawState || "").trim();
  if (!value) return "Desconhecido";
  return value
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

function makeBucket() {
  return {
    tickets_per_day: new Map(),
    total_time: 0,
    time_count: 0,
    count: 0,
  };
}

function makeStateHolder() {
  return {
    overall: makeBucket(),
    priorities: new Map(),
  };
}

function makeHolder() {
  return {
    overall: makeBucket(),
    priorities: new Map(),
    states: new Map(),
  };
}

function updateBucket(bucket, day, deltaHours) {
  bucket.count += 1;
  bucket.tickets_per_day.set(day, (bucket.tickets_per_day.get(day) || 0) + 1);
  if (typeof deltaHours === "number") {
    bucket.total_time += deltaHours;
    bucket.time_count += 1;
  }
}

function recordEntity(holder, day, priorityName, stateLabel, deltaHours) {
  updateBucket(holder.overall, day, deltaHours);
  if (!holder.priorities.has(priorityName)) {
    holder.priorities.set(priorityName, makeBucket());
  }
  updateBucket(holder.priorities.get(priorityName), day, deltaHours);

  if (!holder.states.has(stateLabel)) {
    holder.states.set(stateLabel, makeStateHolder());
  }
  const stateHolder = holder.states.get(stateLabel);
  updateBucket(stateHolder.overall, day, deltaHours);
  if (!stateHolder.priorities.has(priorityName)) {
    stateHolder.priorities.set(priorityName, makeBucket());
  }
  updateBucket(stateHolder.priorities.get(priorityName), day, deltaHours);
}

function bucketToJson(bucket) {
  const avg = bucket.time_count ? bucket.total_time / bucket.time_count : null;
  const perDayEntries = Array.from(bucket.tickets_per_day.entries()).sort(([a], [b]) => a.localeCompare(b));
  return {
    avg_time_hours: avg !== null ? Number(avg.toFixed(2)) : null,
    tickets_count: bucket.count,
    tickets_per_day: Object.fromEntries(perDayEntries),
  };
}

function mapToJson(map, transformFn) {
  return Object.fromEntries(
    Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b, "pt", { sensitivity: "accent" }))
      .map(([key, value]) => [key, transformFn(value)])
  );
}

function holderToJson(holder) {
  return {
    overall: bucketToJson(holder.overall),
    priorities: mapToJson(holder.priorities, bucketToJson),
    states: mapToJson(holder.states, (stateHolder) => ({
      overall: bucketToJson(stateHolder.overall),
      priorities: mapToJson(stateHolder.priorities, bucketToJson),
    })),
  };
}

const jsonHeaders = {
  "Content-Type": "application/json",
  "Cache-Control": "no-store",
};

function buildError(statusCode, message) {
  return {
    statusCode,
    headers: jsonHeaders,
    body: JSON.stringify({ error: message }),
  };
}

let cachedDispatcher;

function loadCertificateBundle() {
  const inlineCert = process.env.ZAMMAD_CA_CERT?.trim();
  if (inlineCert) {
    return inlineCert;
  }
  const bundlePath = process.env.ZAMMAD_CA_BUNDLE?.trim();
  if (!bundlePath) {
    return null;
  }
  try {
    const absolutePath = path.isAbsolute(bundlePath)
      ? bundlePath
      : path.join(process.cwd(), bundlePath);
    return fs.readFileSync(absolutePath, "utf8");
  } catch (error) {
    console.warn("[fetch-metrics] Failed to read CA bundle", error.message);
    return null;
  }
}

function buildDispatcher() {
  if (cachedDispatcher !== undefined) {
    return cachedDispatcher;
  }
  const insecureFlag = (process.env.ZAMMAD_TLS_INSECURE || "").toLowerCase();
  if (["1", "true", "yes"].includes(insecureFlag)) {
    cachedDispatcher = new Agent({ connect: { rejectUnauthorized: false } });
    return cachedDispatcher;
  }

  const caBundle = loadCertificateBundle();
  if (caBundle) {
    cachedDispatcher = new Agent({ connect: { ca: caBundle } });
    return cachedDispatcher;
  }

  cachedDispatcher = null;
  return cachedDispatcher;
}

async function fetchJson(url, options = {}) {
  const dispatcher = buildDispatcher();
  const requestOptions = dispatcher ? { ...options, dispatcher } : options;
  const response = await fetch(url, requestOptions);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status} ${response.statusText}: ${text}`);
  }
  return response.json();
}

async function pagedGet(baseUrl, path, headers, searchParams = {}) {
  const results = [];
  let page = 1;
  while (true) {
    const url = new URL(`/api/v1${path}`, baseUrl);
    url.search = new URLSearchParams({ per_page: "200", page: String(page), ...searchParams }).toString();
    const data = await fetchJson(url, { headers });
    if (!Array.isArray(data) || data.length === 0) break;
    results.push(...data);
    if (data.length < 200) break;
    page += 1;
  }
  return results;
}

async function fetchAgents(baseUrl, headers) {
  const payload = {
    force: true,
    refresh: false,
    sort_by: "created_at, id",
    order_by: "DESC, ASC",
    page: 1,
    per_page: 200,
    query: "",
    role_ids: [2],
    full: true,
  };

  const url = new URL("/api/v1/users/search", baseUrl);
  const dispatcher = buildDispatcher();
  const requestOptions = {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
  if (dispatcher) {
    requestOptions.dispatcher = dispatcher;
  }
  const response = await fetch(url, requestOptions);

  if (response.status === 403) {
    return pagedGet(baseUrl, "/users", headers);
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  if (Array.isArray(data)) {
    return data;
  }
  if (Array.isArray(data?.users)) {
    return data.users;
  }
  if (Array.isArray(data?.data) && data?.assets?.User) {
    return data.data
      .map((id) => data.assets.User?.[String(id)])
      .filter(Boolean);
  }
  if (data?.assets?.User) {
    return Object.values(data.assets.User);
  }
  return [];
}

async function searchTickets(baseUrl, headers, query) {
  const results = [];
  let page = 1;
  while (true) {
    const url = new URL("/api/v1/tickets/search", baseUrl);
    url.search = new URLSearchParams({ query, expand: "true", per_page: "200", page: String(page) }).toString();
    const data = await fetchJson(url, { headers });
    let ticketsPage = [];
    if (Array.isArray(data)) {
      ticketsPage = data;
    } else if (Array.isArray(data?.tickets)) {
      ticketsPage = data.tickets;
      if (ticketsPage.length && typeof ticketsPage[0] === "number") {
        const ticketAssets = data.assets?.Ticket || {};
        ticketsPage = ticketsPage
          .map((id) => ticketAssets[String(id)])
          .filter(Boolean);
      }
    }
    if (!ticketsPage.length) break;
    results.push(...ticketsPage);
    if (ticketsPage.length < 200) break;
    page += 1;
  }
  return results;
}

function isoToDate(isoString) {
  if (!isoString) return null;
  try {
    return new Date(isoString.replace("Z", "+00:00"));
  } catch (error) {
    return null;
  }
}

const handler = async (event) => {
  try {
    const token = process.env.ZAMMAD_TOKEN;
    if (!token) {
      return buildError(500, "Missing ZAMMAD_TOKEN environment variable");
    }

    const baseUrl = (process.env.ZAMMAD_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");
    const fromDate = event.queryStringParameters?.from || process.env.ZAMMAD_FROM_DATE || DEFAULT_FROM_DATE;
    const headers = {
      Authorization: `Token token=${token}`,
    };

    const agents = await fetchAgents(baseUrl, headers);
    const userById = new Map();

    for (const agent of agents) {
      const id = agent?.id;
      if (!id) continue;
      const fullName = (agent?.fullname || "").trim();
      const fallback = `${agent?.firstname || ""} ${agent?.lastname || ""}`.trim() || agent?.login || `id_${id}`;
      userById.set(id, fullName || fallback);
    }

    for (const [id, name] of AGENT_NAME_OVERRIDES.entries()) {
      userById.set(id, name);
    }

    const priorities = await pagedGet(baseUrl, "/ticket_priorities", headers);
    const priorityById = new Map(
      priorities
        .filter((p) => p?.id)
        .map((p) => [p.id, p.name || `priority_${p.id}`])
    );

    const tickets = await searchTickets(baseUrl, headers, "*");

    const perAgent = new Map();
    const perCustomer = new Map();
    const perState = new Map();
    const closedByDay = new Map();
    const openByDay = new Map();

    const isAfterFromDate = (iso) => {
      const dt = isoToDate(iso);
      if (!dt) return false;
      return dt.toISOString().slice(0, 10) >= fromDate;
    };

    for (const ticket of tickets) {
      const state = (ticket?.state || "").trim().toLowerCase();
      const createdAt = ticket?.created_at;
      if (!createdAt || !isAfterFromDate(createdAt)) continue;

      const ownerId = ticket?.owner_id;
      if (ownerId && AGENT_IDS.size && !AGENT_IDS.has(ownerId)) continue;

      if (CLOSED_STATES.has(state)) {
        const closedAt = ticket?.close_at;
        if (!closedAt) continue;
        const dtCreated = isoToDate(createdAt);
        const dtClosed = isoToDate(closedAt);
        if (!dtCreated || !dtClosed) continue;
        const day = dtClosed.toISOString().slice(0, 10);
        if (day < fromDate) continue;

        const deltaHours = (dtClosed.getTime() - dtCreated.getTime()) / 3_600_000;
        const agentName = userById.get(ownerId) || AGENT_NAME_OVERRIDES.get(ownerId) || (ownerId ? `id_${ownerId}` : "Sem agente");
        const priorityName = ticket?.priority || priorityById.get(ticket?.priority_id) || (ticket?.priority_id ? `priority_${ticket.priority_id}` : "unknown");
        const stateLabel = formatStateLabel(ticket?.state);

        if (!perAgent.has(agentName)) perAgent.set(agentName, makeHolder());
        recordEntity(perAgent.get(agentName), day, priorityName, stateLabel, deltaHours);

        const customerId = ticket?.customer_id;
        let customerLabel = (ticket?.customer || "").trim();
        if (customerId) {
          customerLabel = userById.get(customerId) || customerLabel || `cliente_${customerId}`;
        }
        if (customerLabel) {
          if (!perCustomer.has(customerLabel)) perCustomer.set(customerLabel, makeHolder());
          recordEntity(perCustomer.get(customerLabel), day, priorityName, stateLabel, deltaHours);
        }

        if (!perState.has(stateLabel)) perState.set(stateLabel, makeHolder());
        recordEntity(perState.get(stateLabel), day, priorityName, stateLabel, deltaHours);

        closedByDay.set(day, (closedByDay.get(day) || 0) + 1);
      } else if (OPEN_STATES.has(state)) {
        const createdDate = isoToDate(createdAt);
        if (!createdDate) continue;
        const day = createdDate.toISOString().slice(0, 10);
        if (day < fromDate) continue;

        openByDay.set(day, (openByDay.get(day) || 0) + 1);

        const priorityName = ticket?.priority || priorityById.get(ticket?.priority_id) || (ticket?.priority_id ? `priority_${ticket.priority_id}` : "unknown");
        const stateLabel = formatStateLabel(ticket?.state);

        if (ownerId) {
          const agentName = userById.get(ownerId) || AGENT_NAME_OVERRIDES.get(ownerId) || `id_${ownerId}`;
          if (!perAgent.has(agentName)) perAgent.set(agentName, makeHolder());
          recordEntity(perAgent.get(agentName), day, priorityName, stateLabel, null);
        }

        const customerId = ticket?.customer_id;
        let customerLabel = (ticket?.customer || "").trim();
        if (customerId) {
          customerLabel = userById.get(customerId) || customerLabel || `cliente_${customerId}`;
        }
        if (customerLabel) {
          if (!perCustomer.has(customerLabel)) perCustomer.set(customerLabel, makeHolder());
          recordEntity(perCustomer.get(customerLabel), day, priorityName, stateLabel, null);
        }

        if (!perState.has(stateLabel)) perState.set(stateLabel, makeHolder());
        recordEntity(perState.get(stateLabel), day, priorityName, stateLabel, null);
      }
    }

    const agentsJson = mapToJson(perAgent, holderToJson);
    const customersJson = mapToJson(perCustomer, holderToJson);
    const statesJson = mapToJson(perState, (holder) => ({
      overall: bucketToJson(holder.overall),
      priorities: mapToJson(holder.priorities, bucketToJson),
    }));

    const allDays = Array.from(new Set([...closedByDay.keys(), ...openByDay.keys()]));
    allDays.sort((a, b) => a.localeCompare(b));
    const dailySummary = Object.fromEntries(
      allDays.map((day) => [day, { closed: closedByDay.get(day) || 0, open: openByDay.get(day) || 0 }])
    );

    const body = JSON.stringify(
      {
        filters: { from_date: fromDate },
        agents: agentsJson,
        customers: customersJson,
        states: statesJson,
        daily_summary: dailySummary,
      },
      null,
      2
    );

    return {
      statusCode: 200,
      headers: jsonHeaders,
      body,
    };
  } catch (error) {
    console.error("fetch-metrics error", error);
    return buildError(500, error.message || "Unexpected error");
  }
};

exports.handler = handler;
