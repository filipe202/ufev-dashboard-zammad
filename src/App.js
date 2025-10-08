import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer
} from "recharts";
import "./index.css";
import { ZAMMAD_METRICS } from "./zammad_metrics";
const COLORS = [
  "#82B1FF", // azul lavanda
  "#FFAB91", // pêssego suave
  "#FFD54F", // amarelo mostarda clara
  "#81C784", // verde menta médio
  "#BA68C8", // lilás médio
  "#4DD0E1", // turquesa clara
  "#F48FB1", // rosa suave
  "#A1887F", // taupe quente
  "#90CAF9", // azul claro
  "#FFCC80", // laranja pastel forte
];


function emptyBucket() {
  return { avg_time_hours: null, tickets_count: 0, tickets_per_day: {} };
}

function cloneBucket(bucket) {
  if (!bucket) return emptyBucket();
  return {
    avg_time_hours: typeof bucket.avg_time_hours === "number" ? bucket.avg_time_hours : null,
    tickets_count: bucket.tickets_count ?? 0,
    tickets_per_day: { ...(bucket.tickets_per_day || {}) },
  };
}

function mergeBuckets(buckets) {
  const accPerDay = {};
  let totalTickets = 0;
  let weightedHours = 0;

  buckets.forEach((bucket) => {
    if (!bucket) return;
    const ticketsCount = bucket.tickets_count ?? 0;
    totalTickets += ticketsCount;
    if (typeof bucket.avg_time_hours === "number" && ticketsCount > 0) {
      weightedHours += bucket.avg_time_hours * ticketsCount;
    }
    Object.entries(bucket.tickets_per_day || {}).forEach(([day, count]) => {
      accPerDay[day] = (accPerDay[day] || 0) + (count || 0);
    });
  });

  const avg = totalTickets > 0 ? weightedHours / totalTickets : null;
  return {
    avg_time_hours: avg,
    tickets_count: totalTickets,
    tickets_per_day: accPerDay,
  };
}

function mergePriorityBuckets(payload, selectedPriorities) {
  if (!payload) return emptyBucket();
  const buckets = selectedPriorities
    .map((priority) => payload.priorities?.[priority])
    .filter(Boolean);
  if (!buckets.length) return emptyBucket();
  return mergeBuckets(buckets);
}

function computeBucketForPayload(payload, selectedPriorities, selectedStates) {
  if (!payload) return emptyBucket();
  const useAllPriorities = !selectedPriorities?.length || selectedPriorities.includes("ALL");
  const hasStateBreakdown = !!payload.states;
  const useAllStates = !selectedStates?.length || selectedStates.includes("ALL") || !hasStateBreakdown;

  if (useAllStates && useAllPriorities) {
    return cloneBucket(payload.overall);
  }

  if (useAllStates && !useAllPriorities) {
    return mergePriorityBuckets(payload, selectedPriorities);
  }

  const stateMap = payload.states || {};
  const buckets = [];
  selectedStates.forEach((stateLabel) => {
    const statePayload = stateMap[stateLabel];
    if (!statePayload) return;
    if (useAllPriorities) {
      buckets.push(statePayload.overall);
    } else {
      selectedPriorities.forEach((priority) => {
        const bucket = statePayload.priorities?.[priority];
        if (bucket) buckets.push(bucket);
      });
    }
  });

  if (!buckets.length) return emptyBucket();
  return mergeBuckets(buckets);
}

function computeRowsFromGroups(groupsObj, selectedPriorities, selectedStates) {
  if (!groupsObj) return [];
  return Object.entries(groupsObj).map(([label, payload]) => {
    const bucket = computeBucketForPayload(payload, selectedPriorities, selectedStates);
    return {
      label,
      avg_time_hours: bucket.avg_time_hours ?? null,
      tickets_count: bucket.tickets_count ?? 0,
      perDay: bucket.tickets_per_day || {}
    };
  });
}

