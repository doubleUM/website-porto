from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO, emit, join_room, leave_room
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
import os
import uuid
import re

load_dotenv()

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins='*')

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

client = MongoClient(os.getenv('MONGODB_URI'))
db = client.spareparts_db

# Collections — Spareparts
categories_col = db.categories
products_col = db.products
cart_items_col = db.cart_items
orders_col = db.orders
counters_col = db.counters
users_col = db.users

# Collections — Kanban
kanban_col = db.kanban_tasks

# Collections — Chat
chat_messages_col = db.chat_messages

# Active chat users tracker
chat_users = {}

# ============================================================================
# CONTEXT PROCESSOR — injects current_user into every template
# ============================================================================

@app.context_processor
def inject_user():
    user_id = session.get('user_id')
    if user_id:
        user = users_col.find_one({'_id': user_id}, {'password': 0})
        return {'current_user': user}
    return {'current_user': None}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_next_id(collection_name):
    """Auto-increment integer ID using a counters collection."""
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

# ============================================================================
# INITIALIZE DATABASE WITH SAMPLE DATA
# ============================================================================

def init_db():
    # Check if data already exists
    if categories_col.count_documents({}) == 0:
        # Create categories
        categories_data = [
            {'_id': get_next_id('categories'), 'name': 'Engine Parts', 'description': 'High-performance engine components', 'icon': '🔧'},
            {'_id': get_next_id('categories'), 'name': 'Brake Systems', 'description': 'Premium brake pads and rotors', 'icon': '🛑'},
            {'_id': get_next_id('categories'), 'name': 'Electrical', 'description': 'Batteries, alternators, and wiring', 'icon': '⚡'},
            {'_id': get_next_id('categories'), 'name': 'Suspension', 'description': 'Shocks, struts, and control arms', 'icon': '🔩'},
            {'_id': get_next_id('categories'), 'name': 'Filters', 'description': 'Oil, air, and fuel filters', 'icon': '🔍'},
            {'_id': get_next_id('categories'), 'name': 'Lighting', 'description': 'Headlights, tail lights, and bulbs', 'icon': '💡'},
        ]
        categories_col.insert_many(categories_data)

        # Create sample products
        products_data = [
            # Engine Parts
            {'_id': get_next_id('products'), 'name': 'Premium Oil Filter', 'description': 'High-efficiency oil filter for optimal engine protection',
             'price': 15.99, 'stock': 150, 'brand': 'AutoPro', 'part_number': 'OF-2024',
             'category_id': 1, 'compatible_cars': 'Toyota Camry, Honda Accord, Ford Focus',
             'specifications': 'Thread size: 3/4-16, Height: 3.5 inches', 'featured': True,
             'image_url': '/static/images/products/oil-filter.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Spark Plug Set (4pc)', 'description': 'Iridium spark plugs for improved performance',
             'price': 45.99, 'stock': 80, 'brand': 'NGK', 'part_number': 'SP-IR-401',
             'category_id': 1, 'compatible_cars': 'Most 4-cylinder engines',
             'specifications': 'Gap: 0.044", Thread: 14mm', 'featured': True,
             'image_url': '/static/images/products/spark-plugs.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Air Filter', 'description': 'High-flow air filter for better engine breathing',
             'price': 24.99, 'stock': 120, 'brand': 'K&N', 'part_number': 'AF-3320',
             'category_id': 5, 'compatible_cars': 'Universal fit for most sedans',
             'specifications': 'Washable and reusable', 'featured': False,
             'image_url': '/static/images/products/air-filter.png', 'created_at': datetime.utcnow()},

            # Brake Systems
            {'_id': get_next_id('products'), 'name': 'Ceramic Brake Pads', 'description': 'Low-dust ceramic brake pads for quiet stopping',
             'price': 89.99, 'stock': 60, 'brand': 'Brembo', 'part_number': 'BP-CER-500',
             'category_id': 2, 'compatible_cars': 'Honda Civic, Toyota Corolla',
             'specifications': 'Front axle, includes shims', 'featured': True,
             'image_url': '/static/images/products/brake-pads.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Brake Rotors (Pair)', 'description': 'Slotted and drilled performance rotors',
             'price': 159.99, 'stock': 40, 'brand': 'PowerStop', 'part_number': 'BR-SP-250',
             'category_id': 2, 'compatible_cars': 'Ford Mustang, Chevrolet Camaro',
             'specifications': 'Front, 12.6" diameter', 'featured': False,
             'image_url': '/static/images/products/brake-rotors.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Brake Fluid DOT 4', 'description': 'Premium synthetic brake fluid',
             'price': 12.99, 'stock': 200, 'brand': 'Castrol', 'part_number': 'BF-DOT4-500',
             'category_id': 2, 'compatible_cars': 'Universal',
             'specifications': '500ml bottle, high boiling point', 'featured': False,
             'image_url': '/static/images/products/brake-fluid.png', 'created_at': datetime.utcnow()},

            # Electrical
            {'_id': get_next_id('products'), 'name': 'Car Battery 12V', 'description': 'Maintenance-free AGM battery',
             'price': 189.99, 'stock': 35, 'brand': 'Optima', 'part_number': 'BAT-AGM-75',
             'category_id': 3, 'compatible_cars': 'Most sedans and trucks',
             'specifications': '750 CCA, 75 Ah, 3-year warranty', 'featured': True,
             'image_url': '/static/images/products/car-battery.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Alternator', 'description': 'High-output alternator for reliable charging',
             'price': 249.99, 'stock': 25, 'brand': 'Bosch', 'part_number': 'ALT-150A',
             'category_id': 3, 'compatible_cars': 'Toyota Tacoma, 4Runner',
             'specifications': '150 Amp output', 'featured': False,
             'image_url': '/static/images/products/alternator.png', 'created_at': datetime.utcnow()},

            # Suspension
            {'_id': get_next_id('products'), 'name': 'Shock Absorber Set', 'description': 'Gas-charged shock absorbers for smooth ride',
             'price': 199.99, 'stock': 30, 'brand': 'Monroe', 'part_number': 'SH-GAS-400',
             'category_id': 4, 'compatible_cars': 'Nissan Altima, Mazda 6',
             'specifications': 'Rear pair, gas-charged', 'featured': True,
             'image_url': '/static/images/products/shock-absorbers.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Coil Spring Set', 'description': 'Heavy-duty coil springs',
             'price': 139.99, 'stock': 45, 'brand': 'Eibach', 'part_number': 'CS-HD-300',
             'category_id': 4, 'compatible_cars': 'Jeep Wrangler, Cherokee',
             'specifications': 'Front pair, +2" lift', 'featured': False,
             'image_url': '/static/images/products/coil-springs.png', 'created_at': datetime.utcnow()},

            # Filters
            {'_id': get_next_id('products'), 'name': 'Fuel Filter', 'description': 'High-pressure fuel filter',
             'price': 19.99, 'stock': 100, 'brand': 'Wix', 'part_number': 'FF-HP-200',
             'category_id': 5, 'compatible_cars': 'Most fuel-injected vehicles',
             'specifications': 'In-line mount, 10 micron', 'featured': False,
             'image_url': '/static/images/products/fuel-filter.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Cabin Air Filter', 'description': 'Activated carbon cabin filter',
             'price': 16.99, 'stock': 110, 'brand': 'Mann', 'part_number': 'CAF-AC-150',
             'category_id': 5, 'compatible_cars': 'BMW 3-Series, Mercedes C-Class',
             'specifications': 'HEPA filtration, odor elimination', 'featured': False,
             'image_url': '/static/images/products/cabin-filter.png', 'created_at': datetime.utcnow()},

            # Lighting
            {'_id': get_next_id('products'), 'name': 'LED Headlight Bulbs', 'description': 'Super bright LED conversion kit',
             'price': 79.99, 'stock': 70, 'brand': 'Osram', 'part_number': 'LED-H7-6K',
             'category_id': 6, 'compatible_cars': 'H7 socket (most European cars)',
             'specifications': '6000K white, 12000 lumens', 'featured': True,
             'image_url': '/static/images/products/led-headlights.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Fog Light Assembly', 'description': 'Complete fog light kit',
             'price': 129.99, 'stock': 50, 'brand': 'Hella', 'part_number': 'FL-KIT-500',
             'category_id': 6, 'compatible_cars': 'Universal with custom brackets',
             'specifications': 'Includes wiring harness and switch', 'featured': False,
             'image_url': '/static/images/products/fog-light.png', 'created_at': datetime.utcnow()},

            {'_id': get_next_id('products'), 'name': 'Halogen Light Bulb', 'description': 'Classic halogen headlight bulb with warm white light',
             'price': 29.99, 'stock': 90, 'brand': 'Philips', 'part_number': 'HL-H4-3200K',
             'category_id': 6, 'compatible_cars': 'H4 socket (most Japanese and Korean cars)',
             'specifications': '3200K warm white, 1500 lumens, 55W', 'featured': False,
             'image_url': '/static/images/products/halogen-headlight.png', 'created_at': datetime.utcnow()},
        ]
        products_col.insert_many(products_data)
        print("Database initialized with sample data!")

# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.route('/login')
def login_page():
    if session.get('user_id'):
        return redirect(url_for('store_home'))
    return render_template('login.html')

@app.route('/api/auth/signup', methods=['POST'])
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
    user_id = get_next_id('users')
    users_col.insert_one({
        '_id': user_id,
        'name': name,
        'email': email,
        'password': hashed_pw,
        'created_at': datetime.utcnow()
    })

    session['user_id'] = user_id
    session['user_name'] = name
    merge_carts(user_id)
    return jsonify({'success': True, 'name': name})

@app.route('/api/auth/login', methods=['POST'])
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

@app.route('/api/auth/logout')
def logout():
    session.clear()
    return redirect(url_for('portfolio_home'))

# ============================================================================
# ROUTES - PAGE VIEWS
# ============================================================================

@app.route('/')
def portfolio_home():
    ignored_dirs = {'venv', '.git', '__pycache__'}
    max_mtime = 0
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for f in files:
            if f.endswith('.pyc') or f == '.env': 
                continue
            filepath = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime > max_mtime:
                    max_mtime = mtime
            except Exception:
                pass
    last_update = datetime.fromtimestamp(max_mtime) if max_mtime > 0 else datetime.now()
    last_update_str = last_update.strftime('%B %Y')
    return render_template('portfolio_home.html', last_update=last_update_str)


