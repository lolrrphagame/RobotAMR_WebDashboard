"""Local production assets on the existing FastAPI instance and lifespan."""
import os
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse

PAGES = ('overview', 'manual-control', 'navigation', 'missions', 'sensors', 'diagnostics', 'settings')
ASSET_TYPES = {'.js', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.woff', '.woff2', '.ttf'}


def create_app():
    if os.getenv('APP_MODE', 'local') != 'local':
        raise ValueError('Phase 5B.1 production serving is loopback-only; LAN requires Phase 5B.2')
    root = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
    # This factory has no arbitrary filesystem/static root configuration.
    if root.is_symlink() or (root/'assets').is_symlink() or (root/'index.html').is_symlink():
        raise ValueError('Production build root/index/assets must not be symlinks')
    if not (root / 'index.html').is_file() or not (root / 'assets').is_dir():
        raise ValueError('Production frontend missing. Run npm --prefix frontend run build, or ./start-dashboard.sh')
    from .main import app
    if getattr(app.state, 'production_routes_added', False):
        return app
    app.router.routes[:] = [r for r in app.router.routes if r.path not in
                            ('/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect')]

    async def index():
        return FileResponse(root / 'index.html', media_type='text/html')

    async def asset(path: str):
        candidate = (root / 'assets' / path).resolve()
        asset_root = (root / 'assets').resolve()
        if not candidate.is_relative_to(asset_root) or candidate.suffix not in ASSET_TYPES or not candidate.is_file():
            raise HTTPException(404, 'Production asset not found')
        return FileResponse(candidate)

    app.add_api_route('/', index, methods=['GET', 'HEAD'], include_in_schema=False)
    for page in PAGES:
        app.add_api_route('/' + page, index, methods=['GET', 'HEAD'], include_in_schema=False)
    app.add_api_route('/assets/{path:path}', asset, methods=['GET', 'HEAD'], include_in_schema=False)
    app.state.production_routes_added = True
    return app
