"""Filesystem and naming rules shared by the bridge and its tests (no bpy)."""

import json
import ipaddress
import os
from pathlib import Path
import re


class BridgeError(RuntimeError):
    pass


def discovery_endpoint(value):
    """Validate IPv4 multicast without DNS resolution or remote unicast access."""
    try:
        host, port = value.strip().strip('"').split(':')
        address = ipaddress.IPv4Address(host)
        port = int(port)
        if not address.is_multicast or not 1 <= port <= 65535:
            raise ValueError()
    except (ValueError, AttributeError) as exc:
        raise BridgeError('Discovery Endpoint must be IPv4 multicast:port, for example 239.0.0.1:6768') from exc
    return str(address), port


def project_discovery(project, engine=None, override=''):
    """Read relevant scalar config layers; command-line/runtime changes need override.

    This intentionally does not modify Unreal configuration or implement unrelated
    INI array merging. Python's endpoint/bind/enabled settings are scalar values.
    """
    project = Path(project)
    paths = []
    if engine:
        base = Path(engine) / 'Engine/Config'
        paths.extend([base / 'Base.ini', base / 'BaseEngine.ini',
                      base / 'Windows/BaseWindowsEngine.ini'])
    config = project.parent / 'Config'
    paths.extend([config / 'DefaultEngine.ini'])
    if engine:
        paths.append(Path(engine) / 'Engine/Config/Windows/WindowsEngine.ini')
    paths.extend([config / 'Windows/WindowsEngine.ini', config / 'UserEngine.ini',
                  project.parent / 'Saved/Config/Windows/Engine.ini',
                  project.parent / 'Saved/Config/WindowsEditor/Engine.ini'])
    endpoint, source = '239.0.0.1:6766', 'Unreal default'
    section = '/script/pythonscriptplugin.pythonscriptpluginsettings'
    enabled = None
    for path in paths:
        try:
            lines = path.read_text(encoding='utf-8-sig').splitlines()
        except OSError:
            continue
        active = False
        for line in lines:
            line = line.strip()
            if not line or line.startswith((';', '#')):
                continue
            if line.startswith('[') and line.endswith(']'):
                active = line[1:-1].strip().casefold() == section
                continue
            if not active or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.split(';', 1)[0].strip().strip('"')
            if key.strip().casefold() == 'remoteexecutionmulticastgroupendpoint':
                endpoint, source = value, str(path)
            elif key.strip().casefold() == 'bremoteexecution':
                enabled = value.casefold() in ('true', '1', 'yes')
    if override.strip():
        endpoint, source = override.strip(), 'Blender override'
    host, port = discovery_endpoint(endpoint)
    return {'endpoint': f'{host}:{port}', 'source': source, 'enabled': enabled}


def asset_name(value):
    # Deliberately conservative: never silently change the Empty's asset name.
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value) or len(value) > 100:
        raise BridgeError(f'{value!r}: use an Empty name starting with a letter or underscore, '
                          'containing only letters, digits and underscores (maximum 100 characters)')
    return value


def content_path(value):
    value = value.strip().replace('\\', '/').rstrip('/')
    if value != '/Game' and not value.startswith('/Game/'):
        raise BridgeError('Content Folder must be /Game or a folder under /Game')
    for part in value.split('/')[2:]:
        asset_name(part)
    return value


def project_file(value):
    path = Path(value).expanduser().resolve()
    if path.suffix.lower() != '.uproject' or not path.is_file():
        raise BridgeError('Choose an existing Unreal .uproject file')
    try:
        json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise BridgeError(f'Cannot read Unreal project: {exc}') from exc
    return path


def same_path(first, second):
    return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))


def folder_from_disk(project, directory):
    root = (project.parent / 'Content').resolve()
    try:
        relative = Path(directory).resolve().relative_to(root)
    except ValueError as exc:
        raise BridgeError('Choose a folder inside the selected project\'s Content directory') from exc
    return '/Game' if relative == Path('.') else content_path('/Game/' + relative.as_posix())