@app.route('/car-spareparts')
def store_home():
    featured_products = docs_to_list(products_col.find({'featured': True}).limit(6))
    categories = docs_to_list(categories_col.find())
    return render_template('index.html', featured_products=featured_products, categories=categories)

@app.route('/products')
def products():
    category_id = request.args.get('category', type=int)
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', 'name')

    query_filter = {}

    if category_id:
        query_filter['category_id'] = category_id

    if search_query:
        query_filter['$or'] = [
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'description': {'$regex': search_query, '$options': 'i'}},
            {'brand': {'$regex': search_query, '$options': 'i'}},
        ]

    # Sorting
    sort_field = 'name'
    sort_direction = 1  # ascending
    if sort_by == 'price_asc':
        sort_field = 'price'
        sort_direction = 1
    elif sort_by == 'price_desc':
        sort_field = 'price'
        sort_direction = -1

    products_list = docs_to_list(products_col.find(query_filter).sort(sort_field, sort_direction))
    categories = docs_to_list(categories_col.find())

    return render_template('products.html', products=products_list, categories=categories,
                         current_category=category_id, search_query=search_query)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product_doc = products_col.find_one({'_id': product_id})
    if not product_doc:
        return "Product not found", 404
    product = doc_to_dict(product_doc)
    # Attach category for template compatibility (product.category.name)
    category_doc = categories_col.find_one({'_id': product['category_id']})
    product['category'] = doc_to_dict(category_doc) if category_doc else {'name': 'Unknown'}
    related_products = docs_to_list(
        products_col.find({'category_id': product['category_id'], '_id': {'$ne': product_id}}).limit(4)
    )
    return render_template('product_detail.html', product=product, related_products=related_products)

