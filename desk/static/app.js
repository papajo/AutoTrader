// AutoTrader Live Execution Desk - Real-time WebSocket & Controller

let socket = null;
let currentSummary = null;
let currentTickers = {};
let isKilled = false;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    initWebSocket();
    updateOrderPricePreview();
});

// WebSocket Lifecycle
function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        document.getElementById("ws-indicator").className = "dot-online";
        document.getElementById("ws-status-text").innerText = "STREAM: CONNECTED";
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWsMessage(data);
        } catch (e) {
            console.error("WS Parse error:", e);
        }
    };

    socket.onclose = () => {
        document.getElementById("ws-indicator").className = "";
        document.getElementById("ws-status-text").innerText = "STREAM: RECONNECTING...";
        setTimeout(initWebSocket, 2000);
    };

    socket.onerror = (err) => {
        console.warn("WebSocket error:", err);
        socket.close();
    };
}

function handleWsMessage(data) {
    if (data.type === "initial_state") {
        if (data.tickers) {
            data.tickers.forEach(t => currentTickers[t.symbol] = t);
            renderTickerBar(data.tickers);
        }
        if (data.summary) updateSummaryHeader(data.summary);
        if (data.positions) renderPositions(data.positions);
        if (data.orders) renderOrders(data.orders);
        if (data.recent_gates) renderAuditStream(data.recent_gates);
        setKilledState(data.is_killed);
    } else if (data.type === "market_tick") {
        if (data.tickers) {
            updateTickers(data.tickers);
        }
        if (data.summary) updateSummaryHeader(data.summary);
    } else if (data.type === "order_event") {
        if (data.order) {
            prependOrder(data.order);
            const statusMsg = data.order.status === "filled" 
                ? `Order FILLED: ${data.order.side.toUpperCase()} ${data.order.quantity} ${data.order.symbol} @ $${data.order.price}`
                : `Order REJECTED: ${data.order.reason}`;
            showToast(statusMsg, data.order.status === "filled" ? "success" : "error");
        }
        if (data.positions) renderPositions(data.positions);
        if (data.summary) updateSummaryHeader(data.summary);
    } else if (data.type === "system_alert") {
        showToast(data.message, data.level === "critical" ? "error" : "info");
        setKilledState(data.is_killed);
        if (data.summary) updateSummaryHeader(data.summary);
    } else if (data.type === "cycle_completed") {
        if (data.recent_gates) renderAuditStream(data.recent_gates);
        updateGateCardsFromCycle(data.cycle);
        showToast(`Auto-cycle for ${data.cycle.symbol}: ${data.cycle.approved ? 'APPROVED' : 'BLOCKED/ESCALATED'}`, data.cycle.approved ? 'success' : 'warn');
    }
}

// Renderers
function renderTickerBar(tickers) {
    const container = document.getElementById("ticker-bar");
    container.innerHTML = "";
    tickers.forEach(t => {
        const item = document.createElement("div");
        item.className = "ticker-item";
        item.id = `ticker-${t.symbol}`;
        item.onclick = () => selectTickerForOrder(t.symbol);

        const chgClass = t.change_pct >= 0 ? "chg-pos" : "chg-neg";
        const chgSign = t.change_pct >= 0 ? "+" : "";

        item.innerHTML = `
            <span class="ticker-sym">${t.symbol}</span>
            <span class="ticker-price" id="t-price-${t.symbol}">$${formatNumber(t.price)}</span>
            <span class="ticker-chg ${chgClass}" id="t-chg-${t.symbol}">${chgSign}${t.change_pct.toFixed(2)}%</span>
        `;
        container.appendChild(item);
    });
}

