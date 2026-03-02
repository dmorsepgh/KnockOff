#!/usr/bin/env python3
"""
Scaleway Mac mini Provider for KnockOff Cloud Orchestration

Handles:
- Spinning up Mac mini M1/M2/M4 instances on-demand
- Waiting for instances to be ready
- Getting SSH connection details
- Destroying instances after use
- Cost tracking

API Docs: https://www.scaleway.com/en/developers/api/apple-silicon/
"""

import os
import time
import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ScalewayProvider:
    """
    Scaleway Bare Metal Mac mini provider

    Supports M1, M2, and M4 Mac minis with on-demand provisioning
    """

    # Scaleway API endpoints
    API_BASE = "https://api.scaleway.com"
    APPLE_SILICON_API = "/apple-silicon/v1alpha1"

    # Mac mini server types (from Scaleway API)
    OFFERS = {
        'm2': 'M2-M',  # M2 medium
        'm2-l': 'M2-L',  # M2 large
        'm4': 'M4-S',  # M4 small
        'm4-m': 'M4-M',  # M4 medium
        'm4-xl': 'M4-XL'  # M4 extra large
    }

    # Hourly rates in EUR (approximate)
    HOURLY_RATES = {
        'm2': 0.17,
        'm2-l': 0.20,
        'm4': 0.22,
        'm4-m': 0.25,
        'm4-xl': 0.30
    }

    def __init__(self, config: Dict):
        """
        Initialize Scaleway provider

        Args:
            config: Dict with keys:
                - access_key: Scaleway access key
                - secret_key: Scaleway secret key
                - project_id: Project ID
                - organization_id: Organization ID
                - zone: Zone (default: fr-par-1)
                - mac_type: m1, m2, or m4 (default: m2)
        """
        self.access_key = config.get('access_key') or os.getenv('SCW_ACCESS_KEY')
        self.secret_key = config.get('secret_key') or os.getenv('SCW_SECRET_KEY')
        self.project_id = config.get('project_id') or os.getenv('SCW_PROJECT_ID')
        self.organization_id = config.get('organization_id') or os.getenv('SCW_ORGANIZATION_ID')
        self.zone = config.get('zone', 'fr-par-1')
        self.mac_type = config.get('mac_type', 'm2')

        if not all([self.access_key, self.secret_key, self.project_id]):
            raise ValueError("Missing Scaleway credentials. Set access_key, secret_key, and project_id")

        self.session = requests.Session()
        self.session.headers.update({
            'X-Auth-Token': self.secret_key,
            'Content-Type': 'application/json'
        })

        self.server_id = None
        self.server_ip = None

    def _api_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make API request to Scaleway"""
        url = f"{self.API_BASE}{self.APPLE_SILICON_API}{endpoint}"

        logger.debug(f"{method} {url}")

        response = self.session.request(method, url, **kwargs)

        if response.status_code not in [200, 201, 202, 204]:
            logger.error(f"API request failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            response.raise_for_status()

        if response.content:
            return response.json()
        return {}

    def list_servers(self) -> list:
        """List all Mac mini servers in project"""
        endpoint = f"/zones/{self.zone}/servers"
        params = {'project_id': self.project_id}

        result = self._api_request('GET', endpoint, params=params)
        return result.get('servers', [])

    def create_server(self, name: str = None) -> Dict:
        """
        Create a new Mac mini instance

        Args:
            name: Server name (default: knockoff-{timestamp})

        Returns:
            Dict with server details including id and status
        """
        if not name:
            name = f"knockoff-{int(time.time())}"

        endpoint = f"/zones/{self.zone}/servers"

        # Get available OS image (latest macOS)
        images = self._get_available_images()
        if not images:
            raise Exception("No macOS images available")

        image_id = images[0]['id']

        payload = {
            'name': name,
            'project_id': self.project_id,
            'type': self.OFFERS[self.mac_type],
            'os_id': image_id
        }

        logger.info(f"Creating {self.mac_type.upper()} Mac mini: {name}")

        result = self._api_request('POST', endpoint, json=payload)
        server = result.get('server', {})

        self.server_id = server['id']
        logger.info(f"Server created: {self.server_id}")

        return server

    def _get_available_images(self) -> list:
        """Get available macOS images for zone"""
        endpoint = f"/zones/{self.zone}/os"

        result = self._api_request('GET', endpoint)
        os_list = result.get('os', [])

        # Filter for macOS and sort by version (latest first)
        macos_images = [img for img in os_list if 'macos' in img.get('name', '').lower()]
        macos_images.sort(key=lambda x: x.get('version', ''), reverse=True)

        return macos_images

    def get_server_status(self, server_id: str = None) -> str:
        """
        Get server status

        Returns: 'starting', 'ready', 'stopping', 'stopped', etc.
        """
        if not server_id:
            server_id = self.server_id

        endpoint = f"/zones/{self.zone}/servers/{server_id}"

        result = self._api_request('GET', endpoint)
        server = result.get('server', {})

        status = server.get('status', 'unknown')

        # Update IP if available
        if server.get('ip'):
            self.server_ip = server['ip']['address']

        return status

    def wait_for_ready(self, server_id: str = None, timeout: int = 600) -> bool:
        """
        Wait for server to be ready

        Args:
            server_id: Server ID (uses self.server_id if not provided)
            timeout: Max wait time in seconds (default: 10 minutes)

        Returns:
            True if ready, False if timeout
        """
        if not server_id:
            server_id = self.server_id

        logger.info("Waiting for server to be ready...")

        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_server_status(server_id)

            logger.debug(f"Server status: {status}")

            if status == 'ready':
                logger.info(f"✓ Server ready! IP: {self.server_ip}")
                return True

            if status in ['error', 'stopped']:
                logger.error(f"Server failed to start: {status}")
                return False

            time.sleep(10)  # Check every 10 seconds

        logger.error("Timeout waiting for server to be ready")
        return False

    def get_ssh_details(self, server_id: str = None) -> Dict:
        """
        Get SSH connection details

        Returns:
            Dict with 'host', 'username', 'password' (if available)
        """
        if not server_id:
            server_id = self.server_id

        endpoint = f"/zones/{self.zone}/servers/{server_id}"

        result = self._api_request('GET', endpoint)
        server = result.get('server', {})

        ssh_details = {
            'host': server.get('ip', {}).get('address'),
            'username': 'admin',  # Default Scaleway Mac user
            'password': server.get('admin_password'),  # May not be available
        }

        return ssh_details

    def delete_server(self, server_id: str = None):
        """
        Delete/destroy a server

        Args:
            server_id: Server ID (uses self.server_id if not provided)
        """
        if not server_id:
            server_id = self.server_id

        logger.info(f"Deleting server: {server_id}")

        endpoint = f"/zones/{self.zone}/servers/{server_id}"

        self._api_request('DELETE', endpoint)

        logger.info("✓ Server deleted")

    def get_hourly_rate(self) -> float:
        """Get hourly rate for current Mac type in EUR"""
        return self.HOURLY_RATES.get(self.mac_type, 0.17)

    def calculate_cost(self, minutes: float) -> float:
        """
        Calculate cost for given runtime

        Note: Scaleway rounds up to nearest hour

        Args:
            minutes: Runtime in minutes

        Returns:
            Cost in EUR
        """
        hours = max(1, int((minutes + 59) / 60))  # Round up to nearest hour
        rate = self.get_hourly_rate()

        return hours * rate

    # Compatibility methods for cloud_orchestrator.py

    def provision_server(self) -> Dict:
        """Provision a new Mac mini server"""
        server = self.create_server()

        # Wait for it to be ready
        if not self.wait_for_ready(server['id']):
            raise Exception("Server failed to start")

        ssh_details = self.get_ssh_details(server['id'])

        return {
            'server_id': server['id'],
            'ip': ssh_details['host'],
            'username': ssh_details['username'],
            'password': ssh_details.get('password'),
            'status': 'ready'
        }

    def destroy_server(self, server_id: str):
        """Destroy a server"""
        self.delete_server(server_id)


if __name__ == '__main__':
    # Test Scaleway provider
    import sys

    logging.basicConfig(level=logging.INFO)

    # Load credentials from environment
    config = {
        'zone': 'fr-par-1',
        'mac_type': 'm1'  # Use cheapest for testing
    }

    try:
        provider = ScalewayProvider(config)

        # List existing servers
        print("\n📋 Existing servers:")
        servers = provider.list_servers()
        for server in servers:
            print(f"  - {server['name']} ({server['id']}): {server['status']}")

        # Test create (uncomment to actually create)
        # print("\n🚀 Creating test server...")
        # server = provider.create_server('knockoff-test')
        # print(f"✓ Created: {server['id']}")

        # print("\n⏳ Waiting for ready...")
        # if provider.wait_for_ready():
        #     ssh = provider.get_ssh_details()
        #     print(f"✓ SSH: {ssh['username']}@{ssh['host']}")

        # print("\n🗑️  Deleting server...")
        # provider.delete_server()
        # print("✓ Deleted")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
