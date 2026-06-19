"use strict";

async function apiRequest(path, options = {}) {
    const res = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function formatNumber(n) {
    if (typeof n !== "number") return n ?? "—";
    return n.toLocaleString();
}

function badge(text, type = "primary") {
    return `<span class="badge badge-${type}">${text}</span>`;
}

function statusBadge(status) {
    const map = {
        open: ["Open", "success"],
        closed: ["Closed", "danger"],
        pending: ["Pending", "warning"],
        accepted: ["Accepted", "success"],
        denied: ["Denied", "danger"],
    };
    const [label, color] = map[status] || [status, "primary"];
    return badge(label, color);
}

function renderTicketsTable(tickets, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!tickets.length) {
        container.innerHTML = '<div class="empty-state"><h3>No tickets yet</h3></div>';
        return;
    }
    const rows = tickets.map(t => `
        <tr>
            <td>#${t.ticket_id}</td>
            <td>${t.type || "Support"}</td>
            <td>${statusBadge(t.status)}</td>
            <td>${t.user_id}</td>
            <td>${t.created_at ? new Date(t.created_at).toLocaleDateString() : "—"}</td>
        </tr>
    `).join("");
    container.innerHTML = `
        <div class="table-container">
            <table>
                <thead><tr><th>#</th><th>Type</th><th>Status</th><th>User ID</th><th>Created</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
}

function renderLeaderboard(entries, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!entries.length) {
        container.innerHTML = '<div class="empty-state"><h3>No data yet</h3></div>';
        return;
    }
    const medals = ["🥇", "🥈", "🥉"];
    const rows = entries.map((e, i) => `
        <tr>
            <td>${medals[i] || i + 1}</td>
            <td>${e.user_id}</td>
            <td>${formatNumber(e.level ?? 0)}</td>
            <td>${formatNumber(e.xp ?? 0)}</td>
            <td>${formatNumber(e.messages ?? 0)}</td>
        </tr>
    `).join("");
    container.innerHTML = `
        <div class="table-container">
            <table>
                <thead><tr><th>Rank</th><th>User ID</th><th>Level</th><th>XP</th><th>Messages</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
}

async function saveConfig(guildId, formId) {
    const form = document.getElementById(formId);
    if (!form) return;
    const data = {};
    form.querySelectorAll("[name]").forEach(el => {
        if (el.type === "checkbox") {
            data[el.name] = el.checked;
        } else {
            data[el.name] = el.value;
        }
    });
    try {
        await apiRequest(`/api/${guildId}/config`, {
            method: "POST",
            body: JSON.stringify(data),
        });
        showToast("Settings saved!", "success");
    } catch (e) {
        showToast("Failed to save settings.", "error");
    }
}

function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `alert alert-${type}`;
    toast.style.cssText = "position:fixed;bottom:24px;right:24px;z-index:9999;min-width:250px;animation:fadeIn 0.2s";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

document.addEventListener("DOMContentLoaded", () => {
    const GUILD_ID = document.body.dataset.guildId;
    if (!GUILD_ID) return;

    const ticketContainer = document.getElementById("tickets-table");
    if (ticketContainer) {
        apiRequest(`/api/${GUILD_ID}/tickets`).then(data => renderTicketsTable(data, "tickets-table")).catch(() => {});
    }
    const lbContainer = document.getElementById("leaderboard-table");
    if (lbContainer) {
        apiRequest(`/api/${GUILD_ID}/leaderboard`).then(data => renderLeaderboard(data, "leaderboard-table")).catch(() => {});
    }

    const configForms = document.querySelectorAll("[data-config-form]");
    configForms.forEach(form => {
        apiRequest(`/api/${GUILD_ID}/config`).then(cfg => {
            form.querySelectorAll("[name]").forEach(el => {
                const val = cfg[el.name];
                if (val === undefined) return;
                if (el.type === "checkbox") el.checked = !!val;
                else el.value = val;
            });
        }).catch(() => {});
    });

    document.querySelectorAll("[data-save-config]").forEach(btn => {
        btn.addEventListener("click", () => {
            const formId = btn.dataset.saveConfig;
            saveConfig(GUILD_ID, formId);
        });
    });
});