function allDatesFromGroups(groupsObj, selectedPriorities, selectedStates) {
  const set = new Set();
  Object.values(groupsObj || {}).forEach(payload => {
    const bucket = computeBucketForPayload(payload, selectedPriorities, selectedStates);
    Object.keys(bucket.tickets_per_day || {}).forEach(d => set.add(d));
  });
  return Array.from(set).sort();
}

function toStackedSeries(days, rows) {
  return days.map((d) => {
    const obj = { day: d };
    rows.forEach((r) => { obj[r.label] = r.perDay?.[d] ?? 0; });
    return obj;
  });
}

function summarize(rows) {
  const totalTickets = rows.reduce((s, r) => s + (r.tickets_count || 0), 0);
  const vals = rows.filter(r => typeof r.avg_time_hours === "number");
  const avgAll = vals.length ? (vals.reduce((s,r)=>s+r.avg_time_hours,0) / vals.length) : 0;
  const eligible = rows.filter(r => (r.tickets_count||0) >= 3 && typeof r.avg_time_hours === "number");
  const top = eligible.sort((a,b)=>a.avg_time_hours - b.avg_time_hours)[0] || null;
  return { totalTickets, avgAll, top };
}

function MultiSelect({ options, selected, onChange, placeholder }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const toggleValue = (value) => {
    let next;
    if (value === "ALL") {
      next = ["ALL"];
    } else {
      const withoutAll = selected.filter((v) => v !== "ALL");
      if (withoutAll.includes(value)) {
        next = withoutAll.filter((v) => v !== value);
      } else {
        next = [...withoutAll, value];
      }
      if (!next.length) {
        next = ["ALL"];
      }
    }
    onChange(next);
  };

  const displayValue = () => {
    if (!selected?.length || selected.includes("ALL")) {
      return placeholder || "ALL";
    }
    if (selected.length === 1) return selected[0];
    return `${selected.length} selecionados`;
  };

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        style={{
          width: "100%",
          padding: "10px 12px",
          borderRadius: 8,
          border: "1px solid #cbd5f5",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          background: "#fff",
          cursor: "pointer",
          fontSize: 14,
        }}
      >
        <span style={{ color: "#1f2937", fontWeight: 500 }}>{displayValue()}</span>
        <span style={{ fontSize: 12, color: "#64748b" }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            zIndex: 10,
            background: "#fff",
            border: "1px solid #cbd5f5",
            borderRadius: 8,
            boxShadow: "0 10px 25px rgba(15, 23, 42, 0.12)",
            maxHeight: 220,
            overflowY: "auto",
          }}
        >
          {options.map((option) => {
            const checked = selected.includes(option) || (option === "ALL" && (!selected.length || selected.includes("ALL")));
            return (
              <label
                key={option}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "10px 12px",
                  fontSize: 14,
                  cursor: "pointer",
                  borderBottom: "1px solid #f1f5f9",
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleValue(option)}
                  style={{ accentColor: "#2563eb" }}
                />
                <span style={{ color: "#1f2937" }}>{option}</span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState(null);           // estrutura { filters, agents, customers, daily_summary }
  const [viewMode, setViewMode] = useState("agents");
  const [selectedPriorities, setSelectedPriorities] = useState(["ALL"]);
  const [selectedStates, setSelectedStates] = useState(["ALL"]);
  const [sortKey, setSortKey] = useState("tickets"); // "tickets" | "avg"
  const [selectedGroups, setSelectedGroups] = useState(["ALL"]);
  const [error, setError] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const fromDateRef = useRef("");

  const setFromDateSynced = useCallback((value) => {
    fromDateRef.current = value;
  }, []);

  const fetchMetrics = useCallback(async (dateOverride) => {
    setError(null);
    try {
      // Usar dados importados em vez de fetch para proteger acesso
      const payload = ZAMMAD_METRICS;
      setData(payload);
      if (payload?.filters?.from_date) {
        setFromDateSynced(payload.filters.from_date);
      }
    } catch (err) {
      setError(err.message || String(err));
    }
  }, [setFromDateSynced]);

  useEffect(() => {
    // Verificar autenticação ao carregar
    const savedAuth = sessionStorage.getItem('ufev_dashboard_auth');
    if (savedAuth === 'authenticated') {
      setIsAuthenticated(true);
      fetchMetrics();
    }
  }, [fetchMetrics]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchMetrics();
    }
  }, [isAuthenticated, fetchMetrics]);

  useEffect(() => {
    setSelectedGroups(["ALL"]);
    setSelectedPriorities(["ALL"]);
    setSelectedStates(["ALL"]);
  }, [viewMode]);

  const dataset = useMemo(() => {
    if (!data) return null;
    const customers = data.customers || {};
    const filterCustomers = (predicate) =>
      Object.fromEntries(Object.entries(customers).filter(([label]) => predicate(label)));
    const isFam = (label) => label?.toLowerCase().endsWith("@familiaemviagem.com");

    if (viewMode === "agents") {
      return data.agents;
    }
    if (viewMode === "customers") {
      return filterCustomers(isFam);
    }
    if (viewMode === "operators") {
      return filterCustomers(label => !isFam(label));
    }
    if (viewMode === "states") {
      return data.states;
    }
    return data.agents;
  }, [data, viewMode]);

  const priorities = useMemo(() => {
    const set = new Set(["ALL"]);
    Object.values(dataset || {}).forEach(a => {
      Object.keys(a.priorities || {}).forEach(p => set.add(p));
    });
    const list = Array.from(set);
    const allIndex = list.indexOf("ALL");
    if (allIndex >= 0) {
      list.splice(allIndex, 1);
    }
    list.sort((a, b) => a.localeCompare(b, "pt", { numeric: true, sensitivity: "accent" }));
    return ["ALL", ...list];
  }, [dataset]);

  const stateOptions = useMemo(() => {
    const set = new Set(["ALL"]);
    Object.entries(dataset || {}).forEach(([label, payload]) => {
      if (viewMode === "states") {
        set.add(label);
      }
      Object.keys(payload.states || {}).forEach(state => set.add(state));
    });
    const list = Array.from(set);
    const allIndex = list.indexOf("ALL");
    if (allIndex >= 0) {
      list.splice(allIndex, 1);
    }
    list.sort((a, b) => a.localeCompare(b, "pt", { sensitivity: "accent" }));
    return ["ALL", ...list];
  }, [dataset, viewMode]);

  const groupOptions = useMemo(() => {
    if (!dataset || viewMode === "states") return ["ALL"];
    const names = Object.keys(dataset).sort((a, b) => a.localeCompare(b, "pt", { sensitivity: "accent" }));
    return ["ALL", ...names];
  }, [dataset, viewMode]);

  const days = useMemo(() => dataset ? allDatesFromGroups(dataset, selectedPriorities, selectedStates) : [], [dataset, selectedPriorities, selectedStates]);

  const rows = useMemo(() => {
    if (!dataset) return [];
    const bucketStates = viewMode === "states" ? ["ALL"] : selectedStates;
    let list = computeRowsFromGroups(dataset, selectedPriorities, bucketStates);

    if (viewMode === "states") {
      const useAllStates = !selectedStates?.length || selectedStates.includes("ALL");
      if (!useAllStates) {
        const setStates = new Set(selectedStates);
        list = list.filter(r => setStates.has(r.label));
      }
    } else {
      const useAllGroups = !selectedGroups?.length || selectedGroups.includes("ALL");
      if (!useAllGroups) {
        const setGroups = new Set(selectedGroups);
        list = list.filter(r => setGroups.has(r.label));
      }
    }
    list.sort((a,b) => {
      if (sortKey === "tickets") return (b.tickets_count||0) - (a.tickets_count||0);
      const avga = a.avg_time_hours ?? Infinity;
      const avgb = b.avg_time_hours ?? Infinity;
      return avga - avgb;
    });
    return list;
  }, [dataset, selectedPriorities, selectedStates, selectedGroups, sortKey, viewMode]);

  const series = useMemo(() => toStackedSeries(days, rows), [days, rows]);
  const kpis = useMemo(() => summarize(rows), [rows]);

  const groupLabel = {
    agents: "Agente",
    customers: "Cliente",
    operators: "Operador",
    states: "Estado",
    workload: "Período",
  }[viewMode] || "Grupo";

  // Tela de login
  const handleLogin = () => {
    const password = prompt("Palavra-passe para aceder ao dashboard UFEV:");
    if (password === "ufev2024") { // Alterar para senha desejada
      setIsAuthenticated(true);
      sessionStorage.setItem('ufev_dashboard_auth', 'authenticated');
    } else if (password !== null) {
      alert("Palavra-passe incorreta!");
    }
  };

  if (!isAuthenticated) {
    return (
      <div style={{
        maxWidth: 400, 
        margin: "100px auto", 
        padding: "32px", 
        fontFamily: "system-ui, Arial",
        textAlign: "center",
        border: "1px solid #ddd",
        borderRadius: "8px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.1)"
      }}>
        <img src="logo.svg" alt="UFEV" style={{height: 64, marginBottom: 24}} />
        <h2>Dashboard UFEV</h2>
        <p style={{color: "#666", marginBottom: 24}}>Acesso restrito - necessária autenticação</p>
        <button 
          onClick={handleLogin}
          style={{
            padding: "12px 24px",
            backgroundColor: "#007bff",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "16px"
          }}
        >
          Fazer Login
        </button>
      </div>
    );
  }

  // Renderizar análise temporal
  if (viewMode === "workload" && data?.workload_analysis) {
    const workload = data.workload_analysis;
    
    // Dados para gráfico de barras por dia da semana
    const weekdayData = Object.entries(workload.by_weekday).map(([day, count]) => ({
      name: day,
      tickets: count
    }));
    
    // Dados para gráfico de barras por hora
    const hourData = Object.entries(workload.by_hour).map(([hour, count]) => ({
      name: hour,
      tickets: count
    }));

    return (
      <div style={{maxWidth: 1200, margin: "20px auto", padding: "0 16px", fontFamily: "system-ui, Arial"}}>
        <div style={{display:"flex", alignItems:"center", gap:12, marginBottom:16}}>
          <img src="logo.svg" alt="UFEV" style={{height:48, objectFit:"contain"}} />
          <h1 style={{fontSize:24, fontWeight:600, color:"#005A8D", margin:0, flex:1}}>
            Análise Temporal - Carga de Trabalho
          </h1>
          <button 
            onClick={() => {
              setIsAuthenticated(false);
              sessionStorage.removeItem('ufev_dashboard_auth');
            }}
            style={{
              padding: "8px 16px",
              backgroundColor: "#dc3545",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "14px"
            }}
          >
            Logout
          </button>
        </div>
        
        <div style={{display:"flex", gap:8, marginBottom:16}}>
          {[
            { value: "agents", label: "Por agentes" },
            { value: "states", label: "Por estados" },
            { value: "workload", label: "Análise Temporal" },
          ].map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => setViewMode(option.value)}
              style={{
                padding:"8px 16px",
                borderRadius:999,
                border:"1px solid",
                borderColor: viewMode === option.value ? "#005A8D" : "#e2e8f0",
                backgroundColor: viewMode === option.value ? "#005A8D" : "white",
                color: viewMode === option.value ? "white" : "#64748b",
                cursor:"pointer"
              }}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24}}>
          <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
            <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>Tickets por Dia da Semana</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={weekdayData}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="tickets" fill="#005A8D" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          
          <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
            <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>Tickets por Hora do Dia</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={hourData}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="tickets" fill="#28a745" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
          <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>
            Resumo da Análise ({workload.total_tickets} tickets analisados)
          </h3>
          <div style={{display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16}}>
            <div style={{padding: 16, backgroundColor: "#f8f9fa", borderRadius: 6}}>
              <div style={{fontSize: 14, color: "#6b7280", marginBottom: 4}}>Dia mais movimentado</div>
              <div style={{fontSize: 18, fontWeight: 600, color: "#1f2937"}}>
                {Object.entries(workload.by_weekday).reduce((a, b) => workload.by_weekday[a[0]] > workload.by_weekday[b[0]] ? a : b)[0]}
              </div>
            </div>
            <div style={{padding: 16, backgroundColor: "#f8f9fa", borderRadius: 6}}>
              <div style={{fontSize: 14, color: "#6b7280", marginBottom: 4}}>Hora de pico</div>
              <div style={{fontSize: 18, fontWeight: 600, color: "#1f2937"}}>
                {Object.entries(workload.by_hour).reduce((a, b) => workload.by_hour[a[0]] > workload.by_hour[b[0]] ? a : b)[0]}
              </div>
            </div>
            <div style={{padding: 16, backgroundColor: "#f8f9fa", borderRadius: 6}}>
              <div style={{fontSize: 14, color: "#6b7280", marginBottom: 4}}>Período analisado</div>
              <div style={{fontSize: 18, fontWeight: 600, color: "#1f2937"}}>
                Desde {data.filters.from_date}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{maxWidth: 1200, margin: "20px auto", padding: "0 16px", fontFamily: "system-ui, Arial"}}>
