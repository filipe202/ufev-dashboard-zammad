import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./index.css";
import { ZAMMAD_METRICS } from "./zammad_metrics";

// Hook para detectar mobile
const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  return isMobile;
};
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

function summarize(rows, efficiencyData = null) {
  const totalTickets = rows.reduce((s, r) => s + (r.tickets_count || 0), 0);
  const vals = rows.filter(r => typeof r.avg_time_hours === "number");
  const avgAll = vals.length ? (vals.reduce((s,r)=>s+r.avg_time_hours,0) / vals.length) : 0;
  
  // Calcular limite dinâmico: 10% do total de tickets, com mínimo de 5 e máximo de 50
  const dynamicMinTickets = Math.max(5, Math.min(50, Math.ceil(totalTickets * 0.1)));
  
  const eligible = rows.filter(r => (r.tickets_count||0) >= dynamicMinTickets && typeof r.avg_time_hours === "number" && r.label !== "Não Atribuído");
  
  // Top por tempo (menor tempo médio)
  const topTime = eligible.sort((a,b)=>a.avg_time_hours - b.avg_time_hours)[0] || null;
  
  // Top por eficiência (tickets fechados / tickets atribuídos)
  let topRatio = null;
  if (efficiencyData) {
    const efficiencyEligible = Object.entries(efficiencyData)
      .filter(([agent, data]) => data.tickets_closed >= dynamicMinTickets && agent !== "Não Atribuído")
      .map(([agent, data]) => {
        // Encontrar dados do agente nos dados principais
        const agentData = rows.find(r => r.label === agent);
        
        // tickets_count nos dados principais = total de tickets atribuídos (abertos + fechados)
        // tickets_closed no agent_efficiency = tickets efetivamente fechados
        const tickets_assigned = agentData?.tickets_count || 0;
        const tickets_closed = data.tickets_closed;
        
        // Calcular eficiência real, mas limitar a 100%
        let efficiency_ratio = 0;
        if (tickets_assigned > 0) {
          efficiency_ratio = Math.min(tickets_closed / tickets_assigned, 1.0);
        }
        
        // Debug para casos anómalos
        if (tickets_closed > tickets_assigned) {
          console.warn(`${agent}: ${tickets_closed} fechados > ${tickets_assigned} atribuídos - limitando a 100%`);
        }
        
        return {
          label: agent,
          tickets_closed: tickets_closed,
          tickets_assigned: tickets_assigned,
          efficiency_ratio: efficiency_ratio
        };
      })
      .filter(item => item.tickets_assigned > 0); // Só incluir quem tem tickets atribuídos
    
    topRatio = efficiencyEligible.sort((a,b) => b.efficiency_ratio - a.efficiency_ratio)[0] || null;
  } else {
    // Fallback: usar tickets_count como proxy
    topRatio = eligible.sort((a,b)=>b.tickets_count - a.tickets_count)[0] || null;
  }
  
  return { totalTickets, avgAll, topTime, topRatio, dynamicMinTickets };
}

