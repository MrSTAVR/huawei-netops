"""
Парсер конфигурации Huawei USG: поиск security-policy и nat-policy по IP/подсети.

Конфиг VRP структурирован отступами:
    security-policy          <- блок верхнего уровня (отступ 0)
     rule name X             <- правило (отступ 1)
      source-address ...     <- атрибуты правила (отступ 2)
Любая строка с нулевым отступом (или '#') закрывает текущий блок,
поэтому угадывать «конец блока» по ключевым словам не нужно.
"""
import ipaddress


# Предопределённые сервисы Huawei USG: имя -> [(protocol, port_from, port_to)].
# port_from/port_to = None — протокол без портов (icmp, gre, ...) или динамические порты.
_P = None
BUILTIN_SERVICES = {
    'ad': [('udp', 1773, 1773)],
    'ah': [('ah', _P, _P)],
    'bgp': [('tcp', 179, 179)],
    'biff': [('udp', 512, 512)],
    'bootpc': [('udp', 68, 68)],
    'bootps': [('udp', 67, 67)],
    'chargen': [('tcp', 19, 19)],
    'daytime': [('tcp', 13, 13)],
    'diameter': [('tcp', 3868, 3868), ('sctp', 3868, 3868)],
    'discard-tcp': [('tcp', 9, 9)],
    'discard-udp': [('udp', 9, 9)],
    'dns': [('udp', 53, 53)],
    'dns-tcp': [('tcp', 53, 53)],
    'dnsix': [('udp', 90, 90)],
    'echo-tcp': [('tcp', 7, 7)],
    'echo-udp': [('udp', 7, 7)],
    'esp': [('esp', _P, _P)],
    'exec': [('tcp', 512, 512)],
    'fin-rst': [('tcp', _P, _P)],
    'finger': [('tcp', 79, 79)],
    'first-fin': [('tcp', _P, _P)],
    'fragment': [('any', _P, _P)],
    'ftp': [('tcp', 21, 21)],
    'ftp-data': [('tcp', 20, 20)],
    'gopher': [('tcp', 70, 70)],
    'gre': [('gre', _P, _P)],
    'gtpc': [('udp', 2123, 2123)],
    'gtpu': [('udp', 2152, 2152)],
    'gtpv0': [('udp', 3386, 3386)],
    'h225': [('tcp', 1720, 1720)],
    'h245': [('tcp', _P, _P)],
    'h323': [('tcp', 1719, 1719)],
    'h323-rtcp': [('tcp', _P, _P)],
    'h323-rtp': [('tcp', _P, _P)],
    'h323-t120': [('tcp', _P, _P)],
    'hostname': [('tcp', 101, 101)],
    'http': [('tcp', 80, 80)],
    'https': [('tcp', 443, 443)],
    'hwcc': [('udp', 10000, 10000)],
    'icmp': [('icmp', _P, _P)],
    'icmpv6': [('icmpv6', _P, _P)],
    'igmp': [('igmp', _P, _P)],
    'ils': [('tcp', 1002, 1002)],
    'imap': [('tcp', 143, 143)],
    'imaps': [('tcp', 993, 993)],
    'ipinip': [('ipinip', _P, _P)],
    'ipsec-isakmp': [('udp', 500, 500)],
    'irc': [('tcp', 194, 194)],
    'kerberos-tcp': [('tcp', 88, 88)],
    'kerberos-udp': [('udp', 88, 88)],
    'kerberos': [('tcp', 88, 88), ('udp', 88, 88)],
    'klogin': [('tcp', 543, 543)],
    'kshell': [('tcp', 544, 544)],
    'l2tp': [('udp', 1701, 1701)],
    'login': [('tcp', 513, 513)],
    'lpd': [('tcp', 515, 515)],
    'mgcp': [('udp', 2727, 2727)],
    'mgcp-rtcp': [('udp', _P, _P)],
    'mgcp-rtp': [('udp', _P, _P)],
    'mms': [('tcp', 1755, 1755)],
    'mms-rtcp': [('tcp', _P, _P)],
    'mms-rtp': [('tcp', _P, _P)],
    'mobileip-ag': [('udp', 434, 434)],
    'mobileip-mn': [('udp', 435, 435)],
    'msn': [('tcp', 1863, 1863)],
    'msn-audio': [('udp', 7001, 7001)],
    'msn-derived': [('tcp', _P, _P)],
    'msn-discard': [('udp', 9, 9)],
    'msn-stun': [('udp', 3478, 3478)],
    'multihome': [('sctp', _P, _P)],
    'mysql': [('tcp', 3306, 3306)],
    'mssql': [('tcp', 1433, 1433)],
    'nameserver': [('udp', 42, 42)],
    'netbios-datagram': [('udp', 138, 138)],
    'netbios-name': [('udp', 137, 137)],
    'netbios-session': [('tcp', 139, 139)],
    'netbios-ssn': [('udp', 139, 139)],
    'netbios-ns': [('udp', 137, 137)],
    'netbios-dgm': [('udp', 138, 138)],
    'nntp': [('tcp', 119, 119)],
    'ntp': [('udp', 123, 123)],
    'ospf': [('ospf', _P, _P)],
    'p2p': [('any', _P, _P)],
    'pop2': [('tcp', 109, 109)],
    'pop3': [('tcp', 110, 110)],
    'pop3s': [('tcp', 995, 995)],
    'portalserver': [('udp', 62314, 62314)],
    'postgres': [('tcp', 5432, 5432)],
    'pptp': [('tcp', 1723, 1723)],
    'pptp-gre': [('gre', _P, _P)],
    'qq': [('udp', 8000, 8000)],
    'qq-derived': [('udp', _P, _P)],
    'radius': [('udp', 1812, 1812)],
    'radius-accounting': [('udp', 1813, 1813)],
    'ras': [('udp', 1719, 1719)],
    'rdp-tcp': [('tcp', 3389, 3389)],
    'rdp-udp': [('udp', 3389, 3389)],
    'rdp': [('tcp', 3389, 3389), ('udp', 3389, 3389)],
    'redis': [('tcp', 6379, 6379)],
    'rip': [('udp', 520, 520)],
    'rpc': [('tcp', 135, 135), ('udp', 135, 135)],
    'rsh': [('tcp', 514, 514)],
    'rsh-data': [('tcp', _P, _P)],
    'rtsp': [('udp', 554, 554), ('tcp', 554, 554)],
    'rtsp-rtcp': [('tcp', _P, _P)],
    'rtsp-rtp': [('tcp', _P, _P)],
    'sccp': [('tcp', 2000, 2000)],
    'sccp-rtp': [('tcp', _P, _P)],
    'sctp': [('sctp', _P, _P)],
    'sctp-close': [('sctp', _P, _P)],
    'sctp-init': [('sctp', _P, _P)],
    'sip': [('udp', 5060, 5060), ('tcp', 5060, 5060)],
    'sip-rtcp': [('udp', _P, _P)],
    'sip-rtp': [('udp', _P, _P)],
    'smb': [('tcp', 445, 445)],
    'cifs': [('tcp', 445, 445)],
    'smtp': [('tcp', 25, 25)],
    'smtps': [('tcp', 465, 465)],
    'snmp': [('udp', 161, 161)],
    'snmptrap': [('udp', 162, 162)],
    'sqlnet': [('tcp', 1521, 1521)],
    'sqlnet-data': [('tcp', _P, _P)],
    'sqlserver': [('tcp', 1433, 1433)],
    'ssh': [('tcp', 22, 22)],
    'stun-derived': [('udp', _P, _P)],
    'sunrpc-tcp': [('tcp', 111, 111)],
    'sunrpc-udp': [('udp', 111, 111)],
    'syn': [('tcp', _P, _P)],
    'syslog': [('udp', 514, 514)],
    'tacacs': [('tcp', 49, 49)],
    'tacacs-ds': [('udp', 65, 65)],
    'talk-tcp': [('tcp', 517, 517)],
    'talk-udp': [('udp', 517, 517)],
    'tcp': [('tcp', 0, 65535)],
    'telnet': [('tcp', 23, 23)],
    'tftp': [('udp', 69, 69)],
    'time-tcp': [('tcp', 37, 37)],
    'time-udp': [('udp', 37, 37)],
    'udp': [('udp', 0, 65535)],
    'uucp': [('tcp', 540, 540)],
    'vxlan': [('udp', 4789, 4789)],
    'who': [('udp', 513, 513)],
    'whois': [('tcp', 43, 43)],
    'x11': [('tcp', 6000, 6063)],
    'xdmcp': [('udp', 177, 177)],
    'any': [('any', 0, 65535)],
    'dhcp': [('udp', 67, 68)],
    'mongodb': [('tcp', 27017, 27017)],
}

