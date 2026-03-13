#!/usr/bin/env python3
"""
KnockOff Cloud Orchestrator
Automates video generation on remote Mac servers (MacStadium, Macly, etc.)

Usage:
    from cloud_orchestrator import CloudOrchestrator

    orchestrator = CloudOrchestrator(provider='macstadium')
    result = orchestrator.generate_video(
        script_path='scripts/my-video.md',
        avatar='vg-host',
        quality='Improved'
    )
"""

import os
import sys
import json
import time
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import paramiko
from scp import SCPClient

# Add tools directory to path for imports
tools_dir = Path(__file__).parent
if str(tools_dir) not in sys.path:
    sys.path.insert(0, str(tools_dir))

# Import cloud providers
try:
    from scaleway_provider import ScalewayProvider
except ImportError as e:
    ScalewayProvider = None
    logging.debug(f"Scaleway provider import failed: {e}")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'logs/cloud_orchestrator_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CloudProvider:
    """Base class for cloud Mac providers"""

    def __init__(self, config: Dict):
        self.config = config
        self.ssh_client = None
        self.server_ip = None
        self.server_id = None

    def provision_server(self) -> Dict:
        """Provision a new Mac server"""
        raise NotImplementedError

    def destroy_server(self, server_id: str):
        """Destroy/release a Mac server"""
        raise NotImplementedError

    def get_server_status(self, server_id: str) -> str:
        """Get server status"""
        raise NotImplementedError


class MacStadiumProvider(CloudProvider):
    """MacStadium on-demand Mac server provider"""

    def provision_server(self) -> Dict:
        """Provision MacStadium server (API integration coming)"""
        logger.info("MacStadium provisioning - Using pre-configured server")
        # TODO: Implement MacStadium API when available
        # For now, use pre-configured server details
        return {
            'server_id': self.config.get('server_id', 'manual'),
            'ip': self.config['host'],
            'username': self.config['username'],
            'status': 'ready'
        }

    def destroy_server(self, server_id: str):
        logger.info(f"MacStadium server {server_id} - Manual cleanup required")
        # TODO: Implement API-based teardown


class MaclyProvider(CloudProvider):
    """Macly on-demand Mac server provider"""

    def provision_server(self) -> Dict:
        """Provision Macly server (API integration coming)"""
        logger.info("Macly provisioning - Using pre-configured server")
        # TODO: Implement Macly API when available
        return {
            'server_id': self.config.get('server_id', 'manual'),
            'ip': self.config['host'],
            'username': self.config['username'],
            'status': 'ready'
        }

    def destroy_server(self, server_id: str):
        logger.info(f"Macly server {server_id} - Manual cleanup required")


