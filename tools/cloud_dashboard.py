#!/usr/bin/env python3
"""
Lightweight Cloud Server Dashboard
Real-time monitoring of Scaleway Mac mini instances

Usage:
    python tools/cloud_dashboard.py

Access: http://localhost:8087
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add tools directory to path
tools_dir = Path(__file__).parent
sys.path.insert(0, str(tools_dir))

from scaleway_provider import ScalewayProvider

app = FastAPI(title="Cloud Server Dashboard")

# Load Scaleway config
config_path = Path.home() / 'KnockOff' / 'cloud_config.json'
if config_path.exists():
    with open(config_path) as f:
        config = json.load(f)
    scaleway_config = config.get('scaleway', {})
else:
    scaleway_config = {}

# Initialize provider
try:
    provider = ScalewayProvider(scaleway_config)
    provider_available = True
except Exception as e:
    provider_available = False
    provider_error = str(e)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard page"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Cloud Server Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'SF Mono', 'Consolas', monospace;
            background: #0a0a0a;
            color: #00ff00;
            padding: 20px;
        }

        .header {
            border: 2px solid #00ff00;
            padding: 20px;
            margin-bottom: 20px;
            background: #0f0f0f;
        }

        h1 {
            font-size: 24px;
            margin-bottom: 10px;
        }

        .status {
            font-size: 14px;
            color: #888;
        }

        .servers-container {
            display: grid;
            gap: 20px;
        }

        .server-card {
            border: 2px solid #00ff00;
            padding: 20px;
            background: #0f0f0f;
            position: relative;
        }

        .server-card.offline {
            border-color: #444;
            color: #666;
        }

        .server-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #00ff00;
        }

        .server-name {
            font-size: 18px;
            font-weight: bold;
        }

        .server-status {
            padding: 5px 15px;
            background: #00ff00;
            color: #0a0a0a;
            font-size: 12px;
            font-weight: bold;
            border-radius: 3px;
        }

        .server-status.starting {
            background: #ffaa00;
        }

        .server-status.ready {
            background: #00ff00;
        }

        .server-status.error {
            background: #ff0000;
            color: #fff;
        }

        .server-info {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 15px;
        }

        .info-item {
            font-size: 13px;
        }

        .info-label {
            color: #666;
            margin-bottom: 5px;
        }

        .info-value {
            color: #00ff00;
            font-weight: bold;
        }

        .current-task {
            background: #1a1a1a;
            padding: 15px;
            margin-top: 15px;
            border-left: 3px solid #00ff00;
        }

        .task-label {
            color: #666;
            font-size: 12px;
            margin-bottom: 5px;
        }

        .task-value {
            color: #00ff00;
            font-size: 14px;
        }

        .actions {
            margin-top: 15px;
            display: flex;
            gap: 10px;
        }

        button {
            padding: 8px 20px;
            background: #00ff00;
            color: #0a0a0a;
            border: none;
            font-family: inherit;
            font-size: 12px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.2s;
        }

        button:hover {
            background: #00cc00;
        }

        button.danger {
            background: #ff0000;
            color: #fff;
        }

        button.danger:hover {
            background: #cc0000;
        }

        .no-servers {
            text-align: center;
            padding: 60px;
            color: #666;
            font-size: 18px;
        }

        .cost-tracker {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #0f0f0f;
            border: 2px solid #00ff00;
            padding: 15px 25px;
            min-width: 200px;
        }

        .cost-label {
            color: #666;
            font-size: 12px;
            margin-bottom: 5px;
        }

        .cost-value {
            color: #00ff00;
            font-size: 24px;
            font-weight: bold;
        }

        .pulse {
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .refresh-indicator {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #0f0f0f;
            border: 1px solid #00ff00;
            padding: 10px 20px;
            font-size: 12px;
            opacity: 0;
            transition: opacity 0.3s;
        }

        .refresh-indicator.active {
            opacity: 1;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>☁️ CLOUD SERVER DASHBOARD</h1>
        <div class="status">Scaleway Mac mini Monitoring • Real-time Updates</div>
    </div>

    <div class="cost-tracker">
        <div class="cost-label">TOTAL COST</div>
        <div class="cost-value" id="totalCost">€0.00</div>
    </div>

    <div class="servers-container" id="serversContainer">
        <div class="no-servers">
            <div class="pulse">⏳ Connecting to Scaleway...</div>
        </div>
    </div>

    <div class="refresh-indicator" id="refreshIndicator">
        🔄 Updating...
    </div>

    <script>
        const eventSource = new EventSource('/stream');
        const serversContainer = document.getElementById('serversContainer');
        const totalCostEl = document.getElementById('totalCost');
        const refreshIndicator = document.getElementById('refreshIndicator');

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);

            // Show refresh indicator
            refreshIndicator.classList.add('active');
            setTimeout(() => refreshIndicator.classList.remove('active'), 500);

            // Update total cost
            totalCostEl.textContent = `€${data.total_cost.toFixed(2)}`;

            // Update servers
            if (data.servers.length === 0) {
                serversContainer.innerHTML = `
                    <div class="no-servers">
                        No active servers
                        <br><br>
                        <div style="font-size: 14px; color: #888;">
                        Servers will appear here when running
                        </div>
                    </div>
                `;
            } else {
                serversContainer.innerHTML = data.servers.map(server => `
                    <div class="server-card ${server.status === 'ready' ? '' : 'offline'}">
                        <div class="server-header">
                            <div class="server-name">${server.name}</div>
                            <div class="server-status ${server.status}">${server.status.toUpperCase()}</div>
                        </div>

                        <div class="server-info">
                            <div class="info-item">
                                <div class="info-label">Type</div>
                                <div class="info-value">${server.type}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">IP Address</div>
                                <div class="info-value">${server.ip || 'Pending...'}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Uptime</div>
                                <div class="info-value">${server.uptime}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Cost</div>
                                <div class="info-value">€${server.cost.toFixed(2)}</div>
                            </div>
                        </div>

                        ${server.current_task ? `
                        <div class="current-task">
                            <div class="task-label">CURRENT TASK</div>
                            <div class="task-value">${server.current_task}</div>
                        </div>
                        ` : ''}

                        <div class="actions">
                            ${server.ip ? `
                            <button onclick="copySSH('${server.ip}')">📋 Copy SSH</button>
                            ` : ''}
                            <button class="danger" onclick="destroyServer('${server.id}')">🗑️ Destroy</button>
                        </div>
                    </div>
                `).join('');
            }
        };

        function copySSH(ip) {
            const ssh = `ssh admin@${ip}`;
            navigator.clipboard.writeText(ssh);
            alert(`Copied to clipboard:\\n${ssh}`);
        }

        async function destroyServer(id) {
            if (!confirm('Destroy this server? This will stop any running tasks.')) return;

            const response = await fetch(`/destroy/${id}`, { method: 'POST' });
            const result = await response.json();
            alert(result.message);
        }

        // Keep connection alive
        eventSource.onerror = function() {
            console.log('Connection lost, reconnecting...');
        };
    </script>
</body>
</html>
    """
    return html