@app.route('/api/product/<int:product_id>')
def api_product_detail(product_id):
    product_doc = products_col.find_one({'_id': product_id})
    if not product_doc:
        return jsonify({'error': 'Product not found'}), 404
    product = doc_to_dict(product_doc)
    category_doc = categories_col.find_one({'_id': product.get('category_id')})
    product['category_name'] = doc_to_dict(category_doc)['name'] if category_doc else 'Unknown'
    product['category_icon'] = doc_to_dict(category_doc).get('icon', '') if category_doc else ''
    return jsonify(product)

@app.route('/cart')
def cart():
    cart_items = []
    total = 0
    for item_doc in cart_items_col.find(get_cart_filter()):
        item = doc_to_dict(item_doc)
        product = doc_to_dict(products_col.find_one({'_id': item['product_id']}))
        item['product'] = product
        total += product['price'] * item['quantity']
        cart_items.append(item)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/checkout')
def checkout():
    cart_items = []
    total = 0
    for item_doc in cart_items_col.find(get_cart_filter()):
        item = doc_to_dict(item_doc)
        product = doc_to_dict(products_col.find_one({'_id': item['product_id']}))
        item['product'] = product
        total += product['price'] * item['quantity']
        cart_items.append(item)
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/admin')
def admin():
    products_list = docs_to_list(products_col.find())
    categories = docs_to_list(categories_col.find())
    # Build a category lookup for template compatibility (product.category.name)
    cat_lookup = {cat['id']: cat for cat in categories}
    for product in products_list:
        product['category'] = cat_lookup.get(product.get('category_id'), {'name': 'Unknown'})
    return render_template('admin.html', products=products_list, categories=categories)

# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    cart_filter = get_cart_filter()
    existing = cart_items_col.find_one({**cart_filter, 'product_id': product_id})

    if existing:
        cart_items_col.update_one({'_id': existing['_id']}, {'$inc': {'quantity': quantity}})
    else:
        cart_items_col.insert_one({**cart_filter, '_id': get_next_id('cart_items'), 'product_id': product_id, 'quantity': quantity})

    # Count only this user's cart
    pipeline = [{'$match': cart_filter}, {'$group': {'_id': None, 'total': {'$sum': '$quantity'}}}]
    result = list(cart_items_col.aggregate(pipeline))
    cart_count = result[0]['total'] if result else 0

    return jsonify({'success': True, 'cart_count': cart_count})