class CloudOrchestrator:
    """
    Main orchestrator for cloud-based KnockOff video generation
    Handles full workflow: provision → deploy → generate → retrieve → cleanup
    """

    def __init__(self, provider: str = 'macstadium', config_path: Optional[str] = None):
        """
        Initialize orchestrator

        Args:
            provider: 'macstadium', 'macly', or 'custom'
            config_path: Path to cloud config JSON file
        """
        self.provider_name = provider
        self.knockoff_dir = Path.home() / 'KnockOff'
        self.config = self._load_config(config_path)
        self.provider = self._init_provider()
        self.ssh_client = None
        self.costs = {
            'compute_time': 0,
            'data_transfer': 0,
            'total': 0
        }
        self.start_time = None

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load cloud provider configuration"""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)

        # Default config file location
        default_config = self.knockoff_dir / 'cloud_config.json'
        if default_config.exists():
            with open(default_config, 'r') as f:
                return json.load(f)

        # Fallback to environment variables or defaults
        logger.warning("No config file found, using defaults")
        return {
            'macstadium': {
                'host': os.getenv('MACSTADIUM_HOST', ''),
                'username': os.getenv('MACSTADIUM_USER', 'admin'),
                'password': os.getenv('MACSTADIUM_PASS', ''),
                'ssh_key': os.getenv('MACSTADIUM_KEY', ''),
                'hourly_rate': 0.85  # Per test estimate
            },
            'macly': {
                'host': os.getenv('MACLY_HOST', ''),
                'username': os.getenv('MACLY_USER', 'admin'),
                'password': os.getenv('MACLY_PASS', ''),
                'ssh_key': os.getenv('MACLY_KEY', ''),
                'hourly_rate': 0.85
            },
            'scaleway': {
                'access_key': os.getenv('SCW_ACCESS_KEY', ''),
                'secret_key': os.getenv('SCW_SECRET_KEY', ''),
                'project_id': os.getenv('SCW_PROJECT_ID', ''),
                'organization_id': os.getenv('SCW_ORGANIZATION_ID', ''),
                'zone': os.getenv('SCW_ZONE', 'fr-par-1'),
                'mac_type': 'm2',  # m1, m2, or m4
                'hourly_rate': 0.17  # M2 rate in EUR
            }
        }

    def _init_provider(self) -> CloudProvider:
        """Initialize cloud provider"""
        provider_config = self.config.get(self.provider_name, {})

        if self.provider_name == 'macstadium':
            return MacStadiumProvider(provider_config)
        elif self.provider_name == 'macly':
            return MaclyProvider(provider_config)
        elif self.provider_name == 'scaleway':
            if ScalewayProvider is None:
                raise ImportError("Scaleway provider not available. Check scaleway_provider.py")
            return ScalewayProvider(provider_config)
        else:
            raise ValueError(f"Unknown provider: {self.provider_name}")

    def _connect_ssh(self, host: str, username: str, password: str = None, key_path: str = None):
        """Establish SSH connection to remote server"""
        logger.info(f"Connecting to {host} as {username}...")

        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if key_path and os.path.exists(key_path):
                self.ssh_client.connect(host, username=username, key_filename=key_path)
            elif password:
                self.ssh_client.connect(host, username=username, password=password)
            else:
                raise ValueError("No valid authentication method provided")

            logger.info("SSH connection established")
            return True
        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
            return False

    def _run_remote_command(self, command: str, workdir: str = None) -> tuple:
        """Execute command on remote server"""
        if workdir:
            command = f"cd {workdir} && {command}"

        logger.debug(f"Running: {command}")
        stdin, stdout, stderr = self.ssh_client.exec_command(command)

        output = stdout.read().decode()
        errors = stderr.read().decode()
        exit_code = stdout.channel.recv_exit_status()

        if exit_code != 0:
            logger.warning(f"Command failed with exit code {exit_code}")
            if errors:
                logger.warning(f"Errors: {errors}")

        return output, errors, exit_code

    def _upload_file(self, local_path: str, remote_path: str):
        """Upload file to remote server"""
        logger.info(f"Uploading {local_path} → {remote_path}")
        with SCPClient(self.ssh_client.get_transport()) as scp:
            scp.put(local_path, remote_path, recursive=os.path.isdir(local_path))

    def _download_file(self, remote_path: str, local_path: str):
        """Download file from remote server"""
        logger.info(f"Downloading {remote_path} → {local_path}")
        with SCPClient(self.ssh_client.get_transport()) as scp:
            scp.get(remote_path, local_path, recursive=True)

    def deploy_knockoff(self, remote_dir: str = '/tmp/KnockOff'):
        """Deploy KnockOff to remote server"""
        logger.info("=" * 60)
        logger.info("DEPLOYING KNOCKOFF TO REMOTE SERVER")
        logger.info("=" * 60)

        # Create remote directory
        self._run_remote_command(f"mkdir -p {remote_dir}")

        # Upload setup script
        logger.info("Uploading setup.sh...")
        setup_script = self.knockoff_dir / 'setup.sh'
        self._upload_file(str(setup_script), f"{remote_dir}/setup.sh")

        # Upload requirements.txt
        logger.info("Uploading requirements.txt...")
        requirements = self.knockoff_dir / 'requirements.txt'
        self._upload_file(str(requirements), f"{remote_dir}/requirements.txt")

        # Upload tools directory
        logger.info("Uploading tools/...")
        tools_dir = self.knockoff_dir / 'tools'
        self._upload_file(str(tools_dir), f"{remote_dir}/tools")

        # Make setup script executable and run it
        logger.info("Running setup.sh on remote server...")
        self._run_remote_command(f"chmod +x {remote_dir}/setup.sh")

        output, errors, exit_code = self._run_remote_command(
            f"{remote_dir}/setup.sh {remote_dir}",
            workdir=remote_dir
        )

        if exit_code == 0:
            logger.info("✓ KnockOff deployed successfully")
            return True
        else:
            logger.error("✗ KnockOff deployment failed")
            logger.error(errors)
            return False

    def upload_assets(self, avatar: str, broll: List[str] = None,
                     overlays: List[str] = None, music: List[str] = None,
                     remote_dir: str = '/tmp/KnockOff'):
        """Upload required assets to remote server"""
        logger.info("=" * 60)
        logger.info("UPLOADING ASSETS")
        logger.info("=" * 60)

        # Upload avatar
        avatar_path = self.knockoff_dir / 'avatars' / f'{avatar}.mp4'
        if avatar_path.exists():
            logger.info(f"Uploading avatar: {avatar}.mp4")
            self._upload_file(str(avatar_path), f"{remote_dir}/avatars/{avatar}.mp4")
        else:
            logger.error(f"Avatar not found: {avatar_path}")
            return False

        # Upload B-roll
        if broll:
            for broll_file in broll:
                broll_path = self.knockoff_dir / 'broll' / broll_file
                if broll_path.exists():
                    logger.info(f"Uploading B-roll: {broll_file}")
                    self._upload_file(str(broll_path), f"{remote_dir}/broll/{broll_file}")

        # Upload overlays
        if overlays:
            for overlay_file in overlays:
                overlay_path = self.knockoff_dir / 'overlays' / overlay_file
                if overlay_path.exists():
                    logger.info(f"Uploading overlay: {overlay_file}")
                    self._upload_file(str(overlay_path), f"{remote_dir}/overlays/{overlay_file}")

        # Upload music
        if music:
            for music_file in music:
                music_path = self.knockoff_dir / 'music' / music_file
                if music_path.exists():
                    logger.info(f"Uploading music: {music_file}")
                    self._upload_file(str(music_path), f"{remote_dir}/music/{music_file}")

        logger.info("✓ Assets uploaded successfully")
        return True

    def generate_video(self, script_path: str, avatar: str,
                      quality: str = 'Improved', format: str = 'portrait',
                      voice: str = 'joe', remote_dir: str = '/tmp/KnockOff') -> Dict:
        """
        Full workflow: provision → deploy → generate → retrieve

        Args:
            script_path: Path to script .md file
            avatar: Avatar name (without .mp4 extension)
            quality: Fast, Improved, or Enhanced
            format: portrait, landscape, or square
            voice: joe or lessac
            remote_dir: Remote KnockOff installation directory

        Returns:
            Dict with results and metadata
        """
        self.start_time = time.time()

        try:
            # Step 1: Provision server
            logger.info("=" * 60)
            logger.info("STEP 1: PROVISIONING SERVER")
            logger.info("=" * 60)
            server_info = self.provider.provision_server()

            # Step 2: Connect via SSH
            logger.info("=" * 60)
            logger.info("STEP 2: CONNECTING TO SERVER")
            logger.info("=" * 60)

            provider_config = self.config[self.provider_name]
            connected = self._connect_ssh(
                host=provider_config['host'],
                username=provider_config['username'],
                password=provider_config.get('password'),
                key_path=provider_config.get('ssh_key')
            )

            if not connected:
                raise Exception("Failed to connect to server")

            # Step 3: Deploy KnockOff
            logger.info("=" * 60)
            logger.info("STEP 3: DEPLOYING KNOCKOFF")
            logger.info("=" * 60)
            if not self.deploy_knockoff(remote_dir):
                raise Exception("Failed to deploy KnockOff")

            # Step 4: Upload script
            logger.info("=" * 60)
            logger.info("STEP 4: UPLOADING SCRIPT")
            logger.info("=" * 60)
            script_file = Path(script_path)
            remote_script = f"{remote_dir}/scripts/{script_file.name}"
            self._upload_file(str(script_file), remote_script)

            # Step 5: Parse script and upload required assets
            logger.info("=" * 60)
            logger.info("STEP 5: UPLOADING ASSETS")
            logger.info("=" * 60)
            # TODO: Parse script to extract required B-roll/overlays/music
            # For now, upload common assets
            self.upload_assets(avatar=avatar, remote_dir=remote_dir)

            # Step 6: Generate video
            logger.info("=" * 60)
            logger.info("STEP 6: GENERATING VIDEO")
            logger.info("=" * 60)

            generate_cmd = (
                f"cd {remote_dir} && "
                f"source .venv/bin/activate && "
                f"python tools/generate_avatar_video.py "
                f"--script {remote_script} "
                f"--avatar {avatar} "
                f"--quality {quality} "
                f"--format {format} "
                f"--voice {voice}"
            )

            logger.info("Running generation command...")
            output, errors, exit_code = self._run_remote_command(generate_cmd)

            if exit_code != 0:
                logger.error("Video generation failed")
                logger.error(errors)
                raise Exception("Video generation failed")

            logger.info("✓ Video generated successfully")
            logger.info(output)

            # Step 7: Download result
            logger.info("=" * 60)
            logger.info("STEP 7: DOWNLOADING RESULT")
            logger.info("=" * 60)

            # Find output file (usually in .tmp/avatar/output/)
            find_cmd = f"find {remote_dir}/.tmp/avatar/output -name '*.mp4' -type f"
            output, _, _ = self._run_remote_command(find_cmd)

            if output.strip():
                remote_video = output.strip().split('\n')[0]  # Get first match
                local_output = self.knockoff_dir / '.tmp' / 'avatar' / 'output' / Path(remote_video).name
                local_output.parent.mkdir(parents=True, exist_ok=True)

                self._download_file(remote_video, str(local_output))
                logger.info(f"✓ Video downloaded to: {local_output}")

                # Also copy to NAS if mounted
                nas_path = Path('/Volumes/homes/dmpgh/KnockOff')
                if nas_path.exists():
                    import shutil
                    nas_output = nas_path / local_output.name
                    shutil.copy2(local_output, nas_output)
                    logger.info(f"✓ Video copied to NAS: {nas_output}")
            else:
                logger.warning("Could not find generated video file")
                local_output = None

            # Step 8: Cleanup
            logger.info("=" * 60)
            logger.info("STEP 8: CLEANUP")
            logger.info("=" * 60)
            self._run_remote_command(f"rm -rf {remote_dir}")

            # Calculate costs
            elapsed_time = time.time() - self.start_time
            elapsed_minutes = elapsed_time / 60
            hourly_rate = self.config[self.provider_name].get('hourly_rate', 0.85)
            compute_cost = (elapsed_minutes / 60) * hourly_rate

            self.costs = {
                'compute_time_minutes': round(elapsed_minutes, 2),
                'compute_cost': round(compute_cost, 2),
                'data_transfer': 0.0,  # TODO: Calculate based on file sizes
                'total': round(compute_cost, 2)
            }

            # Return results
            result = {
                'success': True,
                'video_path': str(local_output) if local_output else None,
                'elapsed_time': elapsed_time,
                'costs': self.costs,
                'server_id': server_info['server_id']
            }

            logger.info("=" * 60)
            logger.info("✅ GENERATION COMPLETE")
            logger.info("=" * 60)
            logger.info(f"Time: {elapsed_minutes:.1f} minutes")
            logger.info(f"Cost: ${self.costs['total']:.2f}")
            logger.info(f"Video: {local_output}")

            return result

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'costs': self.costs
            }

        finally:
            # Always close SSH connection
            if self.ssh_client:
                self.ssh_client.close()
                logger.info("SSH connection closed")


if __name__ == '__main__':
    # Example usage
    orchestrator = CloudOrchestrator(provider='macstadium')
    result = orchestrator.generate_video(
        script_path='scripts/test.md',
        avatar='vg-host',
        quality='Improved'
    )

    if result['success']:
        print(f"\n✅ Video generated: {result['video_path']}")
        print(f"💰 Total cost: ${result['costs']['total']:.2f}")
    else:
        print(f"\n❌ Generation failed: {result['error']}")