<div style={{display:"flex", alignItems:"center", gap:12, marginBottom:16}}>
  <img
    src="logo.svg"
    alt="UFEV"
    style={{height:48, objectFit:"contain"}}
  />
  <h1 style={{fontSize:24, fontWeight:600, color:"#005A8D", margin:0, flex:1}}>
    Dashboard de Suporte
  </h1>
  <button 
    onClick={() => {
      setIsAuthenticated(false);
      sessionStorage.removeItem('ufev_dashboard_auth');
    }}
    style={{
      padding: "8px 16px",
      backgroundColor: "#dc3545",
      color: "white",
      border: "none",
      borderRadius: "4px",
      cursor: "pointer",
      fontSize: "14px"
    }}
  >
    Logout
  </button>
</div>
      <div style={{display:"flex", gap:8, marginBottom:16}}>
        {[
          { value: "agents", label: "Por agentes" },
          { value: "states", label: "Por estados" },
          { value: "workload", label: "Análise Temporal" },
        ].map(option => (
          <button
            key={option.value}
            type="button"
            onClick={() => setViewMode(option.value)}
            style={{
              padding:"8px 16px",
              borderRadius:999,
              border:"1px solid",
              borderColor: viewMode === option.value ? "#005A8D" : "#e2e8f0",
              background: viewMode === option.value ? "#005A8D" : "#fff",
              color: viewMode === option.value ? "#fff" : "#334155",
              fontWeight:600,
              cursor:"pointer"
            }}
          >
            {option.label}
          </button>
        ))}
      </div>
      {/* Controles */}
      <div style={{display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px,1fr))", gap: 12, marginBottom: 12}}>
        <div>
          <label style={{fontSize: 12, color: "#555"}}>Prioridade</label>
          <MultiSelect
            options={priorities}
            selected={selectedPriorities}
            onChange={setSelectedPriorities}
            placeholder="Selecione prioridades"
          />
        </div>
        <div>
          <label style={{fontSize: 12, color: "#555"}}>Estado</label>
          <MultiSelect
            options={stateOptions}
            selected={selectedStates}
            onChange={setSelectedStates}
            placeholder="Selecione estados"
          />
        </div>
   
        {viewMode !== "states" && (
          <div>
            <label style={{fontSize: 12, color: "#555"}}>Filtrar por {groupLabel.toLowerCase()}</label>
            <MultiSelect
              options={groupOptions}
              selected={selectedGroups}
              onChange={setSelectedGroups}
              placeholder={
                viewMode === "agents"
                  ? "Selecione agentes"
                  : viewMode === "customers"
                    ? "Selecione clientes"
                    : "Selecione operadores"
              }
            />
          </div>
        )}
             <div>
          <label style={{fontSize: 12, color: "#555"}}>Ordenar por</label>
          <select value={sortKey} onChange={e=>setSortKey(e.target.value)} style={{width:"100%", padding:8, borderRadius:8}}>
            <option value="tickets"># Tickets</option>
            <option value="avg">Média (horas) ↑</option>
          </select>
        </div>
      </div>

      {error && <div style={{color:"#b91c1c", marginBottom:12}}>Erro a carregar JSON: {error}</div>}

      {/* KPIs */}
      <div style={{display:"grid", gridTemplateColumns:"repeat(3, minmax(0,1fr))", gap:12, margin:"12px 0"}}>
        <div style={{borderTop:"4px solid #0096D6", border:"1px solid #eee", borderRadius:10, padding:16}}>
          <div style={{fontSize:12, color:"#666"}}>Tickets (total)</div>
          <div style={{fontSize:28, fontWeight:600}}>{kpis.totalTickets || 0}</div>
        </div>
        <div style={{borderTop:"4px solid #F47C20", border:"1px solid #eee", borderRadius:10, padding:16}}>
          <div style={{fontSize:12, color:"#666"}}>Média geral (horas)</div>
          <div style={{fontSize:28, fontWeight:600}}>{kpis.avgAll ? kpis.avgAll.toFixed(2) : "—"}</div>
        </div>
        <div style={{borderTop:"4px solid #005A8D", border:"1px solid #eee", borderRadius:10, padding:16}}>
          <div style={{fontSize:12, color:"#666"}}>Top performer (mín. 3 tickets)</div>
          <div style={{fontSize:18, fontWeight:600}}>
            {kpis.top ? `${kpis.top.label} · ${kpis.top.avg_time_hours.toFixed(2)}h` : "—"}
          </div>
        </div>
      </div>

      {/* Gráfico */}
      <div style={{border:"1px solid #eee", borderRadius:10, padding:12, marginBottom:12}}>
        <div style={{display:"flex", alignItems:"center", gap:8, margin:"4px 0 8px 4px"}}>
          <div style={{width:8, height:24, background:"#0096D6", borderRadius:4}}/>
          <h2 style={{margin:0, fontSize:16, color:"#005A8D"}}>Tickets por dia</h2>
        </div>
        <div style={{width:"100%", height:380}}>
          <ResponsiveContainer>
            <BarChart data={series}>
              <XAxis dataKey="day" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend />
              {rows.map((r, i) => (
                <Bar key={r.label} dataKey={r.label} stackId="a" fill={COLORS[i % COLORS.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Tabela */}
      <div style={{border:"1px solid #eee", borderRadius:10, overflowX:"auto"}}>
        <table style={{width:"100%", borderCollapse:"collapse", fontSize:14}}>
          <thead>
            <tr style={{background:"#f9fafb", color:"#475569"}}>
              <th style={{textAlign:"left", padding:10}}>{groupLabel}</th>
              <th style={{textAlign:"right", padding:10}}># Tickets</th>
              <th style={{textAlign:"right", padding:10}}>Média (h)</th>
              {days.map(d => (
                <th key={d} style={{textAlign:"center", padding:10, whiteSpace:"nowrap"}}>{d}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, idx) => (
              <tr key={r.label} style={{background: idx%2 ? "#fff" : "#f8fafc"}}>
                <td style={{padding:10, fontWeight:600}}>{r.label}</td>
                <td style={{padding:10, textAlign:"right"}}>{r.tickets_count ?? 0}</td>
                <td style={{padding:10, textAlign:"right"}}>{typeof r.avg_time_hours === "number" ? r.avg_time_hours.toFixed(2) : "—"}</td>
                {days.map(d => (
                  <td key={d} style={{padding:10, textAlign:"center"}}>{r.perDay?.[d] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{fontSize:12, color:"#64748b", marginTop:8}}>
        Os dados são carregados em tempo-real através da function serverless <code>fetch-metrics</code>.
      </div>
    </div>
  );
}