async def get_server_data():
    """Get current server data from Scaleway"""
    if not provider_available:
        return {
            'servers': [],
            'total_cost': 0,
            'error': provider_error if 'provider_error' in globals() else 'Provider not available'
        }

    try:
        servers = provider.list_servers()

        server_data = []
        total_cost = 0

        for server in servers:
            # Calculate uptime
            created_at = datetime.fromisoformat(server.get('created_at', '').replace('Z', '+00:00'))
            uptime = datetime.now(created_at.tzinfo) - created_at
            uptime_str = f"{uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m"

            # Calculate cost (rounds up to nearest hour)
            hours = max(1, (uptime.seconds + 3599) // 3600)
            cost = hours * provider.get_hourly_rate()
            total_cost += cost

            server_data.append({
                'id': server['id'],
                'name': server['name'],
                'type': server.get('type', 'Unknown'),
                'status': server.get('status', 'unknown'),
                'ip': server.get('ip', {}).get('address'),
                'uptime': uptime_str,
                'cost': cost,
                'current_task': server.get('current_task', None)  # Can be set via tags
            })

        return {
            'servers': server_data,
            'total_cost': total_cost
        }

    except Exception as e:
        return {
            'servers': [],
            'total_cost': 0,
            'error': str(e)
        }


@app.get("/stream")
async def stream():
    """Server-sent events stream for real-time updates"""
    async def event_generator():
        while True:
            data = await get_server_data()
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(10)  # Update every 10 seconds

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/destroy/{server_id}")
async def destroy_server(server_id: str):
    """Destroy a server"""
    try:
        provider.delete_server(server_id)
        return {"success": True, "message": f"Server {server_id} destroyed"}
    except Exception as e:
        return {"success": False, "message": str(e)}


if __name__ == '__main__':
    import uvicorn
    print("🌐 Cloud Server Dashboard starting...")
    print("📊 Access at: http://localhost:8087")
    print("")
    uvicorn.run(app, host="0.0.0.0", port=8087, log_level="error")