@app.route('/api/cart/update', methods=['POST'])
def update_cart():
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity')

    cart_filter = get_cart_filter()
    cart_item = cart_items_col.find_one({**cart_filter, '_id': item_id})
    if cart_item:
        if quantity > 0:
            cart_items_col.update_one({'_id': item_id}, {'$set': {'quantity': quantity}})
        else:
            cart_items_col.delete_one({'_id': item_id})
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/cart/remove/<int:item_id>', methods=['DELETE'])
def remove_from_cart(item_id):
    cart_filter = get_cart_filter()
    result = cart_items_col.delete_one({**cart_filter, '_id': item_id})
    if result.deleted_count > 0:
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/order', methods=['POST'])
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
        total += product['price'] * item['quantity']
        items_list.append({
            'product': product['name'],
            'quantity': item['quantity'],
            'price': product['price']
        })

    order_id = get_next_id('orders')
    order = {
        '_id': order_id,
        'customer_name': data.get('name'),
        'email': data.get('email'),
        'phone': data.get('phone'),
        'address': data.get('address'),
        'total_amount': total,
        'status': 'pending',
        'created_at': datetime.utcnow(),
        'items': str(items_list),
        'user_id': session.get('user_id')
    }

    orders_col.insert_one(order)
    # Clear only this user's cart
    cart_items_col.delete_many(cart_filter)
    return jsonify({'success': True, 'order_id': order_id})

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json()

    product = {
        '_id': get_next_id('products'),
        'name': data.get('name'),
        'description': data.get('description'),
        'price': data.get('price'),
        'stock': data.get('stock'),
        'brand': data.get('brand'),
        'part_number': data.get('part_number'),
        'category_id': data.get('category_id'),
        'compatible_cars': data.get('compatible_cars'),
        'specifications': data.get('specifications'),
        'featured': False,
        'image_url': '',
        'created_at': datetime.utcnow()
    }

    products_col.insert_one(product)
    return jsonify({'success': True, 'product_id': product['_id']})

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    product = products_col.find_one({'_id': product_id})
    if not product:
        return jsonify({'success': False}), 404

    data = request.get_json()
    update_fields = {}
    for field in ['name', 'description', 'price', 'stock', 'brand', 'part_number',
                  'category_id', 'compatible_cars', 'specifications']:
        if field in data:
            update_fields[field] = data[field]

    if update_fields:
        products_col.update_one({'_id': product_id}, {'$set': update_fields})

    return jsonify({'success': True})

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    result = products_col.delete_one({'_id': product_id})
    if result.deleted_count > 0:
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/cart/count')
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

@app.route('/api/kanban/tasks')
def kanban_list():
    tasks = docs_to_list(kanban_col.find().sort('created_at', -1))
    return jsonify({'tasks': tasks})

@app.route('/api/kanban/add', methods=['POST'])
def kanban_add():
    data = request.get_json()
    task = {
        '_id': get_next_id('kanban_tasks'),
        'name': data.get('name', ''),
        'description': data.get('description', ''),
        'status': data.get('status', 'todo'),
        'priority': data.get('priority', 'medium'),
        'color': data.get('color', '#f59e0b'),
        'due_date': data.get('due_date'),
        'subtasks': data.get('subtasks', []),
        'created_at': datetime.utcnow().isoformat()
    }
    kanban_col.insert_one(task)
    return jsonify({'success': True, 'task_id': task['_id']})

@app.route('/api/kanban/update', methods=['POST'])
def kanban_update():
    data = request.get_json()
    task_id = data.get('task_id')
    update = {}
    for f in ['name', 'description', 'status', 'priority', 'color', 'due_date', 'subtasks']:
        if f in data:
            update[f] = data[f]
    kanban_col.update_one({'_id': task_id}, {'$set': update})
    return jsonify({'success': True})

@app.route('/api/kanban/move', methods=['POST'])
def kanban_move():
    data = request.get_json()
    kanban_col.update_one({'_id': data['task_id']}, {'$set': {'status': data['status']}})
    return jsonify({'success': True})

@app.route('/api/kanban/delete', methods=['POST'])
def kanban_delete():
    data = request.get_json()
    kanban_col.delete_one({'_id': data['task_id']})
    return jsonify({'success': True})

# ============================================================================
# CHAT ROUTES & SOCKET EVENTS
# ============================================================================

@app.route('/chat')
def chat_page():
    return render_template('chat_lobby.html')


@app.route('/chat/app')
def chat_app_page():
    return render_template('chat_app.html')


@app.route('/chat/settings')
def chat_settings_page():
    return render_template('chat_settings.html')

@socketio.on('set_username')
def handle_set_username(data):
    chat_users[request.sid] = data.get('username', 'Anonymous')
    emit('online_count', {'count': len(chat_users)}, broadcast=True)

