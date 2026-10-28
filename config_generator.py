"""
Генератор конфигов Huawei для TOR- и Core-коммутаторов.

Восстановлен по сборке Nuitka от 07.10 (исходник был случайно перезаписан
копией парсера USG). Логика команд сохранена, исправлено одно:
если TOR кластера подключены к разным Core, интерфейсы раскладываются
по своим Core, а не все в первый.
"""
import os
import re

import db


def _vlan_block(vlans):
    """Объявления VLAN с описаниями."""
    commands = []
    for vlan in vlans:
        commands.append(f"vlan {vlan['vlan_id']}")
        if vlan.get("description"):
            commands.append(f"  description {vlan['description']}")
        commands.append("  quit")
    return commands


def _trunk_block(interface, vlans):
    """Интерфейс-транк с разрешёнными VLAN."""
    commands = [f"interface {interface}"]
    for vlan in vlans:
        commands.append(f"  port trunk allow-pass vlan {vlan['vlan_id']}")
    commands.append("  quit")
    return commands


def generate_configs_for_selection(selected_cluster_ids, selected_vlan_ids):
    """
    Генерирует конфиги для выбранных кластеров и VLAN.

    selected_cluster_ids: список ID кластеров
    selected_vlan_ids: список VLAN ID из общей базы
    Возвращает {hostname: [команды]}.
    """
    configs = {}

    selected_vlans = []
    for vlan_id in selected_vlan_ids:
        vlan = db.get_vlan_by_id(vlan_id)
        if vlan:
            selected_vlans.append(vlan)

    for cluster_id in selected_cluster_ids:
        cluster = db.get_cluster(cluster_id)
        if not cluster:
            continue
        cluster_name = cluster["name"]
        switches = db.list_switches(cluster_id)

        # --- TOR ---
        for sw in switches:
            hostname = sw["hostname"]
            server_interfaces = db.get_switch_interfaces(sw["id"])

            commands = configs.setdefault(hostname, [])
            commands.append(f"! === Кластер {cluster_name} ===")
            commands.extend(_vlan_block(selected_vlans))
            for iface in server_interfaces:
                commands.extend(_trunk_block(iface, selected_vlans))
            commands.extend(_trunk_block(sw["uplink_interface"], selected_vlans))
            commands.append("")

        # --- Core: группируем TOR кластера по их Core ---
        by_core = {}
        for sw in switches:
            by_core.setdefault(sw["core_hostname"], []).append(sw)

        for core_hostname, core_switches in by_core.items():
            commands = configs.setdefault(core_hostname, [])
            commands.append(f"! === Кластер {cluster_name} ===")
            commands.extend(_vlan_block(selected_vlans))
            for sw in core_switches:
                commands.extend(_trunk_block(sw["core_interface"], selected_vlans))
            commands.append("")

    return configs


def format_configs(configs):
    output = []
    for hostname in sorted(configs.keys()):
        output.append("=" * 60)
        output.append(f"Коммутатор: {hostname}")
        output.append("=" * 60)
        output.extend(configs[hostname])
        output.append("")
    return "\n".join(output)


def save_configs_to_file(configs, filepath):
    text = format_configs(configs)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def save_configs_to_dir(configs, dirpath):
    """Сохраняет каждый коммутатор в отдельный <hostname>.txt. Возвращает число файлов."""
    os.makedirs(dirpath, exist_ok=True)
    for hostname, commands in configs.items():
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", hostname)
        with open(os.path.join(dirpath, f"{safe_name}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(commands) + "\n")
    return len(configs)
