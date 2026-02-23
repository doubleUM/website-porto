from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
import os
import uuid

load_dotenv()

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

client = MongoClient(os.getenv('MONGODB_URI'))
db = client.spareparts_db

# Collections
categories_col = db.categories
products_col = db.products
cart_items_col = db.cart_items
orders_col = db.orders
counters_col = db.counters
users_col = db.users

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
        return redirect(url_for('index'))
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
    return redirect(url_for('index'))

# ============================================================================
# ROUTES - PAGE VIEWS
# ============================================================================

@app.route('/')
def index():
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
# MAIN
# ============================================================================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8000)