REMOTE_CLIENT = Path('Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python/remote_execution.py')


def normalize_engine(value):
    """Accept an install root, Engine directory, or editor executable path."""
    text = os.path.expandvars(str(value).strip().strip('"').strip("'"))
    if not text:
        raise BridgeError('Choose an Unreal installation folder or UnrealEditor.exe')
    path = Path(text).expanduser().resolve()
    # Searching ancestors also accepts Binaries/Win64 and paths pasted from Explorer.
    for candidate in (path, *path.parents):
        if (candidate / REMOTE_CLIENT).is_file():
            return candidate
    raise BridgeError(f'Invalid Unreal engine path: {path}. Expected an installation containing '
                      f'{REMOTE_CLIENT.as_posix()}; choose UE_5.7, Engine, or UnrealEditor.exe')


def engine_version(root):
    try:
        data = json.loads((Path(root) / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
        return tuple(int(data[key]) for key in ('MajorVersion', 'MinorVersion', 'PatchVersion'))
    except (OSError, ValueError, TypeError, KeyError):
        return ()


def _registry_engines():
    if os.name != 'nt':
        return []
    import winreg
    found = []
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\EpicGames\Unreal Engine',
                                0, winreg.KEY_READ | view) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    association = winreg.EnumKey(key, index)
                    try:
                        with winreg.OpenKey(key, association) as child:
                            found.append((association, winreg.QueryValueEx(child, 'InstalledDirectory')[0]))
                    except OSError:
                        pass
        except OSError:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Epic Games\Unreal Engine\Builds') as key:
            for index in range(winreg.QueryInfoKey(key)[1]):
                association, path, _ = winreg.EnumValue(key, index)
                found.append((association, path))
    except OSError:
        pass
    return found


def installed_engines():
    """Validated, deduplicated installs. Ignore stale or malformed registrations."""
    candidates = list(_registry_engines())
    launcher = Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'Epic/UnrealEngineLauncher/LauncherInstalled.dat'
    try:
        data = json.loads(launcher.read_text(encoding='utf-8-sig'))
        for entry in data.get('InstallationList', []):
            if not isinstance(entry, dict):
                continue
            name = entry.get('AppName', '')
            if isinstance(name, str) and name.startswith('UE_') and entry.get('InstallLocation'):
                candidates.append((name[3:], entry['InstallLocation']))
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    for variable in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
        base = Path(os.environ.get(variable, 'C:/Program Files')) / 'Epic Games'
        try:
            candidates.extend((path.name[3:], str(path)) for path in base.glob('UE_*') if path.is_dir())
        except OSError:
            pass
    records = {}
    for association, value in candidates:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            root = normalize_engine(value)
        except (BridgeError, OSError, ValueError):
            continue
        key = os.path.normcase(str(root))
        record = records.setdefault(key, {'root': root, 'version': engine_version(root), 'associations': set()})
        record['associations'].add(str(association).casefold())
    return sorted(records.values(), key=lambda item: (item['version'], str(item['root'])), reverse=True)


def engine_root(project, override=''):
    """Explicit manual selection wins; automatic selection never guesses a version."""
    if override and str(override).strip():
        return normalize_engine(override)
    project = project_file(str(project))
    association = str(json.loads(project.read_text(encoding='utf-8-sig')).get('EngineAssociation', '')).strip()
    matches = []
    for record in installed_engines():
        version = '.'.join(map(str, record['version'][:2]))
        if association and (association.casefold() in record['associations'] or association == version):
            matches.append(record['root'])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise BridgeError(f'Multiple installed engines match {association}. Use Detect Installed Builds to choose one')
    raise BridgeError(f'No installed engine matches project EngineAssociation {association!r}. '
                      'Use Detect Installed Builds or Browse Engine to select an installation explicitly')