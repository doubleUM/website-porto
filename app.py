from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///spareparts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'

db = SQLAlchemy(app)

# ============================================================================
# DATABASE MODELS
# ============================================================================

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    brand = db.Column(db.String(100))
    part_number = db.Column(db.String(100))
    image_url = db.Column(db.String(500))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    compatible_cars = db.Column(db.Text)  # Stored as comma-separated values
    specifications = db.Column(db.Text)
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    session_id = db.Column(db.String(100))
    product = db.relationship('Product', backref='cart_items')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50))
    address = db.Column(db.Text, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.Column(db.Text)  # Stored as JSON string

# ============================================================================
# INITIALIZE DATABASE WITH SAMPLE DATA
# ============================================================================

def init_db():
    with app.app_context():
        db.create_all()
        
        # Check if data already exists
        if Category.query.first() is None:
            # Create categories
            categories_data = [
                {'name': 'Engine Parts', 'description': 'High-performance engine components', 'icon': '🔧'},
                {'name': 'Brake Systems', 'description': 'Premium brake pads and rotors', 'icon': '🛑'},
                {'name': 'Electrical', 'description': 'Batteries, alternators, and wiring', 'icon': '⚡'},
                {'name': 'Suspension', 'description': 'Shocks, struts, and control arms', 'icon': '🔩'},
                {'name': 'Filters', 'description': 'Oil, air, and fuel filters', 'icon': '🔍'},
                {'name': 'Lighting', 'description': 'Headlights, tail lights, and bulbs', 'icon': '💡'},
            ]
            
            categories = []
            for cat_data in categories_data:
                category = Category(**cat_data)
                db.session.add(category)
                categories.append(category)
            
            db.session.commit()
            
            # Create sample products
            products_data = [
                # Engine Parts
                {'name': 'Premium Oil Filter', 'description': 'High-efficiency oil filter for optimal engine protection', 
                 'price': 15.99, 'stock': 150, 'brand': 'AutoPro', 'part_number': 'OF-2024',
                 'category_id': 1, 'compatible_cars': 'Toyota Camry, Honda Accord, Ford Focus',
                 'specifications': 'Thread size: 3/4-16, Height: 3.5 inches', 'featured': True,
                 'image_url': '/static/images/products/oil-filter.svg'},
                
                {'name': 'Spark Plug Set (4pc)', 'description': 'Iridium spark plugs for improved performance',
                 'price': 45.99, 'stock': 80, 'brand': 'Champion', 'part_number': 'SP-IR-401',
                 'category_id': 1, 'compatible_cars': 'Most 4-cylinder engines',
                 'specifications': 'Gap: 0.044", Thread: 14mm', 'featured': True,
                 'image_url': '/static/images/products/spark-plugs.svg'},
                
                {'name': 'Air Filter', 'description': 'High-flow air filter for better engine breathing',
                 'price': 24.99, 'stock': 120, 'brand': 'K&N', 'part_number': 'AF-3320',
                 'category_id': 5, 'compatible_cars': 'Universal fit for most sedans',
                 'specifications': 'Washable and reusable', 'featured': False,
                 'image_url': '/static/images/products/air-filter.svg'},
                
                # Brake Systems
                {'name': 'Ceramic Brake Pads', 'description': 'Low-dust ceramic brake pads for quiet stopping',
                 'price': 89.99, 'stock': 60, 'brand': 'Brembo', 'part_number': 'BP-CER-500',
                 'category_id': 2, 'compatible_cars': 'Honda Civic, Toyota Corolla',
                 'specifications': 'Front axle, includes shims', 'featured': True,
                 'image_url': '/static/images/products/brake-pads.svg'},
                
                {'name': 'Brake Rotors (Pair)', 'description': 'Slotted and drilled performance rotors',
                 'price': 159.99, 'stock': 40, 'brand': 'PowerStop', 'part_number': 'BR-SP-250',
                 'category_id': 2, 'compatible_cars': 'Ford Mustang, Chevrolet Camaro',
                 'specifications': 'Front, 12.6" diameter', 'featured': False,
                 'image_url': '/static/images/products/brake-rotors.svg'},
                
                {'name': 'Brake Fluid DOT 4', 'description': 'Premium synthetic brake fluid',
                 'price': 12.99, 'stock': 200, 'brand': 'Castrol', 'part_number': 'BF-DOT4-500',
                 'category_id': 2, 'compatible_cars': 'Universal',
                 'specifications': '500ml bottle, high boiling point', 'featured': False,
                 'image_url': '/static/images/products/brake-fluid.svg'},
                
                # Electrical
                {'name': 'Car Battery 12V', 'description': 'Maintenance-free AGM battery',
                 'price': 189.99, 'stock': 35, 'brand': 'Optima', 'part_number': 'BAT-AGM-75',
                 'category_id': 3, 'compatible_cars': 'Most sedans and trucks',
                 'specifications': '750 CCA, 75 Ah, 3-year warranty', 'featured': True,
                 'image_url': '/static/images/products/car-battery.svg'},
                
                {'name': 'Alternator', 'description': 'High-output alternator for reliable charging',
                 'price': 249.99, 'stock': 25, 'brand': 'Bosch', 'part_number': 'ALT-150A',
                 'category_id': 3, 'compatible_cars': 'Toyota Tacoma, 4Runner',
                 'specifications': '150 Amp output', 'featured': False,
                 'image_url': '/static/images/products/alternator.svg'},
                
                # Suspension
                {'name': 'Shock Absorber Set', 'description': 'Gas-charged shock absorbers for smooth ride',
                 'price': 199.99, 'stock': 30, 'brand': 'Monroe', 'part_number': 'SH-GAS-400',
                 'category_id': 4, 'compatible_cars': 'Nissan Altima, Mazda 6',
                 'specifications': 'Rear pair, gas-charged', 'featured': True,
                 'image_url': '/static/images/products/shock-absorbers.svg'},
                
                {'name': 'Coil Spring Set', 'description': 'Heavy-duty coil springs',
                 'price': 139.99, 'stock': 45, 'brand': 'Eibach', 'part_number': 'CS-HD-300',
                 'category_id': 4, 'compatible_cars': 'Jeep Wrangler, Cherokee',
                 'specifications': 'Front pair, +2" lift', 'featured': False,
                 'image_url': '/static/images/products/coil-springs.svg'},
                
                # Filters
                {'name': 'Fuel Filter', 'description': 'High-pressure fuel filter',
                 'price': 19.99, 'stock': 100, 'brand': 'Wix', 'part_number': 'FF-HP-200',
                 'category_id': 5, 'compatible_cars': 'Most fuel-injected vehicles',
                 'specifications': 'In-line mount, 10 micron', 'featured': False,
                 'image_url': '/static/images/products/fuel-filter.svg'},
                
                {'name': 'Cabin Air Filter', 'description': 'Activated carbon cabin filter',
                 'price': 16.99, 'stock': 110, 'brand': 'Mann', 'part_number': 'CAF-AC-150',
                 'category_id': 5, 'compatible_cars': 'BMW 3-Series, Mercedes C-Class',
                 'specifications': 'HEPA filtration, odor elimination', 'featured': False,
                 'image_url': '/static/images/products/cabin-filter.svg'},
                
                # Lighting
                {'name': 'LED Headlight Bulbs', 'description': 'Super bright LED conversion kit',
                 'price': 79.99, 'stock': 70, 'brand': 'Philips', 'part_number': 'LED-H7-6K',
                 'category_id': 6, 'compatible_cars': 'H7 socket (most European cars)',
                 'specifications': '6000K white, 12000 lumens', 'featured': True,
                 'image_url': '/static/images/products/led-headlights.svg'},
                
                {'name': 'Fog Light Assembly', 'description': 'Complete fog light kit',
                 'price': 129.99, 'stock': 50, 'brand': 'Hella', 'part_number': 'FL-KIT-500',
                 'category_id': 6, 'compatible_cars': 'Universal with custom brackets',
                 'specifications': 'Includes wiring harness and switch', 'featured': False,
                 'image_url': '/static/images/products/fog-light.svg'},
            ]
            
            for prod_data in products_data:
                product = Product(**prod_data)
                db.session.add(product)
            
            db.session.commit()
            print("Database initialized with sample data!")

# ============================================================================
# ROUTES - PAGE VIEWS
# ============================================================================

@app.route('/')
def index():
    featured_products = Product.query.filter_by(featured=True).limit(6).all()
    categories = Category.query.all()
    return render_template('index.html', featured_products=featured_products, categories=categories)

@app.route('/products')
def products():
    category_id = request.args.get('category', type=int)
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', 'name')
    
    query = Product.query
    
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    if search_query:
        query = query.filter(
            (Product.name.contains(search_query)) | 
            (Product.description.contains(search_query)) |
            (Product.brand.contains(search_query))
        )
    
    # Sorting
    if sort_by == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort_by == 'name':
        query = query.order_by(Product.name.asc())
    
    products_list = query.all()
    categories = Category.query.all()
    
    return render_template('products.html', products=products_list, categories=categories, 
                         current_category=category_id, search_query=search_query)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    related_products = Product.query.filter_by(category_id=product.category_id).filter(Product.id != product_id).limit(4).all()
    return render_template('product_detail.html', product=product, related_products=related_products)

@app.route('/cart')
def cart():
    cart_items = CartItem.query.all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/checkout')
def checkout():
    cart_items = CartItem.query.all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/admin')
def admin():
    products_list = Product.query.all()
    categories = Category.query.all()
    return render_template('admin.html', products=products_list, categories=categories)

# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    
    # Check if item already in cart
    cart_item = CartItem.query.filter_by(product_id=product_id).first()
    
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
    
    db.session.commit()
    
    cart_count = sum(item.quantity for item in CartItem.query.all())
    return jsonify({'success': True, 'cart_count': cart_count})

@app.route('/api/cart/update', methods=['POST'])
def update_cart():
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity')
    
    cart_item = CartItem.query.get(item_id)
    if cart_item:
        if quantity > 0:
            cart_item.quantity = quantity
        else:
            db.session.delete(cart_item)
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False}), 404

