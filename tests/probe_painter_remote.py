"""Safe Painter diagnostics; --launch starts a remote-enabled instance if absent."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def load_bridge():
    # Ordinary Python must not import the addon entry point (which requires bpy).
    spec = importlib.util.spec_from_file_location(
        'mbt_probe_bridge', ROOT / 'features/substance_painter/bridge.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def painter_running():
    """Fail closed if Windows process discovery cannot establish a safe launch."""
    if os.name != 'nt':
        raise RuntimeError('Guarded automatic launch currently supports Windows only')
    command = ("$ErrorActionPreference='Stop'; @(Get-Process | Where-Object "
               "{$_.ProcessName -like '*Painter*'}).Count")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, check=True, timeout=15)
    return int(result.stdout.strip()) > 0


def ensure_endpoint(bridge, client, allow_launch=False, executable='', startup_timeout=90):
    try:
        client.check_endpoint()
        return False
    except bridge.ConnectionUnavailable:
        if not allow_launch:
            raise
    if client.port != 60041:
        raise bridge.BridgeError('Automatic launch requires default port 60041')
    if painter_running():
        raise bridge.BridgeError('Painter is already running but remote scripting is unreachable. '
                                'No second instance launched; save/close the existing session first.')
    process = bridge.launch(executable or bridge.detect_executable())
    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        try:
            client.check_endpoint()
            return True
        except bridge.ConnectionUnavailable:
            if process.poll() is not None:
                raise bridge.BridgeError('Painter exited before remote scripting became available')
            time.sleep(1)
    raise bridge.BridgeError('Painter startup timed out; inspect license/startup dialogs. Painter left running.')


def probe(port=60041, allow_launch=False, executable='', startup_timeout=90):
    bridge = load_bridge()
    client = bridge.Client(port=port, timeout=5)
    launched = ensure_endpoint(bridge, client, allow_launch, executable, startup_timeout)
    ping = client.execute('__import__("json").dumps({"mbt_ping": 1})')
    if ping.get('mbt_ping') != 1:
        raise bridge.BridgeError('Painter Python handshake was not recognized')
    source = (ROOT / 'features/substance_painter/painter_remote.py').read_text(encoding='utf-8')
    # Isolated namespace: do not replace helpers or state belonging to an active job.
    expression = (
        f'(lambda ns: (exec({source!r}, ns), '
        '__import__("json").dumps({"api": __import__("json").loads(ns["_mbt_probe"]()), '
        '"projection": __import__("json").loads(ns["_mbt_projection_capabilities"]())}))[1])({})')
    result = client.execute(expression)
    result.update(host=client.host, port=client.port, project_modified=False, launched=launched)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=60041)
    parser.add_argument('--launch', action='store_true', help='Launch remote-enabled Painter only if no instance is running')
    parser.add_argument('--executable', default='', help='Painter executable; otherwise auto-detect')
    parser.add_argument('--startup-timeout', type=float, default=90)
    parser.add_argument('--output', type=Path,
                        default=Path(tempfile.gettempdir()) / 'mbt_painter_remote_probe.json')
    args = parser.parse_args()
    try:
        result = probe(args.port, args.launch, args.executable, args.startup_timeout)
    except Exception as error:
        result = {'state': 'FAILED', 'error': str(error), 'project_modified': False}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print('Report: ' + str(args.output.resolve()))
    return 1 if result.get('state') == 'FAILED' else 0


if __name__ == '__main__':
    sys.exit(main())