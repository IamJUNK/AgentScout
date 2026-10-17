from urllib.parse import urlsplit, urlunsplit

def canonical_url(url):
    p = urlsplit(url.strip())
    if p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password:
        raise ValueError('Invalid public URL')
    host = p.hostname.encode('idna').decode().lower()
    if ':' in host:
        host = '[' + host + ']'
    port = p.port
    if port and (p.scheme, port) not in {('http',80),('https',443)}:
        host += ':' + str(port)
    # Preserve query order/encoding and semantic parameters; only remove known tracking.
    query = '&'.join(part for part in p.query.split('&') if part and not part.split('=')[0].lower().startswith('utm_'))
    return urlunsplit((p.scheme.lower(), host, p.path or '/', query, ''))