@app.route('/api/cart/remove/<int:item_id>', methods=['DELETE'])
def remove_from_cart(item_id):
    cart_item = CartItem.query.get(item_id)
    if cart_item:
        db.session.delete(cart_item)
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False}), 404

@app.route('/api/order', methods=['POST'])
def create_order():
    data = request.get_json()
    
    cart_items = CartItem.query.all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    
    order = Order(
        customer_name=data.get('name'),
        email=data.get('email'),
        phone=data.get('phone'),
        address=data.get('address'),
        total_amount=total,
        items=str([{'product': item.product.name, 'quantity': item.quantity, 'price': item.product.price} for item in cart_items])
    )
    
    db.session.add(order)
    
    # Clear cart
    CartItem.query.delete()
    db.session.commit()
    
    return jsonify({'success': True, 'order_id': order.id})

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json()
    
    product = Product(
        name=data.get('name'),
        description=data.get('description'),
        price=data.get('price'),
        stock=data.get('stock'),
        brand=data.get('brand'),
        part_number=data.get('part_number'),
        category_id=data.get('category_id'),
        compatible_cars=data.get('compatible_cars'),
        specifications=data.get('specifications')
    )
    
    db.session.add(product)
    db.session.commit()
    
    return jsonify({'success': True, 'product_id': product.id})

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.get_json()
    
    product.name = data.get('name', product.name)
    product.description = data.get('description', product.description)
    product.price = data.get('price', product.price)
    product.stock = data.get('stock', product.stock)
    product.brand = data.get('brand', product.brand)
    product.part_number = data.get('part_number', product.part_number)
    product.category_id = data.get('category_id', product.category_id)
    product.compatible_cars = data.get('compatible_cars', product.compatible_cars)
    product.specifications = data.get('specifications', product.specifications)
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/cart/count')
def cart_count():
    count = sum(item.quantity for item in CartItem.query.all())
    return jsonify({'count': count})

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8000)