function updateTickers(tickers) {
    tickers.forEach(t => {
        const prev = currentTickers[t.symbol];
        const elPrice = document.getElementById(`t-price-${t.symbol}`);
        const elChg = document.getElementById(`t-chg-${t.symbol}`);
        const elItem = document.getElementById(`ticker-${t.symbol}`);

        if (elPrice && prev) {
            elPrice.innerText = `$${formatNumber(t.price)}`;
            const chgSign = t.change_pct >= 0 ? "+" : "";
            elChg.className = `ticker-chg ${t.change_pct >= 0 ? 'chg-pos' : 'chg-neg'}`;
            elChg.innerText = `${chgSign}${t.change_pct.toFixed(2)}%`;

            // Flash effect
            if (t.price > prev.price) {
                elItem.classList.remove("flash-down");
                elItem.classList.add("flash-up");
                setTimeout(() => elItem.classList.remove("flash-up"), 800);
            } else if (t.price < prev.price) {
                elItem.classList.remove("flash-up");
                elItem.classList.add("flash-down");
                setTimeout(() => elItem.classList.remove("flash-down"), 800);
            }
        }
        currentTickers[t.symbol] = t;
    });

    // Also update order preview estimated value
    updateOrderPricePreview();
}

function updateSummaryHeader(s) {
    currentSummary = s;
    document.getElementById("nav-val").innerText = `$${formatCurrency(s.net_account_value)}`;
    document.getElementById("cash-val").innerText = `$${formatCurrency(s.cash)}`;

    const pnlSign = s.total_pnl >= 0 ? "+" : "-";
    const pnlClass = s.total_pnl >= 0 ? "pnl-pos" : "pnl-neg";
    const pnlPct = ((s.total_pnl / 100000) * 100).toFixed(2);
    const pnlEl = document.getElementById("total-pnl-val");
    pnlEl.className = `metric-val ${pnlClass}`;
    pnlEl.innerText = `${pnlSign}$${formatCurrency(Math.abs(s.total_pnl))} (${pnlSign}${Math.abs(pnlPct)}%)`;

    document.getElementById("daily-loss-val").innerText = `$${formatCurrency(s.daily_loss)} / $${formatCurrency(s.max_daily_loss)}`;

    // Badges
    const badge = document.getElementById("engine-status-badge");
    const badgeText = document.getElementById("engine-status-text");
    if (s.status === "HALTED") {
        badge.className = "badge badge-halted";
        badgeText.innerText = "ENGINE: HALTED";
    } else {
        badge.className = "badge badge-running";
        badgeText.innerText = "ENGINE: RUNNING";
    }
}