// Componente para filtro de datas
function DateFilter({ selected, onChange }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  const dateOptions = [
    { value: "all", label: "Todos os dados" },
    { value: "6months", label: "Últimos 6 meses" },
    { value: "1month", label: "Último mês" },
    { value: "15days", label: "Últimos 15 dias" },
    { value: "7days", label: "Última semana" }
  ];

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

  const selectedOption = dateOptions.find(opt => opt.value === selected) || dateOptions[0];

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
        <span style={{ color: "#1f2937", fontWeight: 500 }}>{selectedOption.label}</span>
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
          {dateOptions.map((option) => (
            <button
              key={option.value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 12px",
                fontSize: 14,
                cursor: "pointer",
                border: "none",
                background: selected === option.value ? "#f1f5f9" : "transparent",
                color: "#1f2937",
                textAlign: "left",
                borderBottom: "1px solid #f1f5f9",
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
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
  const [selectedPriorities, setSelectedPriorities] = useState(["ALL"]);
  const [selectedStates, setSelectedStates] = useState(["ALL"]);
  const [sortKey, setSortKey] = useState("tickets"); // "tickets" | "avg"
  const [selectedGroups, setSelectedGroups] = useState(["ALL"]);
  const [error, setError] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [selectedDateFilter, setSelectedDateFilter] = useState("all"); // Novo estado para filtro de data
  const fromDateRef = useRef("");
  const isMobile = useIsMobile();

  // Roteamento baseado na URL
  const getViewModeFromURL = () => {
    const hash = window.location.hash.slice(1); // Remove o #
    const baseHash = hash.split('?')[0];
    const validModes = ["agents", "states", "responses", "efficiency", "workload", "state_changes"];
    return validModes.includes(baseHash) ? baseHash : "agents";
  };

  const getWorkloadModeFromURL = () => {
    const hash = window.location.hash.slice(1);
    const params = new URLSearchParams(hash.split('?')[1] || '');
    const mode = params.get('mode');
    return mode === 'closed' ? 'closed' : 'created';
  };

  const [workloadMode, setWorkloadMode] = useState(getWorkloadModeFromURL());

  const [viewMode, setViewMode] = useState(getViewModeFromURL());

  const updateViewMode = (mode) => {
    setViewMode(mode);
    window.location.hash = mode;
  };

  const updateWorkloadMode = (mode) => {
    setWorkloadMode(mode);
    // Adicionar parâmetro de workload mode na URL
    const baseHash = window.location.hash.split('?')[0];
    window.location.hash = `${baseHash}?mode=${mode}`;
  };

  const setFromDateSynced = useCallback((value) => {
    fromDateRef.current = value;
  }, []);

  // Função para calcular a data de corte baseada no filtro selecionado
  const getDateCutoff = useCallback((filterType) => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    
    switch (filterType) {
      case "7days":
        return new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      case "15days":
        return new Date(today.getTime() - 15 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      case "1month":
        const oneMonthAgo = new Date(today);
        oneMonthAgo.setMonth(oneMonthAgo.getMonth() - 1);
        return oneMonthAgo.toISOString().split('T')[0];
      case "6months":
        const sixMonthsAgo = new Date(today);
        sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
        return sixMonthsAgo.toISOString().split('T')[0];
      case "all":
      default:
        return null; // Sem filtro de data
    }
  }, []);

  // Função para filtrar dados baseado na data
  const filterDataByDate = useCallback((originalData, dateFilter) => {
    if (!originalData || dateFilter === "all") {
      return originalData;
    }

    const cutoffDate = getDateCutoff(dateFilter);
    if (!cutoffDate) {
      return originalData;
    }

    const filterBucketByDate = (bucket) => {
      if (!bucket || !bucket.tickets_per_day) {
        return bucket;
      }

      const filteredTicketsPerDay = {};
      let filteredCount = 0;

      Object.entries(bucket.tickets_per_day).forEach(([date, count]) => {
        if (date >= cutoffDate) {
          filteredTicketsPerDay[date] = count;
          filteredCount += count;
        }
      });

      return {
        ...bucket,
        tickets_per_day: filteredTicketsPerDay,
        tickets_count: filteredCount
      };
    };

    const filterEntityData = (entityData) => {
      const filtered = {};
      
      Object.entries(entityData).forEach(([entityName, entityBuckets]) => {
        filtered[entityName] = {
          overall: filterBucketByDate(entityBuckets.overall),
          priorities: {},
          states: {}
        };

        // Filtrar prioridades
        if (entityBuckets.priorities) {
          Object.entries(entityBuckets.priorities).forEach(([priority, bucket]) => {
            filtered[entityName].priorities[priority] = filterBucketByDate(bucket);
          });
        }

        // Filtrar estados
        if (entityBuckets.states) {
          Object.entries(entityBuckets.states).forEach(([state, stateData]) => {
            filtered[entityName].states[state] = {
              overall: filterBucketByDate(stateData.overall),
              priorities: {}
            };
            
            if (stateData.priorities) {
              Object.entries(stateData.priorities).forEach(([priority, bucket]) => {
                filtered[entityName].states[state].priorities[priority] = filterBucketByDate(bucket);
              });
            }
          });
        }
      });

      return filtered;
    };

    // Filtrar daily_summary
    const filteredDailySummary = {};
    if (originalData.daily_summary) {
      Object.entries(originalData.daily_summary).forEach(([date, summary]) => {
        if (date >= cutoffDate) {
          filteredDailySummary[date] = summary;
        }
      });
    }

    return {
      ...originalData,
      agents: filterEntityData(originalData.agents || {}),
      customers: filterEntityData(originalData.customers || {}),
      states: originalData.states ? Object.fromEntries(
        Object.entries(originalData.states).map(([state, stateData]) => [
          state,
          {
            overall: filterBucketByDate(stateData.overall),
            priorities: Object.fromEntries(
              Object.entries(stateData.priorities || {}).map(([priority, bucket]) => [
                priority,
                filterBucketByDate(bucket)
              ])
            )
          }
        ])
      ) : {},
      daily_summary: filteredDailySummary
    };
  }, [getDateCutoff]);

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

    // Listener para mudanças na URL (botão voltar/avançar)
    const handleHashChange = () => {
      setViewMode(getViewModeFromURL());
      setWorkloadMode(getWorkloadModeFromURL());
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
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
    
    // Aplicar filtro de data aos dados
    const filteredData = filterDataByDate(data, selectedDateFilter);
    
    const customers = filteredData.customers || {};
    const filterCustomers = (predicate) =>
      Object.fromEntries(Object.entries(customers).filter(([label]) => predicate(label)));
    const isFam = (label) => label?.toLowerCase().endsWith("@familiaemviagem.com");

    if (viewMode === "agents") {
      return filteredData.agents;
    }
    if (viewMode === "customers") {
      return filterCustomers(isFam);
    }
    if (viewMode === "operators") {
      return filterCustomers(label => !isFam(label));
    }
    if (viewMode === "states") {
      return filteredData.states;
    }
    return filteredData.agents;
  }, [data, viewMode, selectedDateFilter, filterDataByDate]);

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
  const kpis = useMemo(() => summarize(rows, data?.agent_efficiency), [rows, data?.agent_efficiency]);

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

  // Renderizar respostas por agente
  if (viewMode === "responses" && data?.agent_responses) {
    const responsesData = Object.entries(data.agent_responses).map(([agent, count]) => ({
      name: agent,
      respostas: count
    }));

    const totalResponses = Object.values(data.agent_responses).reduce((sum, count) => sum + count, 0);

    return (
      <div style={{maxWidth: 1200, margin: isMobile ? "10px auto" : "20px auto", padding: isMobile ? "0 8px" : "0 16px", fontFamily: "system-ui, Arial"}}>
        <div style={{display:"flex", alignItems:"center", gap:12, marginBottom:16}}>
          <img src="logo.svg" alt="UFEV" style={{height:48, objectFit:"contain"}} />
          <h1 style={{fontSize:24, fontWeight:600, color:"#005A8D", margin:0, flex:1}}>
            Respostas por Agente
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
            { value: "responses", label: "Respostas por Agente" },
            { value: "efficiency", label: "Eficiência por Agente" },
            { value: "state_changes", label: "Trocas de Estado" },
            { value: "workload", label: "Análise Temporal" },
          ].map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => updateViewMode(option.value)}
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

        {/* Filtro de período */}
        <div style={{marginBottom: 16}}>
          <div style={{display: "flex", gap: 12, alignItems: "end"}}>
            <div style={{minWidth: 200}}>
              <label style={{fontSize: 12, color: "#555", display: "block", marginBottom: 4}}>Filtrar por Período</label>
              <DateFilter
                selected={selectedDateFilter}
                onChange={setSelectedDateFilter}
              />
            </div>
            <div style={{fontSize: 12, color: "#6b7280", padding: "8px 0"}}>
              {selectedDateFilter !== "all" && (
                <span>
                  📅 Mostrando dados desde {getDateCutoff(selectedDateFilter)}
                </span>
              )}
            </div>
          </div>
        </div>

        <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: 24}}>
          <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>
            Número de Respostas por Agente ({totalResponses} respostas analisadas)
          </h3>
          <div style={{height: 400, overflowY: "auto"}}>
            {responsesData.map((agent, index) => {
              const maxValue = Math.max(...responsesData.map(a => a.respostas));
              const percentage = (agent.respostas / maxValue) * 100;
              return (
                <div key={agent.name} style={{
                  display: "flex",
                  alignItems: "center",
                  marginBottom: 12,
                  gap: 12
                }}>
                  <div style={{
                    minWidth: 120,
                    textAlign: "right",
                    fontSize: 14,
                    fontWeight: 500
                  }}>
                    {agent.name}
                  </div>
                  <div style={{
                    flex: 1,
                    height: 24,
                    backgroundColor: "#f1f5f9",
                    borderRadius: 12,
                    position: "relative",
                    overflow: "hidden"
                  }}>
                    <div style={{
                      width: `${percentage}%`,
                      height: "100%",
                      backgroundColor: "#17a2b8",
                      borderRadius: 12,
                      transition: "width 0.5s ease"
                    }} />
                    <span style={{
                      position: "absolute",
                      right: 8,
                      top: "50%",
                      transform: "translateY(-50%)",
                      fontSize: 12,
                      fontWeight: 600,
                      color: percentage > 50 ? "white" : "#374151"
                    }}>
                      {agent.respostas}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
          <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>Ranking de Respostas</h3>
          <div style={{display: "grid", gap: 8}}>
            {responsesData.map((agent, index) => (
              <div key={agent.name} style={{
                display: "flex", 
                justifyContent: "space-between", 
                alignItems: "center",
                padding: "12px 16px",
                backgroundColor: index < 3 ? "#f8f9fa" : "transparent",
                borderRadius: 6,
                border: index < 3 ? "1px solid #e9ecef" : "none"
              }}>
                <div style={{display: "flex", alignItems: "center", gap: 8}}>
                  <span style={{
                    fontSize: 18,
                    fontWeight: 600,
                    color: index === 0 ? "#ffd700" : index === 1 ? "#c0c0c0" : index === 2 ? "#cd7f32" : "#6b7280",
                    minWidth: 24
                  }}>
                    {index + 1}º
                  </span>
                  <span style={{fontWeight: 500}}>{agent.name}</span>
                </div>
                <span style={{
                  fontSize: 16,
                  fontWeight: 600,
                  color: "#005A8D",
                  backgroundColor: "#e3f2fd",
                  padding: "4px 12px",
                  borderRadius: 12
                }}>
                  {agent.respostas} respostas
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Renderizar eficiência por agente
  if (viewMode === "efficiency" && data?.agent_efficiency) {
    const efficiencyData = Object.entries(data.agent_efficiency).map(([agent, data]) => ({
      name: agent,
      interacoes: data.avg_interactions_per_ticket,
      tickets: data.tickets_closed,
      total_interacoes: data.total_interactions
    }));

    return (
      <div style={{maxWidth: 1200, margin: isMobile ? "10px auto" : "20px auto", padding: isMobile ? "0 8px" : "0 16px", fontFamily: "system-ui, Arial"}}>
        <div style={{display:"flex", alignItems:"center", gap:12, marginBottom:16}}>
          <img src="logo.svg" alt="UFEV" style={{height:48, objectFit:"contain"}} />
          <h1 style={{fontSize:24, fontWeight:600, color:"#005A8D", margin:0, flex:1}}>
            Eficiência por Agente
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
            { value: "responses", label: "Respostas por Agente" },
            { value: "efficiency", label: "Eficiência por Agente" },
            { value: "state_changes", label: "Trocas de Estado" },
            { value: "workload", label: "Análise Temporal" },
          ].map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => updateViewMode(option.value)}
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

        {/* Filtro de período */}
        <div style={{marginBottom: 16}}>
          <div style={{display: "flex", gap: 12, alignItems: "end"}}>
            <div style={{minWidth: 200}}>
              <label style={{fontSize: 12, color: "#555", display: "block", marginBottom: 4}}>Filtrar por Período</label>
              <DateFilter
                selected={selectedDateFilter}
                onChange={setSelectedDateFilter}
              />
            </div>
            <div style={{fontSize: 12, color: "#6b7280", padding: "8px 0"}}>
              {selectedDateFilter !== "all" && (
                <span>
                  📅 Mostrando dados desde {getDateCutoff(selectedDateFilter)}
                </span>
              )}
            </div>
          </div>
        </div>

        <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: 24}}>
          <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>
            Interações Médias por Ticket Fechado (menor = mais eficiente)
          </h3>
          <div style={{height: 400, overflowY: "auto"}}>
            {efficiencyData.map((agent, index) => {
              const maxValue = Math.max(...efficiencyData.map(a => a.interacoes));
              const percentage = (agent.interacoes / maxValue) * 100;
              return (
                <div key={agent.name} style={{
                  display: "flex",
                  alignItems: "center",
                  marginBottom: 12,
                  gap: 12
                }}>
                  <div style={{
                    minWidth: 120,
                    textAlign: "right",
                    fontSize: 14,
                    fontWeight: 500
                  }}>
                    {agent.name}
                  </div>
                  <div style={{
                    flex: 1,
                    height: 24,
                    backgroundColor: "#f1f5f9",
                    borderRadius: 12,
                    position: "relative",
                    overflow: "hidden"
                  }}>
                    <div style={{
                      width: `${percentage}%`,
                      height: "100%",
                      backgroundColor: "#28a745",
                      borderRadius: 12,
                      transition: "width 0.5s ease"
                    }} />
                    <span style={{
                      position: "absolute",
                      right: 8,
                      top: "50%",
                      transform: "translateY(-50%)",
                      fontSize: 12,
                      fontWeight: 600,
                      color: percentage > 50 ? "white" : "#374151"
                    }}>
                      {agent.interacoes}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
          <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>Ranking de Eficiência</h3>
          <div style={{display: "grid", gap: 8}}>
            {efficiencyData.map((agent, index) => (
              <div key={agent.name} style={{
                display: "flex", 
                justifyContent: "space-between", 
                alignItems: "center",
                padding: "12px 16px",
                backgroundColor: index < 3 ? "#f8f9fa" : "transparent",
                borderRadius: 6,
                border: index < 3 ? "1px solid #e9ecef" : "none"
              }}>
                <div style={{display: "flex", alignItems: "center", gap: 8}}>
                  <span style={{
                    fontSize: 18,
                    fontWeight: 600,
                    color: index === 0 ? "#28a745" : index === 1 ? "#17a2b8" : index === 2 ? "#ffc107" : "#6b7280",
                    minWidth: 24
                  }}>
                    {index + 1}º
                  </span>
                  <span style={{fontWeight: 500}}>{agent.name}</span>
                </div>
                <div style={{display: "flex", gap: 16, alignItems: "center"}}>
                  <span style={{
                    fontSize: 16,
                    fontWeight: 600,
                    color: "#28a745",
                    backgroundColor: "#d4edda",
                    padding: "4px 12px",
                    borderRadius: 12
                  }}>
                    {agent.interacoes} int/ticket
                  </span>
                  <span style={{
                    fontSize: 14,
                    color: "#6b7280"
                  }}>
                    {agent.tickets} tickets • {agent.total_interacoes} interações
                  </span>
                </div>
              </div>
            ))}
          </div>
          
          <div style={{marginTop: 20, padding: 16, backgroundColor: "#e3f2fd", borderRadius: 8}}>
            <h4 style={{margin: "0 0 8px 0", color: "#1565c0"}}>💡 Como interpretar esta métrica:</h4>
            <ul style={{margin: 0, paddingLeft: 20, color: "#1976d2"}}>
              <li><strong>Interações por ticket</strong> = número médio de trocas de mensagens/ações necessárias para resolver um ticket</li>
              <li><strong>Menos interações</strong> = agente resolve problemas de forma mais direta e eficiente</li>
              <li><strong>Mais interações</strong> = pode indicar tickets mais complexos ou processo menos otimizado</li>
              <li><strong>Dados reais</strong>: baseado no número real de artigos/mensagens públicas em cada ticket fechado</li>
            </ul>
            <p style={{margin: "8px 0 0 0", fontSize: 13, color: "#1565c0", fontStyle: "italic"}}>
              <strong>Exemplo:</strong> Se um agente tem 2.5 interações/ticket, significa que em média precisa de 2-3 trocas para resolver cada problema.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Renderizar trocas de estado por agente
  if (viewMode === "state_changes" && data?.agent_state_changes) {
    const agentNames = Object.keys(data.agent_state_changes);
    const useAllPriorities = !selectedPriorities?.length || selectedPriorities.includes("ALL");
    
    // Preparar dados agregados por agente
    const aggregated = {};
    agentNames.forEach(agent => {
      const agentData = data.agent_state_changes[agent];
      aggregated[agent] = { overall: {}, priorities: {} };
      
      if (useAllPriorities) {
        aggregated[agent].overall = agentData.overall || {};
      } else {
        // Somar apenas prioridades selecionadas
        const combinedPerDay = {};
        let combinedCount = 0;
        
        selectedPriorities.forEach(priority => {
          const priorityData = agentData.priorities?.[priority];
          if (priorityData) {
            combinedCount += priorityData.tickets_count || 0;
            Object.entries(priorityData.tickets_per_day || {}).forEach(([day, count]) => {
              combinedPerDay[day] = (combinedPerDay[day] || 0) + count;
            });
          }
        });
        
        aggregated[agent].overall = {
          tickets_count: combinedCount,
          tickets_per_day: combinedPerDay
        };
      }
      
      // Copiar prioridades
      aggregated[agent].priorities = agentData.priorities || {};
    });
    
    // Ordenar agentes por total de trocas
    const sortedAgents = agentNames.sort((a, b) => {
      const countA = aggregated[a].overall.tickets_count || 0;
      const countB = aggregated[b].overall.tickets_count || 0;
      return sortKey === "tickets" ? countB - countA : countA - countB;
    });
    
    const totalChanges = sortedAgents.reduce((sum, agent) => 
      sum + (aggregated[agent].overall.tickets_count || 0), 0
    );

    return (
      <div style={{maxWidth: 1200, margin: isMobile ? "10px auto" : "20px auto", padding: isMobile ? "0 8px" : "0 16px", fontFamily: "system-ui, Arial"}}>
        <div style={{display:"flex", alignItems:"center", gap:12, marginBottom:16}}>
          <img src="logo.svg" alt="UFEV" style={{height:48, objectFit:"contain"}} />
          <h1 style={{fontSize:24, fontWeight:600, color:"#005A8D", margin:0, flex:1}}>
            Trocas de Estado por Agente
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
        
        <div style={{display:"flex", gap:8, marginBottom:16, flexWrap:"wrap"}}>
          {[
            { value: "agents", label: "Por agentes" },
            { value: "states", label: "Por estados" },
            { value: "responses", label: "Respostas por Agente" },
            { value: "efficiency", label: "Eficiência por Agente" },
            { value: "state_changes", label: "Trocas de Estado" },
            { value: "workload", label: "Análise Temporal" },
          ].map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => updateViewMode(option.value)}
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

        {/* Filtros */}
        <div style={{display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap"}}>
          <div style={{flex: 1, minWidth: 200}}>
            <label style={{fontSize: 12, color: "#555", display: "block", marginBottom: 4}}>Filtrar por Período</label>
            <DateFilter
              selected={selectedDateFilter}
              onChange={setSelectedDateFilter}
            />
          </div>
          <div style={{flex: 1, minWidth: 200}}>
            <label style={{fontSize: 12, color: "#555", display: "block", marginBottom: 4}}>Filtrar por Prioridade</label>
            <MultiSelect
              options={priorities}
              selected={selectedPriorities}
              onChange={setSelectedPriorities}
              placeholder="Selecione prioridades"
            />
          </div>
          <div style={{flex: 1, minWidth: 200}}>
            <label style={{fontSize: 12, color: "#555", display: "block", marginBottom: 4}}>Ordenar por</label>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                border: "1px solid #e2e8f0",
                borderRadius: 6,
                fontSize: 14,
                cursor: "pointer"
              }}
            >
              <option value="tickets">Mais trocas primeiro</option>
              <option value="avg">Menos trocas primeiro</option>
            </select>
          </div>
        </div>

        {/* Resumo */}
        <div style={{display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(3, 1fr)", gap: 16, marginBottom: 24}}>
          <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
            <div style={{fontSize: 14, color: "#6b7280", marginBottom: 4}}>Total de Trocas</div>
            <div style={{fontSize: 32, fontWeight: 700, color: "#8b5cf6"}}>{totalChanges}</div>
          </div>
          <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
            <div style={{fontSize: 14, color: "#6b7280", marginBottom: 4}}>Agentes Ativos</div>
            <div style={{fontSize: 32, fontWeight: 700, color: "#8b5cf6"}}>{sortedAgents.length}</div>
          </div>
          <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
            <div style={{fontSize: 14, color: "#6b7280", marginBottom: 4}}>Média por Agente</div>
            <div style={{fontSize: 32, fontWeight: 700, color: "#8b5cf6"}}>
              {sortedAgents.length > 0 ? Math.round(totalChanges / sortedAgents.length) : 0}
            </div>
          </div>
        </div>

        {/* Gráfico principal - Trocas por dia */}
        <div style={{border:"1px solid #eee", borderRadius:10, padding:12, marginBottom:12}}>
          <div style={{display:"flex", alignItems:"center", gap:8, margin:"4px 0 8px 4px"}}>
            <div style={{width:8, height:24, background:"#8b5cf6", borderRadius:4}}/>
            <h2 style={{margin:0, fontSize:16, color:"#7c3aed"}}>Trocas de Estado por Dia</h2>
          </div>
          <div style={{width:"100%", height:420, overflowX: "auto", overflowY: "hidden", paddingBottom: 20}}>
            {(() => {
              // Preparar séries de dados (dias)
              const allDays = new Set();
              sortedAgents.forEach(agent => {
                Object.keys(aggregated[agent].overall.tickets_per_day || {}).forEach(day => allDays.add(day));
              });
              const sortedDays = Array.from(allDays).sort();
              
              const series = sortedDays.map(day => {
                const dayData = { day };
                sortedAgents.forEach(agent => {
                  dayData[agent] = aggregated[agent].overall.tickets_per_day[day] || 0;
                });
                return dayData;
              });
              
              const rows = sortedAgents.map(agent => ({ label: agent }));
              
              return (
                <div style={{
                  display: "flex", 
                  alignItems: "end", 
                  height: "calc(100% - 40px)", 
                  gap: isMobile ? 2 : 4, 
                  minWidth: isMobile ? "100%" : series.length * 60,
                  width: "100%"
                }}>
                  {series.map((dayData, index) => {
                    const totalTickets = Object.values(dayData).reduce((sum, val) => 
                      typeof val === 'number' ? sum + val : sum, 0
                    );
                    const maxTotal = Math.max(...series.map(d => 
                      Object.values(d).reduce((sum, val) => typeof val === 'number' ? sum + val : sum, 0)
                    ));
                    const heightPercentage = maxTotal > 0 ? (totalTickets / maxTotal) * 100 : 0;
                    
                    return (
                      <div key={dayData.day} style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        height: "100%",
                        flex: 1,
                        minWidth: isMobile ? 30 : 50,
                        maxWidth: isMobile ? 60 : 80
                      }}>
                        <div style={{
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "end",
                          height: "90%",
                          width: "100%",
                          maxWidth: isMobile ? 35 : 40,
                          backgroundColor: "#f1f5f9",
                          borderRadius: "4px 4px 0 0",
                          position: "relative",
                          overflow: "hidden"
                        }}>
                          {rows.map((row, rowIndex) => {
                            const value = dayData[row.label] || 0;
                            const segmentHeight = totalTickets > 0 ? (value / totalTickets) * heightPercentage : 0;
                            return value > 0 ? (
                              <div
                                key={row.label}
                                style={{
                                  height: `${segmentHeight}%`,
                                  backgroundColor: COLORS[rowIndex % COLORS.length],
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontSize: 10,
                                  fontWeight: 600,
                                  color: "white",
                                  textShadow: "0 1px 2px rgba(0,0,0,0.3)"
                                }}
                                title={`${row.label}: ${value}`}
                              >
                                {value > 0 ? value : ""}
                              </div>
                            ) : null;
                          })}
                        </div>
                        <div style={{
                          fontSize: isMobile ? 8 : 10,
                          fontWeight: 500,
                          color: "#6b7280",
                          marginTop: 8,
                          transform: "rotate(-45deg)",
                          transformOrigin: "center",
                          whiteSpace: "nowrap",
                          height: 20,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center"
                        }}>
                          {dayData.day}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </div>
        </div>
        
        {/* Legenda de cores */}
        <div style={{padding: "16px 20px", backgroundColor: "#f8f9fa", borderTop: "1px solid #e2e8f0", borderRadius: 8}}>
          <h4 style={{margin: "0 0 12px 0", fontSize: 14, fontWeight: 600, color: "#374151"}}>
            🎨 Legenda de Cores:
          </h4>
          <div style={{display: "flex", flexWrap: "wrap", gap: 16}}>
            {sortedAgents.map((agent, index) => (
              <div key={agent} style={{display: "flex", alignItems: "center", gap: 6}}>
                <div style={{
                  width: 16,
                  height: 16,
                  backgroundColor: COLORS[index % COLORS.length],
                  borderRadius: 3,
                  border: "1px solid rgba(0,0,0,0.1)"
                }}/>
                <span style={{fontSize: 13, color: "#4b5563"}}>{agent}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Renderizar análise temporal
  if (viewMode === "workload" && data?.workload_analysis) {
    const workload = data.workload_analysis[workloadMode]; // "created" ou "closed"
    const modeLabel = workloadMode === "created" ? "Criação" : "Fechamento";
    
    // Calcular médias baseadas no período real
    const calculateWeekdayAverages = (weekdayData, fromDate) => {
      // Calcular quantos dias de cada tipo da semana já passaram desde fromDate
      const startDate = new Date(fromDate);
      const endDate = new Date();
      const weekdayNames = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
      const weekdayCounts = [0, 0, 0, 0, 0, 0, 0]; // Segunda=0, Domingo=6
      
      let currentDate = new Date(startDate);
      while (currentDate <= endDate) {
        const weekday = currentDate.getDay();
        const adjustedWeekday = weekday === 0 ? 6 : weekday - 1; // Domingo=6, Segunda=0
        weekdayCounts[adjustedWeekday]++;
        currentDate.setDate(currentDate.getDate() + 1);
      }
      
      return weekdayNames.map((day, index) => ({
        name: day,
        tickets: weekdayCounts[index] > 0 ? Math.round((weekdayData[day] / weekdayCounts[index]) * 10) / 10 : 0,
        total: weekdayData[day],
        days_count: weekdayCounts[index]
      }));
    };
    
    const calculateHourlyAverages = (hourData, fromDate) => {
      // Calcular total de dias no período
      const startDate = new Date(fromDate);
      const endDate = new Date();
      const totalDays = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24));
      
      return Object.entries(hourData).map(([hour, count]) => ({
        name: hour,
        tickets: totalDays > 0 ? Math.round((count / totalDays) * 10) / 10 : 0,
        total: count,
        total_days: totalDays
      }));
    };
    
    // Dados para gráfico de barras por dia da semana (médias)
    const weekdayData = calculateWeekdayAverages(workload.by_weekday, workload.period_info?.from_date || "2025-09-30");
    
    // Dados para gráfico de barras por hora (médias)
    const hourData = calculateHourlyAverages(workload.by_hour, workload.period_info?.from_date || "2025-09-30");

    return (
      <div style={{maxWidth: 1200, margin: isMobile ? "10px auto" : "20px auto", padding: isMobile ? "0 8px" : "0 16px", fontFamily: "system-ui, Arial"}}>
        <div style={{display:"flex", alignItems:"center", gap:12, marginBottom:16}}>
          <img src="logo.svg" alt="UFEV" style={{height:48, objectFit:"contain"}} />
          <h1 style={{fontSize:24, fontWeight:600, color:"#005A8D", margin:0, flex:1}}>
            Análise Temporal - {modeLabel} de Tickets
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
            { value: "responses", label: "Respostas por Agente" },
            { value: "efficiency", label: "Eficiência por Agente" },
            { value: "state_changes", label: "Trocas de Estado" },
            { value: "workload", label: "Análise Temporal" },
          ].map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => updateViewMode(option.value)}
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

        <div style={{display:"flex", gap:8, marginBottom:16, justifyContent:"center"}}>
          {[
            { value: "created", label: "📥 Criação de Tickets" },
            { value: "closed", label: "✅ Fecho de Tickets" },
          ].map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => updateWorkloadMode(option.value)}
              style={{
                padding:"12px 20px",
                borderRadius:8,
                border:"2px solid",
                borderColor: workloadMode === option.value ? "#28a745" : "#e2e8f0",
                backgroundColor: workloadMode === option.value ? "#28a745" : "white",
                color: workloadMode === option.value ? "white" : "#64748b",
                cursor:"pointer",
                fontWeight: workloadMode === option.value ? 600 : 400
              }}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div style={{display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: isMobile ? 16 : 24, marginBottom: 24}}>
          <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
            <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>Média de Tickets por Dia da Semana</h3>
            <div style={{height: 300}}>
              {weekdayData.map((day, index) => {
                const maxValue = Math.max(...weekdayData.map(d => d.tickets));
                const percentage = maxValue > 0 ? (day.tickets / maxValue) * 100 : 0;
                return (
                  <div key={day.name} style={{
                    display: "flex",
                    alignItems: "center",
                    marginBottom: 8,
                    gap: 8
                  }}>
                    <div style={{
                      minWidth: 60,
                      fontSize: 12,
                      fontWeight: 500
                    }}>
                      {day.name}
                    </div>
                    <div style={{
                      flex: 1,
                      height: 20,
                      backgroundColor: "#f1f5f9",
                      borderRadius: 10,
                      position: "relative",
                      overflow: "hidden"
                    }}>
                      <div style={{
                        width: `${percentage}%`,
                        height: "100%",
                        backgroundColor: "#005A8D",
                        borderRadius: 10,
                        transition: "width 0.5s ease"
                      }} />
                      <span style={{
                        position: "absolute",
                        right: 4,
                        top: "50%",
                        transform: "translateY(-50%)",
                        fontSize: 10,
                        fontWeight: 600,
                        color: percentage > 40 ? "white" : "#374151"
                      }}>
                        {day.tickets}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          
          <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)"}}>
            <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>Média de Tickets por Hora do Dia</h3>
            <div style={{height: 300, overflowY: "auto"}}>
              {hourData.map((hour, index) => {
                const maxValue = Math.max(...hourData.map(h => h.tickets));
                const percentage = maxValue > 0 ? (hour.tickets / maxValue) * 100 : 0;
                return (
                  <div key={hour.name} style={{
                    display: "flex",
                    alignItems: "center",
                    marginBottom: 6,
                    gap: 8
                  }}>
                    <div style={{
                      minWidth: 35,
                      fontSize: 11,
                      fontWeight: 500
                    }}>
                      {hour.name}
                    </div>
                    <div style={{
                      flex: 1,
                      height: 16,
                      backgroundColor: "#f1f5f9",
                      borderRadius: 8,
                      position: "relative",
                      overflow: "hidden"
                    }}>
                      <div style={{
                        width: `${percentage}%`,
                        height: "100%",
                        backgroundColor: "#28a745",
                        borderRadius: 8,
                        transition: "width 0.5s ease"
                      }} />
                      <span style={{
                        position: "absolute",
                        right: 4,
                        top: "50%",
                        transform: "translateY(-50%)",
                        fontSize: 9,
                        fontWeight: 600,
                        color: percentage > 40 ? "white" : "#374151"
                      }}>
                        {hour.tickets}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div style={{backgroundColor: "white", padding: 20, borderRadius: 8, boxShadow: "0 1px 3px rgba(0,0,0,0.1)", marginBottom: 24}}>
          <h3 style={{margin: "0 0 16px 0", color: "#1f2937"}}>
            Heatmap: Dia da Semana x Hora ({modeLabel} de Tickets)
          </h3>
          <div style={{overflowX: "auto", paddingTop: 8}}>
            <div style={{minWidth: isMobile ? 600 : 800}}>
              {/* Header com horas */}
              <div style={{display: "flex", marginBottom: 8, position: "sticky", top: 0, backgroundColor: "white", zIndex: 1, paddingBottom: 4}}>
                <div style={{width: 80, fontSize: 12, fontWeight: 600, color: "#6b7280", display: "flex", alignItems: "center", paddingRight: "8px"}}>
                  Dia / Hora
                </div>
                {Array.from({length: 24}, (_, hour) => (
                  <div key={hour} style={{
                    width: isMobile ? 24 : 34, // Ajustar baseado no dispositivo
                    fontSize: 10,
                    textAlign: "center",
                    color: "#6b7280",
                    fontWeight: 500,
                    padding: "4px 0",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center"
                  }}>
                    {hour.toString().padStart(2, '0')}h
                  </div>
                ))}
              </div>
              
              {/* Heatmap grid */}
              {["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"].map(weekday => {
                const dayData = workload.heatmap?.filter(item => item.weekday === weekday) || [];
                const maxTickets = Math.max(...(workload.heatmap?.map(item => item.tickets) || [1]));
                
                return (
                  <div key={weekday} style={{display: "flex", marginBottom: 3}}>
                    <div style={{
                      width: 80,
                      fontSize: 12,
                      fontWeight: 500,
                      color: "#374151",
                      display: "flex",
                      alignItems: "center",
                      paddingRight: 8,
                      height: isMobile ? 26 : 34 // Ajustar baseado no tamanho das células + border
                    }}>
                      {weekday}
                    </div>
                    {Array.from({length: 24}, (_, hour) => {
                      const hourData = dayData.find(item => item.hour === `${hour.toString().padStart(2, '0')}h`);
                      const tickets = hourData?.tickets || 0;
                      const intensity = maxTickets > 0 ? tickets / maxTickets : 0;
                      
                      // Escala de cores: branco -> azul escuro
                      const getColor = (intensity) => {
                        if (intensity === 0) return "#f8fafc";
                        if (intensity <= 0.2) return "#e0f2fe";
                        if (intensity <= 0.4) return "#b3e5fc";
                        if (intensity <= 0.6) return "#4fc3f7";
                        if (intensity <= 0.8) return "#29b6f6";
                        return "#0277bd";
                      };
                      
                      const textColor = intensity > 0.5 ? "white" : "#374151";
                      
                      return (
                        <div
                          key={hour}
                          style={{
                            width: isMobile ? 24 : 32, // Ajustar baseado no dispositivo
                            height: isMobile ? 24 : 32,
                            backgroundColor: getColor(intensity),
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 9,
                            fontWeight: 600,
                            color: textColor,
                            border: "1px solid #e2e8f0",
                            cursor: tickets > 0 ? "pointer" : "default"
                          }}
                          title={`${weekday} ${hour.toString().padStart(2, '0')}h: ${tickets} tickets`}
                        >
                          {tickets > 0 ? tickets : ""}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
              
              {/* Legenda */}
              <div style={{marginTop: 16, display: "flex", alignItems: "center", gap: 8}}>
                <span style={{fontSize: 12, color: "#6b7280"}}>Intensidade:</span>
                <div style={{display: "flex", alignItems: "center", gap: 2}}>
                  <div style={{width: 16, height: 16, backgroundColor: "#f8fafc", border: "1px solid #e2e8f0"}} />
                  <span style={{fontSize: 10, color: "#6b7280", marginRight: 8}}>0</span>
                  <div style={{width: 16, height: 16, backgroundColor: "#e0f2fe", border: "1px solid #e2e8f0"}} />
                  <div style={{width: 16, height: 16, backgroundColor: "#b3e5fc", border: "1px solid #e2e8f0"}} />
                  <div style={{width: 16, height: 16, backgroundColor: "#4fc3f7", border: "1px solid #e2e8f0"}} />
                  <div style={{width: 16, height: 16, backgroundColor: "#29b6f6", border: "1px solid #e2e8f0"}} />
                  <div style={{width: 16, height: 16, backgroundColor: "#0277bd", border: "1px solid #e2e8f0"}} />
                  <span style={{fontSize: 10, color: "#6b7280", marginLeft: 8}}>Máximo</span>
                </div>
              </div>
            </div>
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
    <div style={{maxWidth: 1200, margin: isMobile ? "10px auto" : "20px auto", padding: isMobile ? "0 8px" : "0 16px", fontFamily: "system-ui, Arial"}}>
<div style={{display:"flex", alignItems:"center", gap:12, marginBottom:16, flexWrap: "wrap"}}>
  <img
    src="logo.svg"
    alt="UFEV"
    style={{height:48, objectFit:"contain"}}
  />
  <h1 style={{fontSize: isMobile ? 18 : 24, fontWeight:600, color:"#005A8D", margin:0, flex:1, minWidth: isMobile ? "150px" : "200px"}}>
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
      <div style={{display:"flex", gap:8, marginBottom:16, flexWrap:"wrap"}}>
        {[
          { value: "agents", label: "Por agentes" },
          { value: "states", label: "Por estados" },
          { value: "responses", label: "Respostas por Agente" },
          { value: "efficiency", label: "Eficiência por Agente" },
          { value: "state_changes", label: "Trocas de Estado" },
          { value: "workload", label: "Análise Temporal" },
        ].map(option => (
          <button
            key={option.value}
            type="button"
            onClick={() => updateViewMode(option.value)}
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
          <label style={{fontSize: 12, color: "#555"}}>Período</label>
          <DateFilter
            selected={selectedDateFilter}
            onChange={setSelectedDateFilter}
          />
        </div>
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
      <div style={{display:"grid", gridTemplateColumns: isMobile ? "repeat(2, minmax(0,1fr))" : "repeat(4, minmax(0,1fr))", gap:12, margin:"12px 0"}}>
        <div style={{borderTop:"4px solid #0096D6", border:"1px solid #eee", borderRadius:10, padding:16}}>
          <div style={{fontSize:12, color:"#666"}}>Tickets (total)</div>
          <div style={{fontSize:28, fontWeight:600}}>{kpis.totalTickets || 0}</div>
        </div>
        <div style={{borderTop:"4px solid #F47C20", border:"1px solid #eee", borderRadius:10, padding:16}}>
          <div style={{fontSize:12, color:"#666"}}>Média geral (horas)</div>
          <div style={{fontSize:28, fontWeight:600}}>{kpis.avgAll ? kpis.avgAll.toFixed(2) : "—"}</div>
        </div>
        <div style={{borderTop:"4px solid #10B981", border:"1px solid #eee", borderRadius:10, padding:16}}>
          <div style={{fontSize:12, color:"#666"}}>Top eficiência (mín. {kpis.dynamicMinTickets})</div>
          <div style={{fontSize: isMobile ? 14 : 16, fontWeight:600}}>
            {kpis.topRatio ? (
              kpis.topRatio.efficiency_ratio !== undefined ? 
                `${kpis.topRatio.label} · ${(kpis.topRatio.efficiency_ratio * 100).toFixed(1)}%` :
                `${kpis.topRatio.label} · ${kpis.topRatio.tickets_count} tickets`
            ) : "—"}
          </div>
        </div>
        <div style={{borderTop:"4px solid #005A8D", border:"1px solid #eee", borderRadius:10, padding:16}}>
          <div style={{fontSize:12, color:"#666"}}>Top tempo (mín. {kpis.dynamicMinTickets})</div>
          <div style={{fontSize: isMobile ? 14 : 16, fontWeight:600}}>
            {kpis.topTime ? `${kpis.topTime.label} · ${kpis.topTime.avg_time_hours.toFixed(2)}h` : "—"}
          </div>
        </div>
      </div>

      {/* Gráfico */}
      <div style={{border:"1px solid #eee", borderRadius:10, padding:12, marginBottom:12}}>
        <div style={{display:"flex", alignItems:"center", gap:8, margin:"4px 0 8px 4px"}}>
          <div style={{width:8, height:24, background:"#0096D6", borderRadius:4}}/>
          <h2 style={{margin:0, fontSize:16, color:"#005A8D"}}>Tickets por dia</h2>
        </div>
        <div style={{width:"100%", height:420, overflowX: "auto", overflowY: "hidden", paddingBottom: 20}}>
          <div style={{
            display: "flex", 
            alignItems: "end", 
            height: "calc(100% - 40px)", 
            gap: isMobile ? 2 : 4, 
            minWidth: isMobile ? "100%" : series.length * 60,
            width: "100%"
          }}>
            {series.map((dayData, index) => {
              const totalTickets = Object.values(dayData).reduce((sum, val) => 
                typeof val === 'number' ? sum + val : sum, 0
              );
              const maxTotal = Math.max(...series.map(d => 
                Object.values(d).reduce((sum, val) => typeof val === 'number' ? sum + val : sum, 0)
              ));
              const heightPercentage = maxTotal > 0 ? (totalTickets / maxTotal) * 100 : 0;
              
              return (
                <div key={dayData.day} style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  height: "100%",
                  flex: 1,
                  minWidth: isMobile ? 30 : 50,
                  maxWidth: isMobile ? 60 : 80
                }}>
                  <div style={{
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "end",
                    height: "90%",
                    width: "100%",
                    maxWidth: isMobile ? 35 : 40,
                    backgroundColor: "#f1f5f9",
                    borderRadius: "4px 4px 0 0",
                    position: "relative",
                    overflow: "hidden"
                  }}>
                    {rows.map((row, rowIndex) => {
                      const value = dayData[row.label] || 0;
                      const segmentHeight = totalTickets > 0 ? (value / totalTickets) * heightPercentage : 0;
                      return value > 0 ? (
                        <div
                          key={row.label}
                          style={{
                            height: `${segmentHeight}%`,
                            backgroundColor: COLORS[rowIndex % COLORS.length],
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: 10,
                            fontWeight: 600,
                            color: "white",
                            textShadow: "0 1px 2px rgba(0,0,0,0.3)"
                          }}
                          title={`${row.label}: ${value}`}
                        >
                          {value > 0 ? value : ""}
                        </div>
                      ) : null;
                    })}
                  </div>
                  <div style={{
                    fontSize: isMobile ? 8 : 10,
                    fontWeight: 500,
                    color: "#6b7280",
                    marginTop: 8,
                    transform: "rotate(-45deg)",
                    transformOrigin: "center",
                    whiteSpace: "nowrap",
                    height: 20,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center"
                  }}>
                    {dayData.day}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
       {/* Legenda de cores */}
        <div style={{padding: "16px 20px", backgroundColor: "#f8f9fa", borderTop: "1px solid #e2e8f0"}}>
          <h4 style={{margin: "0 0 12px 0", fontSize: 14, fontWeight: 600, color: "#374151"}}>
            🎨 Legenda de Cores:
          </h4>
          <div style={{display: "flex", flexWrap: "wrap", gap: 16}}>
            {rows.map((row, index) => (
              <div key={row.label} style={{display: "flex", alignItems: "center", gap: 6}}>
                <div style={{
                  width: 16,
                  height: 16,
                  backgroundColor: COLORS[index % COLORS.length],
                  borderRadius: 3,
                  border: "1px solid rgba(0,0,0,0.1)"
                }} />
                <span style={{fontSize: 13, color: "#374151", fontWeight: 500}}>
                  {row.label}
                </span>
              </div>
            ))}
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
          <tfoot>
            <tr style={{background:"#f1f5f9", fontWeight:600, borderTop:"2px solid #e2e8f0"}}>
              <td style={{padding:10, fontWeight:700, color:"#374151"}}>TOTAL</td>
              <td style={{padding:10, textAlign:"right", fontWeight:700, color:"#374151"}}>
                {rows.reduce((sum, r) => sum + (r.tickets_count ?? 0), 0)}
              </td>
              <td style={{padding:10, textAlign:"right", color:"#6b7280"}}>—</td>
              {days.map(d => {
                const dayTotal = rows.reduce((sum, r) => sum + (r.perDay?.[d] ?? 0), 0);
                return (
                  <td key={d} style={{padding:10, textAlign:"center", fontWeight:700, color:"#374151"}}>
                    {dayTotal}
                  </td>
                );
              })}
            </tr>
          </tfoot>
        </table>
        
 
      </div>

    </div>
  );
}
