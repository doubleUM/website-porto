import os
import re
import time
import threading
from collections import defaultdict, deque
from functools import wraps
from datetime import datetime, timezone, timedelta
import uuid

from flask import Flask, Response, abort, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv

import ml_engine
from deep_translator import MyMemoryTranslator
import textwrap
from langdetect import detect

load_dotenv()

app = Flask(__name__)
# Render terminates TLS at its proxy; trust X-Forwarded-* so url_for(_external=True)
# emits https:// and the real host (needed for correct og:url / og:image).
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
CORS(app)
bcrypt = Bcrypt(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Downloadable CV. Rendered only when this file exists in static/.
RESUME_FILENAME = 'Wilson-Manuel-CV.pdf'

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

client = MongoClient(os.getenv('MONGODB_URI'))

# Project Databases
db_spareparts = client['car-spareparts']
db_kanban = client['kanban']
db_chat = client['buzz-chat']
db_stats = client['site-stats']
db_ai = client['text-forge']

# Collections — Spareparts
categories_col = db_spareparts.categories
products_col = db_spareparts.products
cart_items_col = db_spareparts.cart_items
orders_col = db_spareparts.orders
users_col = db_spareparts.users
spareparts_counters = db_spareparts.counters

# Collections — Kanban
kanban_col = db_kanban.kanban_tasks
kanban_counters = db_kanban.counters

# Collections — Chat
chat_messages_col = db_chat.chat_messages
chat_counters = db_chat.counters

# Collections — Stats
stats_col = db_stats.site_stats

# Active chat users tracker
chat_users = {}

# Active sessions tracker (for Online count)
online_users = {}

# Base directory & cached "Last updated" timestamp (computed once at startup)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _compute_last_update_str():
    ignored_dirs = {'venv', '.venv', '.git', '__pycache__', 'node_modules'}
    max_mtime = 0
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for f in files:
            if f.endswith('.pyc') or f == '.env':
                continue
            filepath = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime > max_mtime:
                    max_mtime = mtime
            except OSError:
                pass
    dt = datetime.fromtimestamp(max_mtime) if max_mtime > 0 else datetime.now()
    return dt.strftime('%B %Y')


LAST_UPDATE_STR = _compute_last_update_str()

# ============================================================================
# RATE LIMITING (In-memory sliding window per client IP)
# ============================================================================

_rate_buckets = defaultdict(deque)
_rate_lock = threading.Lock()


def check_rate_limit(bucket_name, max_requests, window_seconds):
    """Return (allowed: bool, retry_after_seconds: int) for the current client IP."""
    client_ip = request.remote_addr or 'unknown'
    key = f"{bucket_name}:{client_ip}"
    now = time.monotonic()
    cutoff = now - window_seconds

    with _rate_lock:
        dq = _rate_buckets[key]
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= max_requests:
            retry_after = max(1, int(dq[0] + window_seconds - now) + 1)
            return False, retry_after
        dq.append(now)
        return True, 0


def rate_limit_ai(bucket_name, per_minute=10, per_hour=60):
    """Decorator enforcing per-minute and per-hour rate limits on AI endpoints."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            ok_min, retry_min = check_rate_limit(f"{bucket_name}:m", per_minute, 60)
            if not ok_min:
                resp = jsonify({
                    'success': False,
                    'message': f'Rate limit reached ({per_minute}/min). Please wait {retry_min}s before trying again.'
                })
                resp.status_code = 429
                resp.headers['Retry-After'] = str(retry_min)
                return resp

            ok_hr, retry_hr = check_rate_limit(f"{bucket_name}:h", per_hour, 3600)
            if not ok_hr:
                resp = jsonify({
                    'success': False,
                    'message': 'Hourly AI request limit reached. Please try again later.'
                })
                resp.status_code = 429
                resp.headers['Retry-After'] = str(retry_hr)
                return resp

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# GARAGE FITMENT PROFILES (Shared across Store UI, Catalog Filter & AI Mechanic)
# ============================================================================

GARAGE_VEHICLES = [
    {
        'id': 'honda-civic',
        'name': 'Honda Civic',
        'trim': 'Type R / Si · FL5',
        'year': '2022–2026',
        'exact_terms': ['honda civic'],
        'universal_terms': ['universal', 'most sedans', 'most 4-cylinder', 'most fuel-injected', 'japanese'],
    },
    {
        'id': 'toyota-camry',
        'name': 'Toyota Camry',
        'trim': 'TRD / XSE · XV70',
        'year': '2020–2026',
        'exact_terms': ['toyota camry'],
        'universal_terms': ['universal', 'most sedans', 'most 4-cylinder', 'most fuel-injected', 'japanese'],
    },
    {
        'id': 'bmw-3-series',
        'name': 'BMW 3-Series',
        'trim': '330i / M340i · G20',
        'year': '2019–2026',
        'exact_terms': ['bmw 3-series'],
        'universal_terms': ['universal', 'most sedans', 'most 4-cylinder', 'most fuel-injected', 'european'],
    },
    {
        'id': 'ford-mustang',
        'name': 'Ford Mustang',
        'trim': 'GT 5.0 V8 · S650',
        'year': '2021–2026',
        'exact_terms': ['ford mustang'],
        'universal_terms': ['universal', 'most fuel-injected'],
    },
    {
        'id': 'toyota-tacoma',
        'name': 'Toyota Tacoma',
        'trim': 'TRD Pro 4x4 · N400',
        'year': '2020–2026',
        'exact_terms': ['toyota tacoma', '4runner'],
        'universal_terms': ['universal', 'trucks', 'most fuel-injected', 'japanese'],
    },
    {
        'id': 'jeep-wrangler',
        'name': 'Jeep Wrangler',
        'trim': 'Rubicon · JL',
        'year': '2018–2026',
        'exact_terms': ['jeep wrangler', 'cherokee'],
        'universal_terms': ['universal', 'trucks', 'most fuel-injected'],
    },
    {
        'id': 'mercedes-c-class',
        'name': 'Mercedes C-Class',
        'trim': 'C300 AMG Line · W206',
        'year': '2021–2026',
        'exact_terms': ['mercedes c-class'],
        'universal_terms': ['universal', 'most sedans', 'most 4-cylinder', 'most fuel-injected', 'european'],
    },
    {
        'id': 'honda-accord',
        'name': 'Honda Accord',
        'trim': 'Sport 2.0T · CY2',
        'year': '2020–2026',
        'exact_terms': ['honda accord'],
        'universal_terms': ['universal', 'most sedans', 'most 4-cylinder', 'most fuel-injected', 'japanese'],
    },
    {
        'id': 'nissan-altima',
        'name': 'Nissan Altima',
        'trim': 'SR VC-Turbo · L34',
        'year': '2019–2026',
        'exact_terms': ['nissan altima'],
        'universal_terms': ['universal', 'most sedans', 'most 4-cylinder', 'most fuel-injected', 'japanese'],
    },
    {
        'id': 'chevy-camaro',
        'name': 'Chevrolet Camaro',
        'trim': 'SS 1LE · Alpha',
        'year': '2019–2024',
        'exact_terms': ['chevrolet camaro'],
        'universal_terms': ['universal', 'most fuel-injected'],
    },
]

GARAGE_VEHICLE_MAP = {v['id']: v for v in GARAGE_VEHICLES}


# ============================================================================
# CONTEXT PROCESSOR — injects current_user & cart_count only on store pages
# ============================================================================

@app.context_processor
def inject_global_data():
    if not request.path.startswith('/car-spareparts'):
        return {'current_user': None, 'cart_count': 0, 'garage_vehicles': []}

    user_id = session.get('user_id')

    # Get current user
    user = None
    if user_id:
        user = users_col.find_one({'_id': user_id}, {'password': 0})

    # Calculate cart count using the shared filter logic
    cart_filter = get_cart_filter()
    pipeline = [{'$match': cart_filter}, {'$group': {'_id': None, 'total': {'$sum': '$quantity'}}}]
    cart_result = list(cart_items_col.aggregate(pipeline))
    cart_count = cart_result[0]['total'] if cart_result else 0

    return {
        'current_user': user,
        'cart_count': cart_count,
        'garage_vehicles': GARAGE_VEHICLES,
    }

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def utcnow():
    """Timezone-aware UTC timestamp (utcnow() is deprecated)."""
    return datetime.now(timezone.utc)


def get_next_id(collection_name, counters_col):
    """Auto-increment integer ID using a specific counters collection."""
    counter = counters_col.find_one_and_update(
        {'_id': collection_name},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=True
    )
    return counter['seq']


def get_cart_filter():
    """Return a MongoDB filter scoped to the current user or guest session."""
    if 'user_id' in session:
        return {'user_id': session['user_id']}
    if 'cart_id' not in session:
        session['cart_id'] = str(uuid.uuid4())
    return {'cart_id': session['cart_id']}


def merge_carts(target_user_id):
    """Move guest cart items into the user's cart on login/signup."""
    if 'cart_id' not in session:
        return
    guest_filter = {'cart_id': session['cart_id']}
    for item in list(cart_items_col.find(guest_filter)):
        existing = cart_items_col.find_one({'user_id': target_user_id, 'product_id': item['product_id']})
        if existing:
            cart_items_col.update_one({'_id': existing['_id']}, {'$inc': {'quantity': item['quantity']}})
            cart_items_col.delete_one({'_id': item['_id']})
        else:
            cart_items_col.update_one(
                {'_id': item['_id']},
                {'$set': {'user_id': target_user_id}, '$unset': {'cart_id': ''}}
            )
    session.pop('cart_id', None)


def doc_to_dict(doc):
    """Convert a MongoDB document to a dict with 'id' field for template compatibility."""
    if doc is None:
        return None
    doc['id'] = doc.pop('_id', None)
    return doc


def docs_to_list(cursor):
    """Convert a MongoDB cursor to a list of dicts with 'id' fields."""
    return [doc_to_dict(doc) for doc in cursor]


def get_demo_session_id():
    """Return a persistent per-visitor session ID for sandboxing public demo edits."""
    if 'demo_sid' not in session:
        session['demo_sid'] = session.get('tracker_id') or str(uuid.uuid4())
    return session['demo_sid']


def get_store_visibility_filter():
    """Show official seed products plus custom products added by the current visitor."""
    sid = get_demo_session_id()
    return {
        '$or': [
            {'is_seed': True},
            {'session_id': {'$exists': False}},
            {'session_id': sid},
        ]
    }


def is_protected_seed_product(product_doc):
    """True when a product belongs to the protected default demo catalog."""
    if not product_doc:
        return False
    return bool(product_doc.get('is_seed') or not product_doc.get('session_id'))


DEFAULT_KANBAN_SEED = [
    {
        'name': 'Benchmark Gemini vs Naive Bayes ticket routing',
        'description': 'Compare latency and confidence calibration across 200 bilingual support tickets.',
        'status': 'done',
        'priority': 'high',
        'color': '#15803d',
        'due_date': None,
        'subtasks': [
            {'text': 'Curate English + Bahasa Indonesia test split', 'done': True},
            {'text': 'Log latency & accuracy metrics', 'done': True},
        ],
    },
    {
        'name': 'Convert product catalog assets to WebP',
        'description': 'Resize 2048x2048 PNG assets and add lazy-loading across store & portfolio views.',
        'status': 'in-progress',
        'priority': 'high',
        'color': '#1d4ed8',
        'due_date': None,
        'subtasks': [
            {'text': 'Generate optimized WebP assets', 'done': True},
            {'text': 'Verify Lighthouse LCP score', 'done': False},
        ],
    },
    {
        'name': 'Add rate limiting & session sandboxing to public demos',
        'description': 'Isolate visitor-created demo records per session so public catalog & board stay clean.',
        'status': 'todo',
        'priority': 'medium',
        'color': '#b45309',
        'due_date': None,
        'subtasks': [],
    },
]


def ensure_session_kanban_tasks(sid):
    """Seed an isolated Kanban workspace per visitor session so public edits never collide."""
    if session.get('kb_seeded') and kanban_col.count_documents({'session_id': sid}, limit=1) > 0:
        return

    # Opportunistically clean up abandoned visitor Kanban tasks older than 48h
    cutoff_iso = (utcnow() - timedelta(hours=48)).isoformat()
    kanban_col.delete_many({'session_id': {'$exists': True}, 'created_at': {'$lt': cutoff_iso}})

    if kanban_col.count_documents({'session_id': sid}, limit=1) > 0:
        session['kb_seeded'] = True
        return

    # Clone existing global template tasks (those without session_id), or fall back to DEFAULT_KANBAN_SEED
    templates = list(kanban_col.find({'session_id': {'$exists': False}}).sort('created_at', 1).limit(10))
    source_items = templates if templates else DEFAULT_KANBAN_SEED
    now_iso = utcnow().isoformat()

    new_docs = []
    for item in source_items:
        new_docs.append({
            '_id': get_next_id('kanban_tasks', kanban_counters),
            'session_id': sid,
            'name': item.get('name', 'Sample Task'),
            'description': item.get('description', ''),
            'status': item.get('status', 'todo'),
            'priority': item.get('priority', 'medium'),
            'color': item.get('color', '#b45309'),
            'due_date': item.get('due_date'),
            'subtasks': item.get('subtasks', []),
            'created_at': now_iso,
        })
    if new_docs:
        kanban_col.insert_many(new_docs)
    session['kb_seeded'] = True


_BOT_UA_RE = re.compile(r'bot|spider|crawl|slurp|headless|lighthouse|facebookexternalhit|whatsapp|discordbot', re.I)
_IGNORED_TRACK_PREFIXES = ('/static', '/api/', '/car-spareparts/api/', '/kanban/api/', '/ai-tool/api/')
_IGNORED_TRACK_PATHS = {'/robots.txt', '/sitemap.xml', '/favicon.ico'}


@app.before_request
def track_analytics():
    # Only track real HTML page views (exclude static assets, JSON API calls, SEO files, and bots)
    if request.method != 'GET':
        return
    path = request.path
    if path in _IGNORED_TRACK_PATHS or path.startswith(_IGNORED_TRACK_PREFIXES):
        return
    ua = request.headers.get('User-Agent', '')
    if _BOT_UA_RE.search(ua):
        return

    inc_fields = {'total_visits': 1}
    if 'tracker_id' not in session or 'unique_counted' not in session:
        if 'tracker_id' not in session:
            session['tracker_id'] = str(uuid.uuid4())
        inc_fields['unique_visitors'] = 1
        session['unique_counted'] = True

    stats_col.update_one({'_id': 'global_stats'}, {'$inc': inc_fields}, upsert=True)

    tracker_id = session['tracker_id']
    now = utcnow()
    online_users[tracker_id] = now

    # Cleanup old users (older than 5 mins)
    expired = [tid for tid, last_seen in online_users.items() if (now - last_seen).total_seconds() > 300]
    for tid in expired:
        online_users.pop(tid, None)

# ============================================================================
# INITIALIZE DATABASE WITH SAMPLE DATA
# ============================================================================

def init_db():
    # Check if data already exists
    if categories_col.count_documents({}) == 0:
        # Create categories
        categories_data = [
            {'_id': get_next_id('categories', spareparts_counters), 'name': 'Engine Parts', 'description': 'High-performance engine components', 'icon': '🔧'},
            {'_id': get_next_id('categories', spareparts_counters), 'name': 'Brake Systems', 'description': 'Premium brake pads and rotors', 'icon': '🛑'},
            {'_id': get_next_id('categories', spareparts_counters), 'name': 'Electrical', 'description': 'Batteries, alternators, and wiring', 'icon': '⚡'},
            {'_id': get_next_id('categories', spareparts_counters), 'name': 'Suspension', 'description': 'Shocks, struts, and control arms', 'icon': '🔩'},
            {'_id': get_next_id('categories', spareparts_counters), 'name': 'Filters', 'description': 'Oil, air, and fuel filters', 'icon': '🔍'},
            {'_id': get_next_id('categories', spareparts_counters), 'name': 'Lighting', 'description': 'Headlights, tail lights, and bulbs', 'icon': '💡'},
        ]
        categories_col.insert_many(categories_data)

        # Create sample products
        products_data = [
            # Engine Parts
            {'_id': get_next_id('products', spareparts_counters), 'name': 'Premium Oil Filter', 'description': 'High-efficiency oil filter for optimal engine protection',
             'price': 15.99, 'stock': 150, 'brand': 'AutoPro', 'part_number': 'OF-2024',
             'category_id': 1, 'compatible_cars': 'Toyota Camry, Honda Accord, Ford Focus',
             'specifications': 'Thread size: 3/4-16, Height: 3.5 inches', 'featured': True, 'is_seed': True,
             'image_url': '/static/images/products/oil-filter.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Spark Plug Set (4pc)', 'description': 'Iridium spark plugs for improved performance',
             'price': 45.99, 'stock': 80, 'brand': 'NGK', 'part_number': 'SP-IR-401',
             'category_id': 1, 'compatible_cars': 'Most 4-cylinder engines',
             'specifications': 'Gap: 0.044", Thread: 14mm', 'featured': True, 'is_seed': True,
             'image_url': '/static/images/products/spark-plugs.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Air Filter', 'description': 'High-flow air filter for better engine breathing',
             'price': 24.99, 'stock': 120, 'brand': 'K&N', 'part_number': 'AF-3320',
             'category_id': 5, 'compatible_cars': 'Universal fit for most sedans',
             'specifications': 'Washable and reusable', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/air-filter.webp', 'created_at': utcnow()},

            # Brake Systems
            {'_id': get_next_id('products', spareparts_counters), 'name': 'Ceramic Brake Pads', 'description': 'Low-dust ceramic brake pads for quiet stopping',
             'price': 89.99, 'stock': 60, 'brand': 'Brembo', 'part_number': 'BP-CER-500',
             'category_id': 2, 'compatible_cars': 'Honda Civic, Toyota Corolla',
             'specifications': 'Front axle, includes shims', 'featured': True, 'is_seed': True,
             'image_url': '/static/images/products/brake-pads.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Brake Rotors (Pair)', 'description': 'Slotted and drilled performance rotors',
             'price': 159.99, 'stock': 40, 'brand': 'PowerStop', 'part_number': 'BR-SP-250',
             'category_id': 2, 'compatible_cars': 'Ford Mustang, Chevrolet Camaro',
             'specifications': 'Front, 12.6" diameter', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/brake-rotors.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Brake Fluid DOT 4', 'description': 'Premium synthetic brake fluid',
             'price': 12.99, 'stock': 200, 'brand': 'Castrol', 'part_number': 'BF-DOT4-500',
             'category_id': 2, 'compatible_cars': 'Universal',
             'specifications': '500ml bottle, high boiling point', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/brake-fluid.webp', 'created_at': utcnow()},

            # Electrical
            {'_id': get_next_id('products', spareparts_counters), 'name': 'Car Battery 12V', 'description': 'Maintenance-free AGM battery',
             'price': 189.99, 'stock': 35, 'brand': 'Optima', 'part_number': 'BAT-AGM-75',
             'category_id': 3, 'compatible_cars': 'Most sedans and trucks',
             'specifications': '750 CCA, 75 Ah, 3-year warranty', 'featured': True, 'is_seed': True,
             'image_url': '/static/images/products/car-battery.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Alternator', 'description': 'High-output alternator for reliable charging',
             'price': 249.99, 'stock': 25, 'brand': 'Bosch', 'part_number': 'ALT-150A',
             'category_id': 3, 'compatible_cars': 'Toyota Tacoma, 4Runner',
             'specifications': '150 Amp output', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/alternator.webp', 'created_at': utcnow()},

            # Suspension
            {'_id': get_next_id('products', spareparts_counters), 'name': 'Shock Absorber Set', 'description': 'Gas-charged shock absorbers for smooth ride',
             'price': 199.99, 'stock': 30, 'brand': 'Monroe', 'part_number': 'SH-GAS-400',
             'category_id': 4, 'compatible_cars': 'Nissan Altima, Mazda 6',
             'specifications': 'Rear pair, gas-charged', 'featured': True, 'is_seed': True,
             'image_url': '/static/images/products/shock-absorbers.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Coil Spring Set', 'description': 'Heavy-duty coil springs',
             'price': 139.99, 'stock': 45, 'brand': 'Eibach', 'part_number': 'CS-HD-300',
             'category_id': 4, 'compatible_cars': 'Jeep Wrangler, Cherokee',
             'specifications': 'Front pair, +2" lift', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/coil-springs.webp', 'created_at': utcnow()},

            # Filters
            {'_id': get_next_id('products', spareparts_counters), 'name': 'Fuel Filter', 'description': 'High-pressure fuel filter',
             'price': 19.99, 'stock': 100, 'brand': 'Wix', 'part_number': 'FF-HP-200',
             'category_id': 5, 'compatible_cars': 'Most fuel-injected vehicles',
             'specifications': 'In-line mount, 10 micron', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/fuel-filter.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Cabin Air Filter', 'description': 'Activated carbon cabin filter',
             'price': 16.99, 'stock': 110, 'brand': 'Mann', 'part_number': 'CAF-AC-150',
             'category_id': 5, 'compatible_cars': 'BMW 3-Series, Mercedes C-Class',
             'specifications': 'HEPA filtration, odor elimination', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/cabin-filter.webp', 'created_at': utcnow()},

            # Lighting
            {'_id': get_next_id('products', spareparts_counters), 'name': 'LED Headlight Bulbs', 'description': 'Super bright LED conversion kit',
             'price': 79.99, 'stock': 70, 'brand': 'Osram', 'part_number': 'LED-H7-6K',
             'category_id': 6, 'compatible_cars': 'H7 socket (most European cars)',
             'specifications': '6000K white, 12000 lumens', 'featured': True, 'is_seed': True,
             'image_url': '/static/images/products/led-headlights.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Fog Light Assembly', 'description': 'Complete fog light kit',
             'price': 129.99, 'stock': 50, 'brand': 'Hella', 'part_number': 'FL-KIT-500',
             'category_id': 6, 'compatible_cars': 'Universal with custom brackets',
             'specifications': 'Includes wiring harness and switch', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/fog-light.webp', 'created_at': utcnow()},

            {'_id': get_next_id('products', spareparts_counters), 'name': 'Halogen Light Bulb', 'description': 'Classic halogen headlight bulb with warm white light',
             'price': 29.99, 'stock': 90, 'brand': 'Philips', 'part_number': 'HL-H4-3200K',
             'category_id': 6, 'compatible_cars': 'H4 socket (most Japanese and Korean cars)',
             'specifications': '3200K warm white, 1500 lumens, 55W', 'featured': False, 'is_seed': True,
             'image_url': '/static/images/products/halogen-headlight.webp', 'created_at': utcnow()},
        ]
        products_col.insert_many(products_data)
        print("Database initialized with sample data!")
    else:
        # Upgrade any existing MongoDB product image_url references from .png -> .webp
        # and ensure default catalog items are marked as protected seed items.
        for doc in products_col.find({'image_url': {'$regex': r'\.png$'}}):
            new_url = re.sub(r'\.png$', '.webp', doc.get('image_url', ''))
            products_col.update_one({'_id': doc['_id']}, {'$set': {'image_url': new_url}})
        products_col.update_many(
            {'session_id': {'$exists': False}, 'is_seed': {'$exists': False}},
            {'$set': {'is_seed': True}}
        )

# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.route('/car-spareparts/login')
def login_page():
    if session.get('user_id'):
        return redirect(url_for('store_home'))
    return render_template('login.html')

@app.route('/car-spareparts/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not name or not email or not password:
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400
    if users_col.find_one({'email': email}):
        return jsonify({'success': False, 'message': 'An account with this email already exists.'}), 409

    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    user_id = get_next_id('users', spareparts_counters)
    users_col.insert_one({
        '_id': user_id,
        'name': name,
        'email': email,
        'password': hashed_pw,
        'created_at': utcnow()
    })

    session['user_id'] = user_id
    session['user_name'] = name
    merge_carts(user_id)
    return jsonify({'success': True, 'name': name})

@app.route('/car-spareparts/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = users_col.find_one({'email': email})
    if not user or not bcrypt.check_password_hash(user['password'], password):
        return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401

    session['user_id'] = user['_id']
    session['user_name'] = user['name']
    merge_carts(user['_id'])
    return jsonify({'success': True, 'name': user['name']})

@app.route('/car-spareparts/api/auth/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('cart_id', None)
    return redirect(url_for('store_home'))

# ============================================================================
# ROUTES - PAGE VIEWS
# ============================================================================

@app.route('/')
def portfolio_home():
    # Only surface the CV button once the file is actually there, so the link
    # can never 404. Drop the PDF at static/RESUME_FILENAME to switch it on.
    resume_path = os.path.join(BASE_DIR, 'static', RESUME_FILENAME)
    resume_url = url_for('static', filename=RESUME_FILENAME) if os.path.isfile(resume_path) else None

    return render_template('portfolio_home.html',
                           last_update=LAST_UPDATE_STR,
                           resume_url=resume_url)


@app.route('/car-spareparts')
def store_home():
    visibility = get_store_visibility_filter()
    all_visible = docs_to_list(products_col.find(visibility))
    categories = docs_to_list(categories_col.find())
    cat_lookup = {c['id']: c for c in categories}

    # Count SKUs per category and attach category info to products
    cat_counts = defaultdict(int)
    for p in all_visible:
        cat_counts[p.get('category_id')] += 1
        p['category'] = cat_lookup.get(p.get('category_id'), {'name': 'Component', 'icon': ''})

    for c in categories:
        c['product_count'] = cat_counts.get(c['id'], 0)

    featured_products = [p for p in all_visible if p.get('featured')][:6]
    catalog_compat = [
        {'id': p['id'], 'compatible_cars': p.get('compatible_cars', '')}
        for p in all_visible
    ]
    return render_template(
        'index.html',
        featured_products=featured_products,
        categories=categories,
        total_skus=len(all_visible),
        catalog_compat=catalog_compat,
    )

@app.route('/car-spareparts/products')
def products():
    category_id = request.args.get('category', type=int)
    search_query = request.args.get('search', '').strip()
    vehicle_id = request.args.get('vehicle', '').strip()
    sort_by = request.args.get('sort', 'name')

    visibility = get_store_visibility_filter()
    conditions = [visibility]

    if category_id:
        conditions.append({'category_id': category_id})

    if search_query:
        safe_pattern = re.escape(search_query[:100])
        conditions.append({
            '$or': [
                {'name': {'$regex': safe_pattern, '$options': 'i'}},
                {'description': {'$regex': safe_pattern, '$options': 'i'}},
                {'brand': {'$regex': safe_pattern, '$options': 'i'}},
                {'part_number': {'$regex': safe_pattern, '$options': 'i'}},
                {'compatible_cars': {'$regex': safe_pattern, '$options': 'i'}},
            ]
        })

    active_vehicle = None
    if vehicle_id:
        active_vehicle = GARAGE_VEHICLE_MAP.get(vehicle_id)
        if active_vehicle:
            terms = active_vehicle['exact_terms'] + active_vehicle['universal_terms']
            pattern = '|'.join(re.escape(t) for t in terms)
            conditions.append({'compatible_cars': {'$regex': pattern, '$options': 'i'}})
        else:
            safe_veh = re.escape(vehicle_id[:80])
            conditions.append({'compatible_cars': {'$regex': f"{safe_veh}|universal", '$options': 'i'}})

    query_filter = conditions[0] if len(conditions) == 1 else {'$and': conditions}

    # Sorting
    sort_spec = [('name', 1)]
    if sort_by == 'price_asc':
        sort_spec = [('price', 1)]
    elif sort_by == 'price_desc':
        sort_spec = [('price', -1)]
    elif sort_by == 'featured':
        sort_spec = [('featured', -1), ('name', 1)]

    products_list = docs_to_list(products_col.find(query_filter).sort(sort_spec))
    categories = docs_to_list(categories_col.find())
    cat_lookup = {c['id']: c for c in categories}

    # Compute overall category SKU counts within current session visibility
    cat_counts = defaultdict(int)
    for doc in products_col.find(visibility, {'category_id': 1}):
        cat_counts[doc.get('category_id')] += 1
    for c in categories:
        c['product_count'] = cat_counts.get(c['id'], 0)

    for p in products_list:
        p['category'] = cat_lookup.get(p.get('category_id'), {'name': 'Component', 'icon': ''})

    return render_template(
        'products.html',
        products=products_list,
        categories=categories,
        current_category=category_id,
        search_query=search_query,
        current_sort=sort_by,
        current_vehicle=vehicle_id,
        active_vehicle=active_vehicle,
        total_catalog_count=sum(cat_counts.values()),
    )

@app.route('/car-spareparts/product/<int:product_id>')
def product_detail(product_id):
    product_doc = products_col.find_one({'$and': [{'_id': product_id}, get_store_visibility_filter()]})
    if not product_doc:
        abort(404)
    product = doc_to_dict(product_doc)
    # Attach category for template compatibility (product.category.name)
    category_doc = categories_col.find_one({'_id': product['category_id']})
    product['category'] = doc_to_dict(category_doc) if category_doc else {'name': 'Unknown'}
    related_products = docs_to_list(
        products_col.find({
            '$and': [
                get_store_visibility_filter(),
                {'category_id': product['category_id'], '_id': {'$ne': product_id}}
            ]
        }).limit(4)
    )
    return render_template('product_detail.html', product=product, related_products=related_products)

@app.route('/car-spareparts/api/product/<int:product_id>')
def api_product_detail(product_id):
    product_doc = products_col.find_one({'$and': [{'_id': product_id}, get_store_visibility_filter()]})
    if not product_doc:
        return jsonify({'error': 'Product not found'}), 404
    product = doc_to_dict(product_doc)
    category_doc = categories_col.find_one({'_id': product.get('category_id')})
    product['category_name'] = doc_to_dict(category_doc)['name'] if category_doc else 'Unknown'
    product['category_icon'] = doc_to_dict(category_doc).get('icon', '') if category_doc else ''
    return jsonify(product)

@app.route('/car-spareparts/cart')
def cart():
    cart_items = []
    total = 0
    for item_doc in cart_items_col.find(get_cart_filter()):
        item = doc_to_dict(item_doc)
        product = doc_to_dict(products_col.find_one({'_id': item['product_id']}))
        if not product:
            cart_items_col.delete_one({'_id': item['id']})
            continue
        item['product'] = product
        total += product['price'] * item['quantity']
        cart_items.append(item)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/car-spareparts/checkout')
def checkout():
    cart_items = []
    total = 0
    for item_doc in cart_items_col.find(get_cart_filter()):
        item = doc_to_dict(item_doc)
        product = doc_to_dict(products_col.find_one({'_id': item['product_id']}))
        if not product:
            continue
        item['product'] = product
        total += product['price'] * item['quantity']
        cart_items.append(item)
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/car-spareparts/admin')
def admin():
    # Clean up expired custom demo products older than 24h
    cutoff = utcnow() - timedelta(hours=24)
    products_col.delete_many({'is_seed': False, 'session_id': {'$exists': True}, 'created_at': {'$lt': cutoff}})

    products_list = docs_to_list(products_col.find(get_store_visibility_filter()))
    categories = docs_to_list(categories_col.find())
    # Build a category lookup for template compatibility (product.category.name)
    cat_lookup = {cat['id']: cat for cat in categories}
    for product in products_list:
        product['category'] = cat_lookup.get(product.get('category_id'), {'name': 'Unknown'})
    return render_template('admin.html', products=products_list, categories=categories)

@app.route('/insights')
def site_insights():
    stats = stats_col.find_one({'_id': 'global_stats'})
    total_impressions = stats.get('total_visits', 0) if stats else 0
    unique_visitors = stats.get('unique_visitors', 0) if stats else 0
    
    # Current online count
    current_online = len(online_users)
    
    return render_template('dashboard.html', 
                         total_impressions=total_impressions, 
                         unique_visitors=unique_visitors,
                         online_count=current_online)

# ============================================================================
# API ROUTES
# ============================================================================

FREE_SHIPPING_THRESHOLD = 100.0


def build_cart_snapshot():
    """Return full itemized cart payload + totals for the live slide-out cart drawer."""
    cart_filter = get_cart_filter()
    items = []
    subtotal = 0.0
    total_qty = 0

    for item_doc in cart_items_col.find(cart_filter):
        item = doc_to_dict(item_doc)
        product = doc_to_dict(products_col.find_one({'_id': item['product_id']}))
        if not product:
            cart_items_col.delete_one({'_id': item['id']})
            continue
        qty = int(item.get('quantity', 1))
        price = float(product.get('price', 0))
        line_total = round(price * qty, 2)
        subtotal += line_total
        total_qty += qty
        items.append({
            'id': item['id'],
            'product_id': product['id'],
            'quantity': qty,
            'stock': int(product.get('stock', 0)),
            'name': product.get('name', 'Component'),
            'brand': product.get('brand', ''),
            'part_number': product.get('part_number', ''),
            'price': price,
            'image_url': product.get('image_url') or '/static/images/products/air-filter.webp',
            'line_total': line_total,
        })

    subtotal = round(subtotal, 2)
    tax = round(subtotal * 0.10, 2)
    total = round(subtotal + tax, 2)
    remaining = max(0.0, round(FREE_SHIPPING_THRESHOLD - subtotal, 2))

    return {
        'items': items,
        'cart_count': total_qty,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'free_shipping_threshold': FREE_SHIPPING_THRESHOLD,
        'free_shipping_unlocked': subtotal >= FREE_SHIPPING_THRESHOLD,
        'amount_to_free_shipping': remaining,
    }


@app.route('/car-spareparts/api/cart')
def api_cart_snapshot():
    return jsonify({'success': True, **build_cart_snapshot()})


@app.route('/car-spareparts/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json() or {}
    product_id = data.get('product_id')
    quantity = max(1, int(data.get('quantity', 1)))

    cart_filter = get_cart_filter()
    existing = cart_items_col.find_one({**cart_filter, 'product_id': product_id})

    if existing:
        cart_items_col.update_one({'_id': existing['_id']}, {'$inc': {'quantity': quantity}})
    else:
        cart_items_col.insert_one({**cart_filter, '_id': get_next_id('cart_items', spareparts_counters), 'product_id': product_id, 'quantity': quantity})

    snapshot = build_cart_snapshot()
    return jsonify({'success': True, 'cart_count': snapshot['cart_count'], 'cart': snapshot})

@app.route('/car-spareparts/api/cart/update', methods=['POST'])
def update_cart():
    data = request.get_json() or {}
    item_id = data.get('item_id')
    quantity = int(data.get('quantity', 0))

    cart_filter = get_cart_filter()
    cart_item = cart_items_col.find_one({**cart_filter, '_id': item_id})
    if cart_item:
        if quantity > 0:
            cart_items_col.update_one({'_id': item_id}, {'$set': {'quantity': quantity}})
        else:
            cart_items_col.delete_one({'_id': item_id})
        snapshot = build_cart_snapshot()
        return jsonify({'success': True, 'cart_count': snapshot['cart_count'], 'cart': snapshot})
    return jsonify({'success': False}), 404

@app.route('/car-spareparts/api/cart/remove/<int:item_id>', methods=['DELETE'])
def remove_from_cart(item_id):
    cart_filter = get_cart_filter()
    result = cart_items_col.delete_one({**cart_filter, '_id': item_id})
    if result.deleted_count > 0:
        snapshot = build_cart_snapshot()
        return jsonify({'success': True, 'cart_count': snapshot['cart_count'], 'cart': snapshot})
    return jsonify({'success': False}), 404

@app.route('/car-spareparts/api/order', methods=['POST'])
def create_order():
    data = request.get_json()

    cart_filter = get_cart_filter()
    cart_items = list(cart_items_col.find(cart_filter))
    if not cart_items:
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400

    total = 0
    items_list = []
    for item in cart_items:
        product = products_col.find_one({'_id': item['product_id']})
        if not product:
            continue
        total += product['price'] * item['quantity']
        items_list.append({
            'product': product['name'],
            'quantity': item['quantity'],
            'price': product['price']
        })

    if not items_list:
        return jsonify({'success': False, 'message': 'No valid items in cart'}), 400

    order_id = get_next_id('orders', spareparts_counters)
    order = {
        '_id': order_id,
        'customer_name': str(data.get('name') or '')[:120],
        'email': str(data.get('email') or '')[:120],
        'phone': str(data.get('phone') or '')[:40],
        'address': str(data.get('address') or '')[:400],
        'total_amount': total,
        'status': 'pending',
        'created_at': utcnow(),
        'items': str(items_list),
        'user_id': session.get('user_id')
    }

    orders_col.insert_one(order)
    # Clear only this user's cart
    cart_items_col.delete_many(cart_filter)
    return jsonify({'success': True, 'order_id': order_id})

@app.route('/car-spareparts/api/products', methods=['POST'])
def create_product():
    data = request.get_json() or {}
    sid = get_demo_session_id()

    if products_col.count_documents({'session_id': sid}) >= 15:
        return jsonify({'success': False, 'message': 'Demo limit reached (max 15 custom products per session).'}), 400

    name = str(data.get('name') or '').strip()[:120]
    brand = str(data.get('brand') or '').strip()[:80]
    if not name or not brand:
        return jsonify({'success': False, 'message': 'Product name and brand are required.'}), 400

    try:
        price = max(0.0, min(99999.99, float(data.get('price', 0))))
        stock = max(0, min(99999, int(data.get('stock', 0))))
        category_id = int(data.get('category_id', 1))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid price, stock, or category.'}), 400

    product = {
        '_id': get_next_id('products', spareparts_counters),
        'session_id': sid,
        'is_seed': False,
        'name': name,
        'description': str(data.get('description') or '')[:600],
        'price': price,
        'stock': stock,
        'brand': brand,
        'part_number': str(data.get('part_number') or '')[:60],
        'category_id': category_id,
        'compatible_cars': str(data.get('compatible_cars') or '')[:300],
        'specifications': str(data.get('specifications') or '')[:400],
        'featured': False,
        'image_url': '/static/images/products/air-filter.webp',
        'created_at': utcnow()
    }

    products_col.insert_one(product)
    return jsonify({'success': True, 'product_id': product['_id']})

@app.route('/car-spareparts/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    product = products_col.find_one({'_id': product_id})
    if not product:
        return jsonify({'success': False, 'message': 'Product not found.'}), 404
    if is_protected_seed_product(product):
        return jsonify({'success': False, 'message': 'Default demo products are protected and cannot be modified.'}), 403
    if product.get('session_id') != get_demo_session_id():
        return jsonify({'success': False, 'message': 'Not authorized to edit this demo item.'}), 403

    data = request.get_json() or {}
    update_fields = {}
    for field in ['name', 'description', 'price', 'stock', 'brand', 'part_number',
                  'category_id', 'compatible_cars', 'specifications']:
        if field in data:
            update_fields[field] = data[field]

    if update_fields:
        products_col.update_one({'_id': product_id}, {'$set': update_fields})

    return jsonify({'success': True})

@app.route('/car-spareparts/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    product = products_col.find_one({'_id': product_id})
    if not product:
        return jsonify({'success': False, 'message': 'Product not found.'}), 404
    if is_protected_seed_product(product):
        return jsonify({'success': False, 'message': 'Default demo products are protected. Add a custom product above to test deletion!'}), 403
    if product.get('session_id') != get_demo_session_id():
        return jsonify({'success': False, 'message': 'Not authorized to delete this demo item.'}), 403

    result = products_col.delete_one({'_id': product_id, 'session_id': get_demo_session_id()})
    if result.deleted_count > 0:
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/car-spareparts/api/cart/count')
def cart_count():
    cart_filter = get_cart_filter()
    pipeline = [{'$match': cart_filter}, {'$group': {'_id': None, 'total': {'$sum': '$quantity'}}}]
    result = list(cart_items_col.aggregate(pipeline))
    count = result[0]['total'] if result else 0
    return jsonify({'count': count})

# ============================================================================
# KANBAN ROUTES
# ============================================================================

@app.route('/kanban')
def kanban_page():
    return render_template('kanban/dashboard.html')


@app.route('/kanban/board')
def kanban_board():
    return render_template('kanban/board.html')


@app.route('/kanban/timeline')
def kanban_timeline():
    return render_template('kanban/timeline.html')


@app.route('/kanban/rules')
def kanban_rules():
    return render_template('kanban/rules.html')

@app.route('/kanban/api/tasks')
def kanban_list():
    sid = get_demo_session_id()
    ensure_session_kanban_tasks(sid)
    tasks = docs_to_list(kanban_col.find({'session_id': sid}).sort('created_at', -1))
    return jsonify({'tasks': tasks})

@app.route('/kanban/api/add', methods=['POST'])
def kanban_add():
    sid = get_demo_session_id()
    ensure_session_kanban_tasks(sid)
    if kanban_col.count_documents({'session_id': sid}) >= 40:
        return jsonify({'success': False, 'message': 'Demo board limit reached (max 40 tasks per session).'}), 400

    data = request.get_json() or {}
    subtasks_raw = data.get('subtasks', [])
    subtasks = [
        {'text': str(s.get('text', ''))[:200], 'done': bool(s.get('done', False))}
        for s in (subtasks_raw[:20] if isinstance(subtasks_raw, list) else [])
        if isinstance(s, dict) and str(s.get('text', '')).strip()
    ]
    status = data.get('status', 'todo')
    if status not in ('todo', 'in-progress', 'done'):
        status = 'todo'
    priority = data.get('priority', 'medium')
    if priority not in ('low', 'medium', 'high'):
        priority = 'medium'

    task = {
        '_id': get_next_id('kanban_tasks', kanban_counters),
        'session_id': sid,
        'name': str(data.get('name', ''))[:160],
        'description': str(data.get('description', ''))[:1200],
        'status': status,
        'priority': priority,
        'color': str(data.get('color', '#f59e0b'))[:20],
        'due_date': str(data.get('due_date'))[:10] if data.get('due_date') else None,
        'subtasks': subtasks,
        'created_at': utcnow().isoformat()
    }
    kanban_col.insert_one(task)
    return jsonify({'success': True, 'task_id': task['_id']})

@app.route('/kanban/api/update', methods=['POST'])
def kanban_update():
    sid = get_demo_session_id()
    data = request.get_json() or {}
    task_id = data.get('task_id')
    update = {}
    if 'name' in data:
        update['name'] = str(data['name'])[:160]
    if 'description' in data:
        update['description'] = str(data['description'])[:1200]
    if 'status' in data and data['status'] in ('todo', 'in-progress', 'done'):
        update['status'] = data['status']
    if 'priority' in data and data['priority'] in ('low', 'medium', 'high'):
        update['priority'] = data['priority']
    if 'color' in data:
        update['color'] = str(data['color'])[:20]
    if 'due_date' in data:
        update['due_date'] = str(data['due_date'])[:10] if data['due_date'] else None
    if 'subtasks' in data and isinstance(data['subtasks'], list):
        update['subtasks'] = [
            {'text': str(s.get('text', ''))[:200], 'done': bool(s.get('done', False))}
            for s in data['subtasks'][:20]
            if isinstance(s, dict) and str(s.get('text', '')).strip()
        ]
    if update:
        kanban_col.update_one({'_id': task_id, 'session_id': sid}, {'$set': update})
    return jsonify({'success': True})

@app.route('/kanban/api/move', methods=['POST'])
def kanban_move():
    sid = get_demo_session_id()
    data = request.get_json() or {}
    status = data.get('status')
    if status not in ('todo', 'in-progress', 'done'):
        return jsonify({'success': False}), 400
    kanban_col.update_one({'_id': data.get('task_id'), 'session_id': sid}, {'$set': {'status': status}})
    return jsonify({'success': True})

@app.route('/kanban/api/delete', methods=['POST'])
def kanban_delete():
    sid = get_demo_session_id()
    data = request.get_json() or {}
    kanban_col.delete_one({'_id': data.get('task_id'), 'session_id': sid})
    return jsonify({'success': True})

@app.route('/kanban/api/predict', methods=['POST'])
@rate_limit_ai('kanban_predict', per_minute=15, per_hour=80)
def kanban_predict():
    data = request.get_json() or {}
    description = str(data.get('description', ''))[:1000]
    priority = str(data.get('priority', 'medium'))[:20]
    try:
        estimated_days = ml_engine.predict_task_duration(description, priority)
        return jsonify({'success': True, 'estimated_days': estimated_days})
    except Exception as e:
        print(f"Kanban Predict ML Error: {e}")
        return jsonify({'success': False}), 500

# ============================================================================
# AI ASSISTANT API
# ============================================================================

@app.route('/car-spareparts/api/ask', methods=['POST'])
@rate_limit_ai('store_chat', per_minute=10, per_hour=60)
def chat_api_ask():
    data = request.get_json() or {}
    user_message = str(data.get('message', '')).strip()[:500]
    chat_history = str(data.get('history', ''))[-4000:]
    garage_vehicle = str(data.get('garage_vehicle', '')).strip()[:100]
    
    if not user_message:
        return jsonify({'success': False, 'message': 'No message provided.'}), 400
        
    # Get inventory context (official catalog + visitor's session items)
    products = list(products_col.find(get_store_visibility_filter()))
    inventory_context = "Available Products:\n"
    for p in products:
        inventory_context += (
            f"- {p.get('name')} (SKU: {p.get('part_number', 'N/A')}, Brand: {p.get('brand')}, "
            f"Price: ${p.get('price')}, Stock: {p.get('stock')}): {p.get('description')}. "
            f"Specs: {p.get('specifications', '')}. Compatible with: {p.get('compatible_cars')}.\n"
        )
    if garage_vehicle:
        inventory_context += f"\nCustomer's Active Garage Vehicle: {garage_vehicle} (prioritize compatible & universal parts for this vehicle when relevant).\n"
        
    # Query AI
    try:
        ai_response = ml_engine.ask_shopping_assistant(inventory_context, user_message, chat_history)
        return jsonify({'success': True, 'response': ai_response})
    except Exception as e:
        print(f"AI Assistant Error: {e}")
        return jsonify({'success': False, 'message': 'Error processing your request.'}), 500

@app.route('/api/portfolio/chat', methods=['POST'])
@rate_limit_ai('portfolio_chat', per_minute=10, per_hour=60)
def portfolio_chat():
    data = request.get_json() or {}
    user_message = str(data.get('message', '')).strip()[:500]
    chat_history = str(data.get('history', ''))[-4000:]

    if not user_message:
        return jsonify({'success': False, 'message': 'Please provide a message.'}), 400

    try:
        response = ml_engine.ask_portfolio_assistant(user_message, chat_history)
        return jsonify({'success': True, 'response': response})
    except Exception as e:
        print(f"Portfolio Assistant Error: {e}")
        return jsonify({'success': False, 'message': 'Failed to get response from AI assistant.'}), 500


# ============================================================================
# AI TOOL ROUTES
# ============================================================================

@app.route('/ai-tool')
def ai_tool_page():
    return render_template('ai_landing.html')


@app.route('/ai-tool/studio')
def ai_tool_studio():
    return render_template('ai_studio.html')


@app.route('/ai-tool/presets')
def ai_tool_presets():
    return render_template('ai_presets.html')


@app.route('/ai-tool/docs')
def ai_tool_docs():
    return render_template('ai_docs.html')

@app.route('/ai-tool/api/process', methods=['POST'])
def ai_process():
    data = request.get_json() or {}
    text = str(data.get('text', '')).strip()[:5000]
    mode = data.get('mode', 'summarize')
    use_ai = bool(data.get('use_ai', False))

    if not text:
        return jsonify({'success': False, 'message': 'Please provide some text.'}), 400

    # Apply strict rate limit when calling Gemini API, and a generous limit for local ML
    if use_ai:
        ok_min, retry_min = check_rate_limit('textforge_gemini:m', 10, 60)
        ok_hr, retry_hr = check_rate_limit('textforge_gemini:h', 60, 3600) if ok_min else (True, 0)
        if not ok_min or not ok_hr:
            retry = retry_min if not ok_min else retry_hr
            resp = jsonify({
                'success': False,
                'message': f'Gemini AI rate limit reached. Please wait {retry}s or switch Gemini AI OFF to use local ML.'
            })
            resp.status_code = 429
            resp.headers['Retry-After'] = str(retry)
            return resp
    else:
        ok_local, retry_local = check_rate_limit('textforge_local:m', 30, 60)
        if not ok_local:
            resp = jsonify({'success': False, 'message': f'Too many requests. Please wait {retry_local}s.'})
            resp.status_code = 429
            resp.headers['Retry-After'] = str(retry_local)
            return resp

    result = ''
    try:
        if mode == 'summarize':
            if use_ai:
                summary = ml_engine.summarize_text_gemini(text, num_sentences=max(2, len(text.split('.')) // 3))
                result = f"📝 Extractive Summary (Gemini 3.5 Flash Lite):\n\n{summary}"
            else:
                summary = ml_engine.summarize_text(text, num_sentences=max(2, len(text.split('.')) // 3))
                result = f"📝 Extractive Summary (TF-IDF):\n\n{summary}"

        elif mode == 'translate':
            target_lang = data.get('target_lang', 'id')
            if use_ai:
                prompt = f"Translate the following text to {target_lang}. Return only the translation.\n\nText: {text}"
                translated_text = ml_engine.call_gemini(prompt)
                result = f"🌍 Translation (Powered by Gemini 3.5 Flash Lite):\n\n{translated_text}"
            else:
                try:
                    mymemory_map = {
                        'id': 'id-ID', 'es': 'es-ES', 'fr': 'fr-FR', 'de': 'de-DE',
                        'ja': 'ja-JP', 'ko': 'ko-KR', 'zh-CN': 'zh-CN', 'ar': 'ar-SA',
                        'ru': 'ru-RU', 'pt': 'pt-PT', 'it': 'it-IT', 'hi': 'hi-IN',
                        'nl': 'nl-NL', 'tr': 'tr-TR', 'vi': 'vi-VN', 'th': 'th-TH', 'en': 'en-GB'
                    }
                    my_mem_lang = mymemory_map.get(target_lang, target_lang)
                    
                    # Detect the source language
                    try:
                        detected_code = detect(text)
                        # Map to MyMemory format if possible, otherwise use the raw code
                        source_lang = mymemory_map.get(detected_code, detected_code)
                    except:
                        source_lang = 'en-GB' # Fallback
                    
                    # MyMemory API has a 500 character limit per request.
                    # We split the text into chunks of 450 characters (preserving word boundaries).
                    chunks = textwrap.wrap(text, width=450, replace_whitespace=False)
                    translated_chunks = []
                    
                    translator = MyMemoryTranslator(source=source_lang, target=my_mem_lang)
                    for chunk in chunks:
                        translated_chunks.append(translator.translate(chunk))
                        
                    translated_text = " ".join(translated_chunks)
                    result = f"🌍 Translation (Powered by MyMemory API):\n\n{translated_text}"
                except Exception as t_err:
                    print(f"Translation sub-error: {t_err}")
                    result = "🌍 Translation failed. Please try again later."

        elif mode == 'tone':
            # Analyze tone rather than simply prepending text
            if use_ai:
                sent_info = ml_engine.analyze_sentiment_gemini(text)
                tone_desc = sent_info.get('tone', 'Neutral')
                result = f"🎭 AI Sentiment Analysis (Gemini 3.5 Flash Lite):\n\nPrimary Tone: {tone_desc}\n\nRaw Metrics:\n- Polarity: {sent_info.get('polarity', 0)}\n- Subjectivity: {sent_info.get('subjectivity', 0)}"
            else:
                sent_info = ml_engine.analyze_sentiment(text)
                tone_desc = ""
                if sent_info['polarity'] > 0.3:
                    tone_desc = "Highly Positive & Enthusiastic"
                elif sent_info['polarity'] > 0:
                    tone_desc = "Slightly Positive / Warm"
                elif sent_info['polarity'] < -0.3:
                    tone_desc = "Highly Negative / Critical"
                elif sent_info['polarity'] < 0:
                    tone_desc = "Slightly Negative / Cold"
                else:
                    tone_desc = "Neutral / Objective"
                    
                subj_desc = "Highly Opinionated" if sent_info['subjectivity'] > 0.6 else ("Factual / Objective" if sent_info['subjectivity'] < 0.4 else "Mixed Fact & Opinion")

                result = f"🎭 Machine Learning Sentiment Analysis (TextBlob):\n\nPrimary Tone: {tone_desc}\nObjectivity: {subj_desc}\n\nRaw Metrics:\n- Polarity: {sent_info['polarity']}\n- Subjectivity: {sent_info['subjectivity']}"

        elif mode == 'document':
            query = data.get('query', '')
            if not query:
                result = "Please provide a query for the document Q&A."
            else:
                if use_ai:
                    rag_results = ml_engine.chat_with_document_gemini(text, query)
                    result = f"🔍 Document Q&A (Gemini 3.5 Flash Lite):\n\nQuery: {query}\n\n"
                    for i, r in enumerate(rag_results, 1):
                        result += f"Match {i} (Confidence {r['score']}%):\n> {r['text']}\n\n"
                else:
                    rag_results = ml_engine.chat_with_document(text, query, top_k=2)
                    result = f"🔍 Document Q&A (Okapi BM25):\n\nQuery: {query}\n\n"
                    for i, r in enumerate(rag_results, 1):
                        result += f"Match {i} (Confidence {r['score']}%):\n> {r['text']}\n\n"

        elif mode == 'ticket':
            if use_ai:
                res = ml_engine.categorize_ticket_gemini(text)
                result = f"🎫 AI Support Desk Triage (Gemini 3.5 Flash Lite):\n\nPredicted Category: {res['category']}\nConfidence Score: {res['confidence']}%\n\n> This mode uses a Zero-Shot prompt sent to the Gemini API to categorize tickets."
            else:
                res = ml_engine.categorize_ticket_classic(text)
                result = f"🎫 AI Support Desk Triage (Naive Bayes):\n\nPredicted Category: {res['category']}\nConfidence Score: {res['confidence']}%\n\n> This mode uses a MultinomialNB classifier trained on an internal support dataset."

    except Exception as e:
        print(f"ML Pipeline Error: {e}")
        return jsonify({'success': False, 'message': 'Machine learning inference failed.'}), 500

    return jsonify({'success': True, 'result': result})


# ============================================================================
# SEO ROUTES (robots.txt & sitemap.xml) + THEMED ERROR PAGES
# ============================================================================

@app.route('/robots.txt')
def robots_txt():
    sitemap_url = url_for('sitemap_xml', _external=True)
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /api/',
        'Disallow: /car-spareparts/api/',
        'Disallow: /car-spareparts/admin',
        'Disallow: /car-spareparts/cart',
        'Disallow: /car-spareparts/checkout',
        'Disallow: /kanban/api/',
        'Disallow: /ai-tool/api/',
        f'Sitemap: {sitemap_url}',
    ]
    return Response('\n'.join(lines) + '\n', mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    pages = [
        ('portfolio_home', '1.0', 'weekly'),
        ('site_insights', '0.6', 'weekly'),
        ('store_home', '0.8', 'monthly'),
        ('products', '0.7', 'monthly'),
        ('kanban_page', '0.8', 'monthly'),
        ('kanban_board', '0.7', 'monthly'),
        ('kanban_timeline', '0.6', 'monthly'),
        ('kanban_rules', '0.6', 'monthly'),
        ('ai_tool_page', '0.8', 'monthly'),
        ('ai_tool_studio', '0.8', 'monthly'),
        ('ai_tool_presets', '0.6', 'monthly'),
        ('ai_tool_docs', '0.6', 'monthly'),
    ]
    today = utcnow().strftime('%Y-%m-%d')
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for endpoint, priority, changefreq in pages:
        loc = url_for(endpoint, _external=True)
        xml_lines.append(
            f'  <url><loc>{loc}</loc><lastmod>{today}</lastmod>'
            f'<changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>'
        )
    xml_lines.append('</urlset>')
    return Response('\n'.join(xml_lines), mimetype='application/xml')


@app.errorhandler(404)
def handle_404(err):
    if '/api/' in request.path or request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return render_template(
        'error.html',
        error_code=404,
        error_title='Page Not Found',
        error_message="The page you're looking for doesn't exist or may have moved. Head back to the Portfolio Hub to explore live projects."
    ), 404


@app.errorhandler(500)
def handle_500(err):
    if '/api/' in request.path or request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    return render_template(
        'error.html',
        error_code=500,
        error_title='Something Went Wrong',
        error_message='An unexpected server error occurred while loading this page. Please try again in a moment.'
    ), 500


# ============================================================================
# INITIALIZATION (Runs on import for WSGI like Gunicorn)
# ============================================================================
init_db()
ml_engine.init_models()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True, port=8000)