function renderPositions(positions) {
    const tbody = document.getElementById("positions-tbody");
    document.getElementById("pos-count-badge").innerText = positions.length;

    if (positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No open positions currently held.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";
    positions.forEach(p => {
        const row = document.createElement("tr");
        const pnlSign = p.unrealized_pnl >= 0 ? "+" : "-";
        const pnlClass = p.unrealized_pnl >= 0 ? "pnl-pos" : "pnl-neg";

        row.innerHTML = `
            <td><strong>${p.symbol}</strong> <span style="font-size:10px;color:var(--text-dim);">(${p.asset_class})</span></td>
            <td>${p.quantity}</td>
            <td>$${formatNumber(p.avg_price)}</td>
            <td>$${formatNumber(p.current_price)}</td>
            <td>$${formatCurrency(p.market_value)}</td>
            <td class="${pnlClass}">${pnlSign}$${formatCurrency(Math.abs(p.unrealized_pnl))} (${pnlSign}${Math.abs(p.unrealized_pnl_pct)}%)</td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="closePosition('${p.symbol}')">Flatten</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function renderOrders(orders) {
    const tbody = document.getElementById("orders-tbody");
    document.getElementById("order-count-badge").innerText = orders.length;

    if (orders.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No orders executed in this session.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";
    orders.forEach(o => appendOrderRow(tbody, o));
}

function prependOrder(o) {
    const tbody = document.getElementById("orders-tbody");
    const emptyRow = tbody.querySelector(".empty-state");
    if (emptyRow) tbody.innerHTML = "";
    appendOrderRow(tbody, o, true);
    const countBadge = document.getElementById("order-count-badge");
    countBadge.innerText = parseInt(countBadge.innerText || "0") + 1;
}

function appendOrderRow(tbody, o, prepend = false) {
    const row = document.createElement("tr");
    const sideClass = o.side.toLowerCase() === "buy" ? "pnl-pos" : "pnl-neg";
    const statusClass = o.status === "filled" ? "pnl-pos" : "pnl-neg";
    const timeStr = new Date(o.timestamp).toLocaleTimeString();

    row.innerHTML = `
        <td style="color:var(--text-dim);">${timeStr}</td>
        <td style="font-size:11px;">${o.order_id}</td>
        <td><strong>${o.symbol}</strong></td>
        <td class="${sideClass}" style="font-weight:700;">${o.side.toUpperCase()}</td>
        <td>${o.quantity}</td>
        <td>$${formatNumber(o.price)}</td>
        <td class="${statusClass}" style="font-weight:700;">${o.status.toUpperCase()}</td>
        <td style="color:var(--text-secondary);max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${o.reason}">${o.reason}</td>
    `;

    if (prepend) {
        tbody.insertBefore(row, tbody.firstChild);
    } else {
        tbody.appendChild(row);
    }
}

function renderAuditStream(entries) {
    const stream = document.getElementById("audit-log-stream");
    stream.innerHTML = "";
    entries.forEach(e => {
        const row = document.createElement("div");
        const decClass = (e.decision || "proceed").toLowerCase();
        row.className = `stream-row ${decClass}`;
        const timeStr = e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : "";

        row.innerHTML = `
            <span class="stream-time">${timeStr}</span>
            <span class="stream-gate">[${e.gate_name || "Gate"}]</span>
            <span class="stream-sym">${e.symbol || ""}</span>
            <span class="stream-reason">${(e.reasons && e.reasons[0]) || e.decision || ""}</span>
        `;
        stream.appendChild(row);
    });
}

function updateGateCardsFromCycle(cycle) {
    if (!cycle) return;
    setGateStatus("gate-1", cycle.preflight);
    setGateStatus("gate-2", cycle.news_risk);
    setGateStatus("gate-3", cycle.thesis_quality);
    setGateStatus("gate-4", cycle.risk_compliance);
}

function setGateStatus(prefix, res) {
    const elStat = document.getElementById(`${prefix}-status`);
    const elDet = document.getElementById(`${prefix}-detail`);
    if (!res || !elStat) return;

    elStat.className = `gate-status status-${res.decision}`;
    elStat.innerText = res.decision.toUpperCase();
    if (res.reasons && res.reasons.length > 0 && elDet) {
        elDet.innerText = res.reasons[0];
        elDet.title = res.reasons.join("; ");
    }
}

// Controller Actions
function selectTickerForOrder(sym) {
    const sel = document.getElementById("order-symbol");
    if (sel) {
        sel.value = sym;
        updateOrderPricePreview();
    }
}

function setOrderSide(side) {
    document.getElementById("order-side").value = side;
    const btnBuy = document.getElementById("side-buy-btn");
    const btnSell = document.getElementById("side-sell-btn");
    if (side === "buy") {
        btnBuy.className = "side-btn active-buy";
        btnSell.className = "side-btn";
    } else {
        btnBuy.className = "side-btn";
        btnSell.className = "side-btn active-sell";
    }
}

function updateOrderPricePreview() {
    const sym = document.getElementById("order-symbol").value;
    const qty = parseFloat(document.getElementById("order-qty").value) || 0;
    const ticker = currentTickers[sym];
    const price = ticker ? ticker.price : 100.0;
    const estVal = qty * price;
    document.getElementById("est-value-display").innerText = `$${formatCurrency(estVal)}`;
}

async function submitManualOrder(event) {
    event.preventDefault();
    const sym = document.getElementById("order-symbol").value;
    const side = document.getElementById("order-side").value;
    const qty = parseFloat(document.getElementById("order-qty").value);
    const assetClass = document.getElementById("order-asset-class").value;
    const validateLaya = document.getElementById("order-validate-laya").checked;

    const payload = {
        symbol: sym,
        side: side,
        quantity: qty,
        asset_class: assetClass,
        validate_laya: validateLaya
    };

    try {
        const resp = await fetch("/api/override/order", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (!resp.ok) {
            showToast(res.detail || "Order execution failed", "error");
        }
    } catch (e) {
        showToast(`Request failed: ${e}`, "error");
    }
}

async function closePosition(sym) {
    if (!confirm(`Are you sure you want to flatten open position in ${sym}?`)) return;
    try {
        const resp = await fetch("/api/override/close-position", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym })
        });
        const res = await resp.json();
        if (!resp.ok) {
            showToast(res.detail || "Failed to flatten position", "error");
        }
    } catch (e) {
        showToast(`Request failed: ${e}`, "error");
    }
}

async function toggleKillSwitch() {
    const endpoint = isKilled ? "/api/override/resume" : "/api/override/kill-switch";
    if (!isKilled && !confirm("⚠️ DANGER: Engaging the Emergency Kill Switch will HALT all automated trading and cancel new orders. Proceed?")) {
        return;
    }

    try {
        const resp = await fetch(endpoint, { method: "POST" });
        const res = await resp.json();
        if (resp.ok) {
            setKilledState(res.status === "HALTED");
        }
    } catch (e) {
        showToast(`Kill switch toggle failed: ${e}`, "error");
    }
}

function setKilledState(killed) {
    isKilled = Boolean(killed);
    const btn = document.getElementById("btn-kill-switch");
    if (isKilled) {
        btn.className = "btn btn-secondary";
        btn.innerText = "▶️ RESUME TRADING";
    } else {
        btn.className = "btn btn-danger";
        btn.innerText = "🚨 EMERGENCY KILL SWITCH";
    }
}

async function runAutoCycle() {
    const sym = document.getElementById("cycle-symbol").value;
    const box = document.getElementById("cycle-output-box");
    const banner = document.getElementById("cycle-status-banner");
    const pre = document.getElementById("cycle-log-text");

    box.style.display = "block";
    banner.innerText = `Evaluating ${sym} across multi-agent analysts and 4 Laya gates...`;
    pre.innerText = "Running...\n";

    try {
        const resp = await fetch("/api/engine/run-cycle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym, asset_class: "stock" })
        });
        const res = await resp.json();
        banner.innerText = res.approved ? "✅ VERDICT: TRADE APPROVED BY ALL GATES" : "❌ VERDICT: TRADE BLOCKED OR ESCALATED";
        banner.style.color = res.approved ? "var(--color-green)" : "var(--color-red)";
        pre.innerText = JSON.stringify(res, null, 2);
    } catch (e) {
        banner.innerText = "Evaluation error";
        pre.innerText = String(e);
    }
}

async function updateRiskLimits(event) {
    event.preventDefault();
    const maxLoss = parseFloat(document.getElementById("cfg-max-loss").value);
    const cooldown = parseInt(document.getElementById("cfg-cooldown").value);
    const maxPos = parseFloat(document.getElementById("cfg-max-pos").value);

    try {
        const resp = await fetch("/api/override/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                max_daily_loss: maxLoss,
                trade_cooldown: cooldown,
                max_position_size: maxPos
            })
        });
        if (resp.ok) {
            showToast("Risk parameters updated successfully.", "success");
        }
    } catch (e) {
        showToast(`Failed to update risk parameters: ${e}`, "error");
    }
}

function switchTab(tabId) {
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));

    const tab = document.getElementById(tabId);
    if (tab) tab.classList.add("active");

    const btn = Array.from(document.querySelectorAll(".tab-btn")).find(b => b.getAttribute("onclick")?.includes(tabId));
    if (btn) btn.classList.add("active");
}

function showToast(message, type = "info") {
    const toast = document.getElementById("toast");
    toast.innerText = message;
    toast.style.display = "block";
    if (type === "error") {
        toast.style.borderColor = "var(--color-red)";
        toast.style.color = "var(--color-red)";
    } else if (type === "success") {
        toast.style.borderColor = "var(--color-green)";
        toast.style.color = "var(--color-green)";
    } else {
        toast.style.borderColor = "var(--border-color)";
        toast.style.color = "var(--text-primary)";
    }
    setTimeout(() => { toast.style.display = "none"; }, 3500);
}

// Helpers
function formatCurrency(val) {
    if (val === undefined || val === null || isNaN(val)) return "0.00";
    return val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatNumber(val) {
    if (val === undefined || val === null || isNaN(val)) return "0.00";
    if (val < 10) return val.toFixed(4);
    return val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
