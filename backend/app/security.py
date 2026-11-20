"""Single-operator LAN sessions. Default bypass is strictly loopback-only."""
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from collections import OrderedDict

COOKIE='pbl4_session'


def password_hash(password, salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()


class Security:
    def __init__(self):
        self.lan=os.getenv('APP_MODE','local')=='lan'
        if os.getenv('APP_MODE','local') not in ('local','lan'):raise ValueError('APP_MODE must be local or lan')
        self.origins=[s.strip() for s in os.getenv('ALLOWED_ORIGINS','http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173').split(',')]
        self.hosts=[s.strip().lower() for s in os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(',')]
        self.hash=os.getenv('OPERATOR_PASSWORD_HASH','')
        if self.lan:
            if not self.hash or not os.getenv('ALLOWED_HOSTS') or not os.getenv('ALLOWED_ORIGINS'):raise ValueError('LAN requires OPERATOR_PASSWORD_HASH, ALLOWED_HOSTS and ALLOWED_ORIGINS')
            salt,digest=self.hash.split(':')
            if len(bytes.fromhex(salt))<16 or len(bytes.fromhex(digest))!=64:raise ValueError('Invalid scrypt hash format')
            if len(digest)!=128 or '*' in ','.join(self.hosts+self.origins) or any(not s.startswith('https://') for s in self.origins):raise ValueError('LAN requires explicit HTTPS origins, hosts and a scrypt password hash')
        self.sessions={};self.buckets=OrderedDict();self.connections=0

    def local(self,scope):
        if self.lan:return False
        host=dict(scope.get('headers',[])).get(b'host',b'').decode().split(':')[0].lower()
        peer=(scope.get('client') or ('',0))[0]
        try:loop=ipaddress.ip_address(peer).is_loopback
        except ValueError:loop=peer=='testclient'
        return loop and host in ('localhost','127.0.0.1','testserver')

    def session(self,cookies):
        token=cookies.get(COOKIE,'');value=self.sessions.get(token)
        if value and value['expires']>time.monotonic():return value
        self.sessions.pop(token,None)
        return None

    def operator(self,connection):return self.local(connection.scope) or self.session(connection.cookies) is not None

    def rate(self,key,limit,period=60):
        now=time.monotonic();start,count=self.buckets.get(key,(now,0))
        if now-start>=period:start,count=now,0
        self.buckets[key]=(start,count+1);self.buckets.move_to_end(key)
        while len(self.buckets)>1024:self.buckets.popitem(last=False)
        return count<limit

    def login(self,password):
        try:valid=hmac.compare_digest(password_hash(password,self.hash.split(':')[0]),self.hash)
        except (ValueError,IndexError):valid=False
        if not valid:return None
        now=time.monotonic()
        self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
        if len(self.sessions)>=128:self.sessions.pop(next(iter(self.sessions)))
        token=secrets.token_urlsafe(32);self.sessions[token]={'csrf':secrets.token_urlsafe(24),'expires':now+8*3600}
        return token


class SecurityMiddleware:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type'] not in ('http','websocket'):return await self.app(scope,receive,send)
        if scope['type']=='http':
            original_send=send
            async def secured_send(message):
                if message['type']=='http.response.start':
                    message={**message,'headers':[*message.get('headers',[]),(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'DENY')]}
                await original_send(message)
            send=secured_send
        security=scope['app'].state.security
        headers=dict(scope.get('headers',[]));host=headers.get(b'host',b'').decode().split(':')[0].lower()
        origin=headers.get(b'origin',b'').decode()
        async def reject(code,message):
            if scope['type']=='websocket':await send({'type':'websocket.close','code':1008})
            else:
                body=json.dumps({'detail':message}).encode()
                await send({'type':'http.response.start','status':code,'headers':[(b'content-type',b'application/json')]})
                await send({'type':'http.response.body','body':body})
        if security.lan and scope.get('scheme') not in ('https','wss'):return await reject(403,'LAN mode requires HTTPS/WSS through a trusted TLS proxy')
        if host not in security.hosts:return await reject(400,'Host is not allowed')
        if not security.lan and not security.local(scope):return await reject(403,'Non-loopback access requires explicit LAN configuration')
        if origin and origin not in security.origins:return await reject(403,'Origin is not allowed')
        if scope['type']=='websocket':
            if security.lan and not origin:return await reject(403,'WebSocket Origin required')
            if security.connections>=64:return await reject(429,'Connection capacity reached')
            security.connections+=1
            try:return await self.app(scope,receive,send)
            finally:security.connections-=1
        from starlette.requests import Request
        request=Request(scope)
        if scope['method'] not in ('GET','HEAD','OPTIONS'):
            if not security.rate(('http',scope.get('client',('',))[0]),120):return await reject(429,'Mutation rate exceeded')
            if scope['path']!='/api/auth/login':
                if not security.operator(request):return await reject(401,'Operator authentication required')
                if not security.local(scope):
                    session=security.session(request.cookies)
                    if origin not in security.origins or not hmac.compare_digest(headers.get(b'x-csrf-token',b'').decode(),session['csrf']):return await reject(403,'CSRF token and allowed Origin required')
            # Buffer at most 32 KiB, including chunked requests, before validation.
            body=b''
            while True:
                message=await receive()
                if message['type']=='http.disconnect':return
                body+=message.get('body',b'')
                if len(body)>32768:return await reject(413,'Request body exceeds 32 KiB')
                if not message.get('more_body'):break
            delivered=False
            async def replay():
                nonlocal delivered
                if not delivered:delivered=True;return {'type':'http.request','body':body,'more_body':False}
                return await receive()
            return await self.app(scope,replay,send)
        await self.app(scope,receive,send)


if __name__=='__main__':
    import getpass
    password=getpass.getpass('New operator password (at least 12 characters): ')
    if len(password)<12:raise SystemExit('Use at least 12 characters')
    if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords differ')
    print('OPERATOR_PASSWORD_HASH='+password_hash(password))