# Колонки результата: (ключ, заголовок, ширина в таблице)
COLUMNS = [
    ('kind', 'Тип правила', 125),
    ('sec_name', 'security-policy name', 170),
    ('src_name', 'Source name', 160),
    ('src_ip', 'Source IP', 190),
    ('nat_name', 'nat-policy name', 150),
    ('src_nat', 'Src (NAT)', 130),
    ('dst_nat', 'Dst (NAT)', 130),
    ('dst_name', 'Destination name', 160),
    ('dst_ip', 'Destination IP', 190),
    ('port', 'Port', 120),
    ('proto', 'Protocol', 80),
    ('action', 'Action', 80),
    ('src_zone', 'Source zone', 110),
    ('dst_zone', 'Destination zone', 120),
]


# ---------- Токенизация и разбор адресов ----------

def smart_split(line):
    """Разбивает строку на токены с учётом кавычек: service "smb service" -> ['service', 'smb service']."""
    tokens = []
    current = []
    quote = None
    for char in line:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in ('"', "'"):
            quote = char
        elif char.isspace():
            if current:
                tokens.append(''.join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append(''.join(current))
    return tokens


def _network(ip, mask, wildcard):
    """
    IP + маска -> IPv4Network.
    mask: длина префикса ('24'), маска ('255.255.255.0') или wildcard ('0.0.0.255').
    wildcard=True — маска без слова 'mask' (так USG пишет wildcard; '0' означает хост).
    """
    try:
        if mask.isdigit():
            prefix = int(mask)
            if wildcard and prefix == 0:
                prefix = 32
            return ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
        if wildcard:
            inverted = int(ipaddress.IPv4Address(mask)) ^ 0xFFFFFFFF
            mask = str(ipaddress.IPv4Address(inverted))
        return ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    except ValueError:
        return None


def _range(start, end):
    try:
        return list(ipaddress.summarize_address_range(ipaddress.IPv4Address(start), ipaddress.IPv4Address(end)))
    except ValueError:
        return []


def _parse_address_tokens(tokens):
    """
    Разбирает хвост адресной команды:
      address-set NAME | IP mask M | IP M | IP | range A B
    Возвращает ('set', name) | ('net', [networks]) | None.
    """
    if not tokens:
        return None
    if tokens[0] == 'address-set' and len(tokens) > 1:
        return ('set', tokens[1])
    if tokens[0] == 'range' and len(tokens) > 2:
        return ('net', _range(tokens[1], tokens[2]))
    ip = tokens[0]
    if len(tokens) >= 3 and tokens[1] == 'mask':
        net = _network(ip, tokens[2], wildcard=False)
    elif len(tokens) >= 2:
        net = _network(ip, tokens[1], wildcard=True)
    else:
        net = _network(ip, '32', wildcard=False)
    return ('net', [net]) if net else None


def _parse_ports(tokens):
    """Ищет 'destination-port A [to B]'. Без него — весь диапазон."""
    if 'destination-port' not in tokens:
        return 0, 65535
    idx = tokens.index('destination-port')
    try:
        lo = int(tokens[idx + 1])
        hi = int(tokens[idx + 3]) if len(tokens) > idx + 3 and tokens[idx + 2] == 'to' else lo
        return lo, hi
    except (IndexError, ValueError):
        return 0, 65535


def _parse_protocol(tokens):
    """tokens начинаются после 'protocol': ['tcp', 'source-port', ...] -> (proto, lo, hi)."""
    proto = tokens[0]
    if proto in ('tcp', 'udp', 'sctp'):
        lo, hi = _parse_ports(tokens)
        return (proto, lo, hi)
    return (proto, None, None)


# ---------- Парсинг конфига ----------

def _new_rule(name, nat=False):
    rule = {
        'name': name,
        'source_zones': [],
        'destination_zones': [],
        'source_addresses': [],
        'destination_addresses': [],
        'services': [],
        'action': None,
        'disabled': False,
        'description': '',
        'raw': [],
    }
    if nat:
        rule.update({'nat_type': None, 'nat_target': None})
    return rule


def _parse_rule_line(rule, tokens):
    key = tokens[0]
    rest = tokens[1:]
    if key == 'disable':
        rule['disabled'] = True
    elif key == 'description':
        rule['description'] = ' '.join(rest)
    elif key == 'source-zone' and rest:
        rule['source_zones'].append(rest[0])
    elif key == 'destination-zone' and rest:
        rule['destination_zones'].append(rest[0])
    elif key in ('source-address', 'destination-address'):
        addr = _parse_address_tokens(rest)
        if addr:
            target = 'source_addresses' if key == 'source-address' else 'destination_addresses'
            rule[target].append(addr)
    elif key == 'service' and rest:
        if rest[0] == 'protocol' and len(rest) > 1:
            rule['services'].append(('inline', _parse_protocol(rest[1:])))
        else:
            rule['services'].append(('name', rest[0]))
    elif key == 'action' and rest:
        if 'nat_type' in rule:
            # action source-nat easy-ip | action source-nat address-group G | action destination-nat address-group G
            rule['nat_type'] = rest[0]
            if 'address-group' in rest:
                idx = rest.index('address-group')
                rule['nat_target'] = rest[idx + 1] if idx + 1 < len(rest) else None
            elif len(rest) > 1:
                rule['nat_target'] = ' '.join(rest[1:])
            rule['action'] = rest[0]
        else:
            rule['action'] = rest[0]


def parse_config(config_text):
    """Парсит конфиг USG за один проход. Возвращает dict с объектами и правилами."""
    address_sets = {}   # name -> {'type': object|group, 'entries': [('net', [..]) | ('set', name)]}
    service_sets = {}   # name -> [(proto, lo, hi)]
    nat_groups = {}     # name -> {'mode': str, 'sections': [(start, end)]}
    security_rules = []
    nat_rules = []
    zones = set()

    block = None        # тип текущего блока верхнего уровня
    name = None         # имя текущего объекта
    rule = None         # текущее правило политики

    for line in config_text.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        # --- Строка верхнего уровня: закрывает предыдущий блок и, возможно, открывает новый ---
        if indent == 0:
            block, name, rule = None, None, None
            tokens = smart_split(stripped)
            if len(tokens) >= 5 and tokens[:2] == ['ip', 'address-set'] and tokens[3] == 'type':
                block, name = 'address_set', tokens[2]
                address_sets[name] = {'type': tokens[4], 'entries': []}
            elif len(tokens) >= 3 and tokens[:2] == ['ip', 'service-set']:
                block, name = 'service_set', tokens[2]
                service_sets[name] = []
            elif len(tokens) >= 3 and tokens[:2] == ['nat', 'address-group']:
                block, name = 'nat_group', tokens[2]
                nat_groups[name] = {'mode': None, 'sections': []}
            elif tokens[:1] == ['security-policy'] and len(tokens) == 1:
                block = 'security_policy'
            elif tokens[:1] == ['nat-policy'] and len(tokens) == 1:
                block = 'nat_policy'
            elif len(tokens) >= 3 and tokens[:2] == ['firewall', 'zone']:
                # firewall zone trust | firewall zone name wifi id 5
                zones.add(tokens[3] if tokens[2] == 'name' and len(tokens) > 3 else tokens[2])
            continue

        if block is None:
            continue
        tokens = smart_split(stripped)

        if block == 'address_set':
            # address 0 10.0.130.0 mask 24 | address 1 address-set NAME | address 2 range A B
            if tokens[0] == 'address' and len(tokens) >= 3:
                addr = _parse_address_tokens(tokens[2:])
                if addr:
                    address_sets[name]['entries'].append(addr)

        elif block == 'service_set':
            # service 0 protocol tcp source-port 0 to 65535 destination-port 8443
            if tokens[0] == 'service' and 'protocol' in tokens:
                idx = tokens.index('protocol')
                if idx + 1 < len(tokens):
                    service_sets[name].append(_parse_protocol(tokens[idx + 1:]))

        elif block == 'nat_group':
            if tokens[0] == 'mode' and len(tokens) > 1:
                nat_groups[name]['mode'] = tokens[1]
            elif tokens[0] == 'section' and len(tokens) >= 4:
                nat_groups[name]['sections'].append((tokens[2], tokens[3]))

        elif block in ('security_policy', 'nat_policy'):
            target = security_rules if block == 'security_policy' else nat_rules
            if indent == 1:
                rule = None
                if tokens[:2] == ['rule', 'name'] and len(tokens) > 2:
                    rule = _new_rule(' '.join(tokens[2:]), nat=(block == 'nat_policy'))
                    rule['raw'].append(stripped)
                    target.append(rule)
            elif rule is not None:
                rule['raw'].append('  ' + stripped)
                _parse_rule_line(rule, tokens)
                zones.update(rule['source_zones'] + rule['destination_zones'])

    return {
        'address_sets': address_sets,
        'service_sets': service_sets,
        'nat_groups': nat_groups,
        'security_rules': security_rules,
        'nat_rules': nat_rules,
        'zones': sorted(zones),
    }


# ---------- Раскрытие объектов ----------

def resolve_address_set(set_name, address_sets, visited=None):
    """Рекурсивно раскрывает address-set до списка сетей."""
    visited = visited if visited is not None else set()
    if set_name in visited or set_name not in address_sets:
        return []
    visited.add(set_name)
    result = []
    for kind, value in address_sets[set_name]['entries']:
        if kind == 'net':
            result.extend(value)
        else:
            result.extend(resolve_address_set(value, address_sets, visited))
    return result


def _resolve_addr(addr, address_sets):
    kind, value = addr
    return value if kind == 'net' else resolve_address_set(value, address_sets)


def resolve_service(service, service_sets):
    """('name', X) | ('inline', (proto, lo, hi)) -> [(proto, lo, hi)]."""
    kind, value = service
    if kind == 'inline':
        return [value]
    if value in service_sets:
        return service_sets[value]
    if value in BUILTIN_SERVICES:
        return BUILTIN_SERVICES[value]
    return [(f'? {value}', None, None)]


# ---------- Поиск ----------

def parse_target(target_str):
    """'10.1.1.1' или '10.1.1.0/24' -> IPv4Network. Бросает ValueError при неверном вводе."""
    return ipaddress.IPv4Network(target_str.strip(), strict=False)


def _side_matches(addresses, target, address_sets, include_any):
    if not addresses:
        return include_any
    return any(net.overlaps(target)
               for addr in addresses
               for net in _resolve_addr(addr, address_sets))


def _zone_matches(rule, zone):
    def ok(zones):
        return not zones or zone in zones or 'any' in zones
    # Правило подходит, если зона совпадает хотя бы с одной стороны
    return ok(rule['source_zones']) or ok(rule['destination_zones'])


def find_matching_rules(rules, target, search_in, address_sets, zone_filter=None, include_any=False):
    """
    Правила, в адресах которых встречается target (пересечение сетей).
    include_any — считать пустой source/destination (any) совпадением.
    """
    matching = []
    for rule in rules:
        if rule['disabled']:
            continue
        if zone_filter and not _zone_matches(rule, zone_filter):
            continue
        src = search_in in ('src', 'both') and _side_matches(
            rule['source_addresses'], target, address_sets, include_any)
        dst = search_in in ('dst', 'both') and _side_matches(
            rule['destination_addresses'], target, address_sets, include_any)
        if src or dst:
            matching.append(rule)
    return matching


# ---------- Форматирование ----------

def format_port_range(lo, hi):
    if lo is None:
        return ''
    if lo == 0 and hi == 65535:
        return 'any'
    return str(lo) if lo == hi else f"{lo}-{hi}"


def format_nat_target(nat_target, nat_groups):
    if nat_target == 'easy-ip':
        return 'IP исходящего интерфейса'
    group = nat_groups.get(nat_target)
    if group and group['sections']:
        return ', '.join(start if start == end else f"{start}-{end}" for start, end in group['sections'])
    return nat_target or ''


def _format_addresses(addresses, address_sets):
    """(names, ips) для ячеек таблицы."""
    if not addresses:
        return 'any', 'any'
    names, ips = [], []
    for addr in addresses:
        nets = [str(n) for n in _resolve_addr(addr, address_sets)]
        names.append(addr[1] if addr[0] == 'set' else ', '.join(nets))
        ips.extend(n for n in nets if n not in ips)
    return '; '.join(names), '; '.join(ips)


def _services_by_proto(rule, service_sets):
    """{proto: [порты]} с сохранением порядка. Без service — any."""
    if not rule['services']:
        return {'any': ['any']}
    result = {}
    for svc in rule['services']:
        for proto, lo, hi in resolve_service(svc, service_sets):
            ports = result.setdefault(proto, [])
            port = format_port_range(lo, hi)
            if port and port not in ports:
                ports.append(port)
    return result


def _rows_for_rule(rule, kind, parsed):
    src_name, src_ip = _format_addresses(rule['source_addresses'], parsed['address_sets'])
    dst_name, dst_ip = _format_addresses(rule['destination_addresses'], parsed['address_sets'])
    base = {
        'kind': kind,
        'sec_name': rule['name'] if kind == 'security-policy' else '',
        'nat_name': rule['name'] if kind == 'nat-policy' else '',
        'src_name': src_name, 'src_ip': src_ip,
        'dst_name': dst_name, 'dst_ip': dst_ip,
        'src_nat': '', 'dst_nat': '',
        'action': rule['action'] or '',
        'src_zone': ', '.join(rule['source_zones']) or 'any',
        'dst_zone': ', '.join(rule['destination_zones']) or 'any',
        'rule': rule,
    }
    if kind == 'nat-policy':
        target = format_nat_target(rule.get('nat_target'), parsed['nat_groups'])
        if rule.get('nat_type') == 'source-nat':
            base['src_nat'] = target
        elif rule.get('nat_type') == 'destination-nat':
            base['dst_nat'] = target

    rows = []
    for proto, ports in _services_by_proto(rule, parsed['service_sets']).items():
        rows.append({**base, 'proto': proto, 'port': ', '.join(ports)})
    return rows


def search(parsed, target_str, zone_filter=None, search_in='both', include_any=False):
    """Ищет правила по IP/подсети. Возвращает список строк-словарей (ключи — COLUMNS + 'rule')."""
    target = parse_target(target_str)
    rows = []
    for kind, rules in (('security-policy', parsed['security_rules']), ('nat-policy', parsed['nat_rules'])):
        for rule in find_matching_rules(rules, target, search_in, parsed['address_sets'], zone_filter, include_any):
            rows.extend(_rows_for_rule(rule, kind, parsed))
    return rows


def row_values(row):
    """Строка-словарь -> кортеж значений в порядке COLUMNS."""
    return tuple(row[key] for key, _, _ in COLUMNS)


def generate_excel_data(config_text, target_ip_str, zone_filter=None, search_in='both', include_any=False):
    """Совместимость со старым API: список кортежей."""
    parsed = parse_config(config_text)
    return [row_values(r) for r in search(parsed, target_ip_str, zone_filter, search_in, include_any)]