@socketio.on('join_room')
def handle_join(data):
    room = data.get('room', 'general')
    join_room(room)
    username = chat_users.get(request.sid, 'Someone')
    # Send last 50 messages as history
    history = list(chat_messages_col.find({'room': room}).sort('created_at', -1).limit(50))
    history.reverse()
    history_list = [{'username': m.get('username',''), 'message': m.get('message',''), 'time': m.get('time','')} for m in history]
    emit('message_history', {'messages': history_list})
    emit('system_message', {'message': f'{username} joined the room'}, room=room)
    emit('online_count', {'count': len(chat_users)}, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    room = data.get('room', 'general')
    username = chat_users.get(request.sid, '')
    if username:
        emit('user_typing', {'username': username}, room=room, include_self=False)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    room = data.get('room', 'general')
    username = chat_users.get(request.sid, '')
    if username:
        emit('user_stop_typing', {'username': username}, room=room, include_self=False)

@socketio.on('leave_room')
def handle_leave(data):
    room = data.get('room', 'general')
    leave_room(room)
    username = chat_users.get(request.sid, 'Someone')
    emit('system_message', {'message': f'{username} left the room'}, room=room)

@socketio.on('send_message')
def handle_message(data):
    room = data.get('room', 'general')
    message = data.get('message', '')
    username = data.get('username', 'Anonymous')
    now = datetime.utcnow()
    msg_doc = {
        '_id': get_next_id('chat_messages'),
        'room': room,
        'username': username,
        'message': message,
        'time': now.strftime('%H:%M'),
        'created_at': now
    }
    chat_messages_col.insert_one(msg_doc)
    emit('new_message', {'username': username, 'message': message, 'time': msg_doc['time']}, room=room)

@socketio.on('disconnect')
def handle_disconnect():
    chat_users.pop(request.sid, None)
    emit('online_count', {'count': len(chat_users)}, broadcast=True)

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

@app.route('/api/ai/process', methods=['POST'])
def ai_process():
    data = request.get_json()
    text = data.get('text', '').strip()
    mode = data.get('mode', 'summarize')

    if not text:
        return jsonify({'success': False, 'message': 'Please provide some text.'}), 400

    import time
    time.sleep(1)  # Simulate processing delay

    result = ''
    if mode == 'summarize':
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 2:
            result = text
        else:
            # Take first sentence and every other sentence for summary
            key_sentences = [sentences[0]]
            for i, s in enumerate(sentences[1:], 1):
                if i % 2 == 0 or i == len(sentences) - 1:
                    key_sentences.append(s)
            result = ' '.join(key_sentences)
        result = f"📝 Summary:\n\n{result}\n\n— Condensed from {len(sentences)} sentences to {len(result.split('. '))} key points."

    elif mode == 'translate':
        target_lang = data.get('target_lang', 'Indonesian')
        # Mock translation — in production, integrate with a real API
        result = f"🌍 Translation to {target_lang}:\n\n[Mock translation — this is a demo]\n\nOriginal ({len(text)} chars):\n{text[:200]}{'...' if len(text) > 200 else ''}\n\n💡 To enable real translation, connect an API key (Google Translate, DeepL, etc.)"

    elif mode == 'tone':
        target_tone = data.get('target_tone', 'professional')
        tone_prefixes = {
            'professional': 'In a professional context, ',
            'casual': 'So basically, ',
            'friendly': 'Hey! Just wanted to share — ',
            'formal': 'It is hereby stated that ',
            'humorous': 'You won\'t believe this, but '
        }
        prefix = tone_prefixes.get(target_tone, '')
        # Simplistic tone mock — just prepend and adjust
        result = f"🎭 {target_tone.title()} Tone:\n\n{prefix}{text[0].lower()}{text[1:]}\n\n— Tone adjusted to: {target_tone}"

    elif mode == 'explain':
        word_count = len(text.split())
        result = f"💡 Explanation:\n\nThe provided text ({word_count} words) discusses the following key concepts:\n\n"
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for i, s in enumerate(sentences[:5], 1):
            result += f"{i}. {s.strip()}\n   → This point establishes {'the context' if i == 1 else 'supporting information'}.\n\n"
        result += f"Overall, the text covers {min(len(sentences), 5)} main ideas in {word_count} words."

    return jsonify({'success': True, 'result': result})

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, port=8000)
