#!/usr/bin/env python3
"""OBS Remote Control — manage OBS on M4 from M4 Pro via websocket."""

import argparse
import sys
import obsws_python as obs

OBS_HOST = "m4.local"
OBS_PORT = 4455
OBS_PASS = "1tv3T63Sq17KK7Xa"


def connect():
    try:
        cl = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASS, timeout=5)
        return cl
    except Exception as e:
        print(f"Failed to connect to OBS at {OBS_HOST}:{OBS_PORT}: {e}")
        sys.exit(1)


def cmd_status(cl):
    v = cl.get_version()
    print(f"OBS {v.obs_version} | WebSocket {v.obs_web_socket_version}")

    scenes = cl.get_scene_list()
    current = scenes.current_program_scene_name
    print(f"\nCurrent scene: {current}")
    print(f"All scenes:")
    for s in scenes.scenes:
        marker = " ← active" if s["sceneName"] == current else ""
        print(f"  - {s['sceneName']}{marker}")

    rec = cl.get_record_status()
    print(f"\nRecording: {'YES' if rec.output_active else 'no'}")

    vcam = cl.get_virtual_cam_status()
    print(f"Virtual Camera: {'ON' if vcam.output_active else 'off'}")


def cmd_scenes(cl):
    scenes = cl.get_scene_list()
    current = scenes.current_program_scene_name
    for s in scenes.scenes:
        marker = " ← active" if s["sceneName"] == current else ""
        print(f"  {s['sceneName']}{marker}")


def cmd_switch(cl, scene_name):
    cl.set_current_program_scene(scene_name)
    print(f"Switched to: {scene_name}")


def cmd_inputs(cl):
    inputs = cl.get_input_list()
    for i in inputs.inputs:
        print(f"  {i['inputName']} ({i['inputKind']})")


def cmd_vcam(cl, action):
    if action == "start":
        cl.start_virtual_cam()
        print("Virtual camera started")
    elif action == "stop":
        cl.stop_virtual_cam()
        print("Virtual camera stopped")
    elif action == "toggle":
        cl.toggle_virtual_cam()
        status = cl.get_virtual_cam_status()
        state = "ON" if status.output_active else "OFF"
        print(f"Virtual camera toggled → {state}")


def cmd_record(cl, action):
    if action == "start":
        cl.start_record()
        print("Recording started")
    elif action == "stop":
        result = cl.stop_record()
        print(f"Recording stopped → {result.output_path}")
    elif action == "toggle":
        cl.toggle_record()
        status = cl.get_record_status()
        state = "recording" if status.output_active else "stopped"
        print(f"Recording toggled → {state}")


def cmd_media(cl, source_name, file_path):
    cl.set_input_settings(source_name, {"local_file": file_path}, overlay=True)
    print(f"Set {source_name} → {file_path}")


def cmd_screenshot(cl, source=None, path="/tmp/obs-screenshot.png"):
    if source:
        result = cl.save_source_screenshot(source, "png", path, 1920, 1080, 100)
    else:
        scenes = cl.get_scene_list()
        current = scenes.current_program_scene_name
        result = cl.save_source_screenshot(current, "png", path, 1920, 1080, 100)
    print(f"Screenshot saved → {path}")


def main():
    parser = argparse.ArgumentParser(description="OBS Remote Control for M4")
    sub = parser.add_subparsers(dest="command", help="Command to run")

    sub.add_parser("status", help="Show OBS status")
    sub.add_parser("scenes", help="List all scenes")
    sub.add_parser("inputs", help="List all inputs")

    p_switch = sub.add_parser("switch", help="Switch to a scene")
    p_switch.add_argument("scene", help="Scene name")

    p_vcam = sub.add_parser("vcam", help="Virtual camera control")
    p_vcam.add_argument("action", choices=["start", "stop", "toggle"])

    p_rec = sub.add_parser("record", help="Recording control")
    p_rec.add_argument("action", choices=["start", "stop", "toggle"])

    p_media = sub.add_parser("media", help="Set media source file")
    p_media.add_argument("source", help="Source name in OBS")
    p_media.add_argument("file", help="Path to media file")

    p_ss = sub.add_parser("screenshot", help="Take a screenshot")
    p_ss.add_argument("--source", help="Source name (default: current scene)")
    p_ss.add_argument("--path", default="/tmp/obs-screenshot.png", help="Save path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cl = connect()

    try:
        if args.command == "status":
            cmd_status(cl)
        elif args.command == "scenes":
            cmd_scenes(cl)
        elif args.command == "inputs":
            cmd_inputs(cl)
        elif args.command == "switch":
            cmd_switch(cl, args.scene)
        elif args.command == "vcam":
            cmd_vcam(cl, args.action)
        elif args.command == "record":
            cmd_record(cl, args.action)
        elif args.command == "media":
            cmd_media(cl, args.source, args.file)
        elif args.command == "screenshot":
            cmd_screenshot(cl, args.source, args.path)
    finally:
        cl.disconnect()


if __name__ == "__main__":
    main()
