#!/usr/bin/env python3
"""
KnockOff Cloud Video Generator - Simple CLI Interface

ONE COMMAND TO RULE THEM ALL:
    python tools/cloud_generate.py --script scripts/my-video.md --avatar vg-host

Handles everything automatically:
    ✓ Provisions cloud Mac server
    ✓ Deploys KnockOff
    ✓ Uploads assets
    ✓ Generates video
    ✓ Downloads result
    ✓ Cleans up server
    ✓ Shows costs
"""

import argparse
import sys
import json
from pathlib import Path
from cloud_orchestrator import CloudOrchestrator


def main():
    parser = argparse.ArgumentParser(
        description='Generate KnockOff videos on cloud Mac servers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate with default settings
  python tools/cloud_generate.py -s scripts/my-video.md -a vg-host

  # Generate with Enhanced quality
  python tools/cloud_generate.py -s scripts/my-video.md -a vg-host --quality Enhanced

  # Use specific provider
  python tools/cloud_generate.py -s scripts/my-video.md -a vg-host --provider macly

  # Dry run (test connection only)
  python tools/cloud_generate.py --test-connection

Cost estimate: ~$0.85 per 2-minute video at Improved quality
        """
    )

    parser.add_argument('-s', '--script', required=False,
                       help='Path to script .md file (e.g., scripts/my-video.md)')
    parser.add_argument('-a', '--avatar', required=False,
                       help='Avatar name without .mp4 extension (e.g., vg-host)')
    parser.add_argument('-q', '--quality',
                       choices=['Fast', 'Improved', 'Enhanced'],
                       default='Improved',
                       help='Quality level (default: Improved)')
    parser.add_argument('-f', '--format',
                       choices=['portrait', 'landscape', 'square'],
                       default='portrait',
                       help='Video format (default: portrait)')
    parser.add_argument('-v', '--voice',
                       choices=['joe', 'lessac'],
                       default='joe',
                       help='TTS voice: joe (male) or lessac (female)')
    parser.add_argument('--provider',
                       choices=['macstadium', 'macly', 'scaleway'],
                       default='scaleway',
                       help='Cloud provider (default: scaleway)')
    parser.add_argument('--config',
                       help='Path to cloud_config.json')
    parser.add_argument('--test-connection',
                       action='store_true',
                       help='Test SSH connection without generating')
    parser.add_argument('--dry-run',
                       action='store_true',
                       help='Show what would be done without executing')

    args = parser.parse_args()

    # Print banner
    print("=" * 70)
    print(" " * 15 + "KnockOff Cloud Video Generator")
    print("=" * 70)
    print()

    # Validate required arguments (unless testing)
    if not args.test_connection and not args.dry_run:
        if not args.script:
            print("❌ Error: --script is required")
            parser.print_help()
            sys.exit(1)
        if not args.avatar:
            print("❌ Error: --avatar is required")
            parser.print_help()
            sys.exit(1)

        # Check if script exists
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"❌ Error: Script not found: {args.script}")
            sys.exit(1)

    # Initialize orchestrator
    try:
        orchestrator = CloudOrchestrator(
            provider=args.provider,
            config_path=args.config
        )
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        print()
        print("Make sure cloud_config.json exists with your server details.")
        print("See cloud_config.example.json for template.")
        sys.exit(1)

    # Test connection mode
    if args.test_connection:
        print("🔌 Testing SSH connection...")
        try:
            provider_config = orchestrator.config[args.provider]
            connected = orchestrator._connect_ssh(
                host=provider_config['host'],
                username=provider_config['username'],
                password=provider_config.get('password'),
                key_path=provider_config.get('ssh_key')
            )
            if connected:
                print("✅ SSH connection successful!")
                orchestrator.ssh_client.close()
                sys.exit(0)
            else:
                print("❌ SSH connection failed")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            sys.exit(1)

    # Dry run mode
    if args.dry_run:
        print("📋 DRY RUN - Nothing will be executed")
        print()
        print(f"Provider:     {args.provider}")
        print(f"Script:       {args.script}")
        print(f"Avatar:       {args.avatar}")
        print(f"Quality:      {args.quality}")
        print(f"Format:       {args.format}")
        print(f"Voice:        {args.voice}")
        print()
        print("Workflow:")
        print("  1. Provision server")
        print("  2. Connect via SSH")
        print("  3. Deploy KnockOff")
        print("  4. Upload script and assets")
        print("  5. Generate video")
        print("  6. Download result")
        print("  7. Cleanup")
        print()
        sys.exit(0)

    # Show job details
    print(f"🎬 Job Details:")
    print(f"   Provider:  {args.provider}")
    print(f"   Script:    {args.script}")
    print(f"   Avatar:    {args.avatar}")
    print(f"   Quality:   {args.quality}")
    print(f"   Format:    {args.format}")
    print(f"   Voice:     {args.voice}")
    print()

    # Confirm before proceeding (costs money!)
    response = input("💰 This will cost money. Proceed? (y/N): ")
    if response.lower() != 'y':
        print("❌ Cancelled by user")
        sys.exit(0)

    print()
    print("🚀 Starting cloud generation workflow...")
    print()

    # Run the generation
    try:
        result = orchestrator.generate_video(
            script_path=args.script,
            avatar=args.avatar,
            quality=args.quality,
            format=args.format,
            voice=args.voice
        )

        print()
        print("=" * 70)
        if result['success']:
            print(" " * 25 + "✅ SUCCESS!")
            print("=" * 70)
            print()
            print(f"📹 Video:     {result['video_path']}")
            print(f"⏱️  Time:      {result['costs']['compute_time_minutes']:.1f} minutes")
            print(f"💰 Cost:      ${result['costs']['total']:.2f}")
            print()

            # Check if video was also saved to NAS
            nas_path = Path('/Volumes/homes/dmpgh/KnockOff')
            if nas_path.exists():
                print(f"💾 Also saved to NAS: {nas_path / Path(result['video_path']).name}")

            sys.exit(0)
        else:
            print(" " * 25 + "❌ FAILED")
            print("=" * 70)
            print()
            print(f"Error: {result['error']}")
            print()
            if result['costs']['total'] > 0:
                print(f"💰 Cost incurred: ${result['costs']['total']:.2f}")
            sys.exit(1)

    except KeyboardInterrupt:
        print()
        print("❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
