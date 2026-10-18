"""AI 協作辦公室：owner_proxy。"""
import hmac
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


class OwnerProxy:
    def __init__(self, config):
        self.origin = config['origin'].rstrip('/')
        u = urlsplit(self.origin)
        if u.scheme != 'https' or not u.hostname or u.path or u.query or u.fragment or u.username:
            raise ValueError('SSO 入口必須是完整 HTTPS origin')
        self.app = config['app']
        self.owner_uid = config['owner_uid']
        additional_uids = config.get('additional_uids', ())
        if not isinstance(additional_uids, (list, tuple)):
            raise ValueError('SSO 身分設定不完整')
        self.additional_uids = tuple(additional_uids)
        if (not self.app or not isinstance(self.owner_uid, str)
                or not re.fullmatch(r'[0-9a-f]{64}', self.owner_uid)
                or any(not isinstance(uid, str) or not re.fullmatch(r'[0-9a-f]{64}', uid)
                       for uid in self.additional_uids)
                or len(set((self.owner_uid, *self.additional_uids))) != 1 + len(self.additional_uids)):
            raise ValueError('SSO 身分設定不完整')
        self.peers = frozenset(str(ipaddress.ip_address(x)) for x in config['proxy_peers'])
        self.local_peers = frozenset(str(ipaddress.ip_address(x)) for x in config['local_peers'])
        if not self.peers or self.peers & self.local_peers:
            raise ValueError('代理與本機來源必須明確分開')

    @classmethod
    def from_file(cls, path):
        p = Path(path)
        if p.stat().st_mode & 0o077:
            raise ValueError('SSO 設定權限必須為 600')
        return cls(json.loads(p.read_text()))

    def trusted(self, handler):
        uid = handler.headers.get('X-Authentik-Uid', '')
        matched = hmac.compare_digest(uid, self.owner_uid)
        for allowed_uid in self.additional_uids:
            matched |= hmac.compare_digest(uid, allowed_uid)
        return (handler.client_address[0] in self.peers
                and matched
                and handler.headers.get('X-Authentik-Meta-App') == self.app)

    def local(self, handler):
        return handler.client_address[0] in self.local_peers

    def same_origin(self, handler):
        return handler.headers.get('Origin') == self.origin

    def reject(self, handler):
        safe = handler.command in ('GET', 'HEAD')
        body = '請由 Authentik 登入。'.encode()
        handler.send_response(302 if safe else 401)
        if safe:
            handler.send_header('Location', self.origin + '/')
        handler.send_header('Content-Type', 'text/plain; charset=utf-8')
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        if handler.command != 'HEAD':
            handler.wfile.write(body)
        return False
