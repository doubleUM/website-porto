import numpy as np
from textblob import TextBlob
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LinearRegression
from sklearn.metrics.pairwise import cosine_similarity
from nltk.tokenize import sent_tokenize, word_tokenize
import nltk
from rank_bm25 import BM25Okapi
import string
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from google import genai
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Global models
ticket_vectorizer = None
ticket_classifier = None
task_duration_model = None

def init_models():
    """Build and train models on synthetic datasets during app startup."""
    global ticket_vectorizer, ticket_classifier, task_duration_model
    print("Initializing Machine Learning Models...")

    # Ensure basic NLTK tokenizers are available safely
    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        print("Downloading NLTK punkt tokenizers...")
        nltk.download('punkt')
        nltk.download('punkt_tab')

    # ---------------------------------------------------------
    # 1. Ticket Auto-Categorizer (Multi-class Classification)
    # ---------------------------------------------------------
    # Synthetic dataset linking support queries to categories
    ticket_data = [
        # Hardware (20 examples)
        ("My screen is completely black and won't turn on", "Hardware"),
        ("The battery drains in 10 minutes", "Hardware"),
        ("I dropped my phone and the glass cracked", "Hardware"),
        ("My laptop keyboard stopped working", "Hardware"),
        ("The charging port is loose and won't charge", "Hardware"),
        ("The cooling fan is making a loud grinding noise", "Hardware"),
        ("My monitor is flickering constantly", "Hardware"),
        ("The power button is stuck inside the case", "Hardware"),
        ("The trackpad is unresponsive on my laptop", "Hardware"),
        ("My headphones are only playing audio out of the left ear", "Hardware"),
        ("The motherboard seems to be fried after the power surge", "Hardware"),
        ("My webcam is displaying very blurry images", "Hardware"),
        ("The internal hard drive makes a clicking sound", "Hardware"),
        ("My phone's speaker is completely muffled", "Hardware"),
        ("The USB-C cable that came in the box is broken", "Hardware"),
        ("My external hard drive is not spinning up", "Hardware"),
        ("The touch screen glass is cracked across the middle", "Hardware"),
        ("I spilled water on my device and it won't boot", "Hardware"),
        ("The hinges on my laptop screen are completely broken", "Hardware"),
        ("My wireless mouse completely stops tracking randomly", "Hardware"),
        
        # Software (20 examples)
        ("How do I update to the latest OS?", "Software"),
        ("The app keeps crashing when I open the camera", "Software"),
        ("I'm getting a blue screen error", "Software"),
        ("The antivirus is blocking my game from launching", "Software"),
        ("The application won't launch after the newest patch", "Software"),
        ("My system freezes when I open multiple browser tabs", "Software"),
        ("I need help installing the new drivers", "Software"),
        ("The software says license expired but I just renewed", "Software"),
        ("Word processor fails to save my documents", "Software"),
        ("My cloud sync keeps failing with error 404", "Software"),
        ("The operating system fails to boot after yesterday's update", "Software"),
        ("Video playback is extremely choppy on the desktop client", "Software"),
        ("My settings are not being preserved across sessions", "Software"),
        ("The application throws a Java memory exception", "Software"),
        ("How can I completely uninstall the program from Windows?", "Software"),
        ("The mobile application drains my battery extremely quickly", "Software"),
        ("My macro scripts stopped working in the new version", "Software"),
        ("I cannot export my video project, it gets stuck at 99%", "Software"),
        ("The UI is glitchy and the buttons are overlapping", "Software"),
        ("My system gives an access denied prompt when updating", "Software"),
        
        # Account (20 examples)
        ("I forgot my password and cannot login", "Account"),
        ("Please delete my account", "Account"),
        ("How do I change my profile picture?", "Account"),
        ("My account is locked due to too many login attempts", "Account"),
        ("I need to update my email address", "Account"),
        ("Can you recover my deleted account?", "Account"),
        ("I didn't receive the password reset email", "Account"),
        ("How do I enable two-factor authentication?", "Account"),
        ("I lost my 2FA backup codes and am locked out", "Account"),
        ("How can I merge two different profiles into one?", "Account"),
        ("I want to change my username", "Account"),
        ("My account says it is suspended for suspicious activity", "Account"),
        ("How do I transfer ownership of this account to my colleague?", "Account"),
        ("I am unable to verify my mobile phone number", "Account"),
        ("Where can I update my security questions?", "Account"),
        ("How do I unlink my Google login from my profile?", "Account"),
        ("My sessions keep logging out automatically every 5 minutes", "Account"),
        ("I am trying to register but the verification code isn't arriving", "Account"),
        ("Please reactivate my disabled account", "Account"),
        ("How do I wipe all my personal data from my profile?", "Account"),
        
        # Billing (20 examples)
        ("Where is my refund?", "Billing"),
        ("I was charged twice for the subscription", "Billing"),
        ("My credit card was declined", "Billing"),
        ("Can I get an invoice for last month?", "Billing"),
        ("Why did the price of my plan increase?", "Billing"),
        ("I want to cancel my subscription", "Billing"),
        ("The checkout page is broken, I can't pay", "Billing"),
        ("Please update my payment method to the new card", "Billing"),
        ("I need to dispute a fraudulent charge on my statement", "Billing"),
        ("How do I switch from a monthly to an annual plan?", "Billing"),
        ("Do you accept wire transfers or PayPal?", "Billing"),
        ("My student discount code isn't applying at checkout", "Billing"),
        ("I was charged after my free trial was already canceled", "Billing"),
        ("Where can I download my annual tax receipt?", "Billing"),
        ("My credit card expired, how do I avoid service interruption?", "Billing"),
        ("Why am I seeing a foreign transaction fee?", "Billing"),
        ("Can I pause my subscription instead of canceling?", "Billing"),
        ("I input the wrong billing address, can I change it?", "Billing"),
        ("I requested a refund last week but the money hasn't arrived", "Billing"),
        ("Why isn't my VAT number being accepted for tax exemption?", "Billing"),
        
        # Sales (20 examples)
        ("Is there a volume discount for enterprise?", "Sales"),
        ("I want to upgrade my team's plan", "Sales"),
        ("Can I schedule a product demo?", "Sales"),
        ("Do you offer special pricing for nonprofits?", "Sales"),
        ("I want to buy 50 licenses for my company", "Sales"),
        ("What are the features of the Premium tier?", "Sales"),
        ("Who can I talk to about a business partnership?", "Sales"),
        ("Can you send me a brochure of your enterprise products?", "Sales"),
        ("How much does it cost to add 10 more seats?", "Sales"),
        ("We are a startup, do you have startup tier discounts?", "Sales"),
        ("What is the difference between the Basic and Pro packages?", "Sales"),
        ("Can we get a custom SLA agreement for our enterprise?", "Sales"),
        ("I'd like to hire an onboarding specialist to train my staff", "Sales"),
        ("Do you white-label your services for resellers?", "Sales"),
        ("Are there hidden setup fees for the Enterprise package?", "Sales"),
        ("I need to procure hardware in bulk for a school district", "Sales"),
        ("Who is the account executive assigned to my region?", "Sales"),
        ("Can we do a 30-day proof of concept before purchasing?", "Sales"),
        ("We need to complete a vendor security questionnaire before buying", "Sales"),
        
        # ==========================================
        # BAHASA INDONESIA TRANSLATIONS (100)
        # ==========================================
        
        # Hardware (Indonesian)
        ("Layar saya benar-benar hitam dan tidak mau menyala", "Hardware"),
        ("Baterai habis dalam 10 menit", "Hardware"),
        ("Ponsel saya jatuh dan kacanya retak", "Hardware"),
        ("Keyboard laptop saya tiba-tiba tidak berfungsi", "Hardware"),
        ("Port pengisian daya longgar dan tidak bisa ngecas", "Hardware"),
        ("Kipas pendingin mengeluarkan suara bising yang sangat keras", "Hardware"),
        ("Monitor saya terus-menerus berkedip", "Hardware"),
        ("Tombol power tersangkut di dalam casing", "Hardware"),
        ("Trackpad di laptop saya tidak merespons sama sekali", "Hardware"),
        ("Headphone saya hanya mengeluarkan suara dari telinga kiri", "Hardware"),
        ("Motherboard sepertinya korslet setelah mati lampu", "Hardware"),
        ("Webcam saya menampilkan gambar yang sangat buram", "Hardware"),
        ("Hard drive internal mengeluarkan bunyi klik", "Hardware"),
        ("Speaker ponsel saya suaranya sangat teredam", "Hardware"),
        ("Kabel USB-C bawaan di dalam kotak rusak", "Hardware"),
        ("Hard drive eksternal saya tidak mau berputar", "Hardware"),
        ("Kaca layar sentuh retak di bagian tengah", "Hardware"),
        ("Perangkat saya ketumpahan air dan tidak mau menyala", "Hardware"),
        ("Engsel layar laptop saya benar-benar patah", "Hardware"),
        ("Mouse nirkabel saya tiba-tiba berhenti bergerak", "Hardware"),

        # Software (Indonesian)
        ("Bagaimana cara update ke OS terbaru?", "Software"),
        ("Aplikasi terus crash saat saya membuka kamera", "Software"),
        ("Saya mendapatkan error blue screen", "Software"),
        ("Antivirus memblokir game saya saat mau dibuka", "Software"),
        ("Aplikasi tidak mau jalan setelah patch terbaru", "Software"),
        ("Sistem saya hang saat membuka banyak tab browser", "Software"),
        ("Saya butuh bantuan untuk menginstal driver baru", "Software"),
        ("Software bilang lisensi kedaluwarsa padahal baru saya perbarui", "Software"),
        ("Aplikasi pemroses kata gagal menyimpan dokumen saya", "Software"),
        ("Sinkronisasi cloud saya terus gagal dengan error 404", "Software"),
        ("Sistem operasi gagal booting setelah update kemarin", "Software"),
        ("Pemutaran video sangat patah-patah di aplikasi desktop", "Software"),
        ("Pengaturan saya kembali ke awal setelah aplikasi ditutup", "Software"),
        ("Aplikasi memunculkan masalah memory limit Java", "Software"),
        ("Bagaimana cara uninstall program ini sampai bersih dari Windows?", "Software"),
        ("Aplikasi mobile ini sangat menguras baterai saya", "Software"),
        ("Script makro saya tidak berfungsi di versi yang baru", "Software"),
        ("Saya tidak bisa export video saya, mentok di 99%", "Software"),
        ("Tampilan UI-nya glitch dan tombol-tombolnya tumpang tindih", "Software"),
        ("Sistem saya memunculkan pesan access denied saat proses update", "Software"),

        # Account (Indonesian)
        ("Saya lupa kata sandi dan tidak bisa login", "Account"),
        ("Tolong hapus akun saya", "Account"),
        ("Bagaimana cara mengganti foto profil saya?", "Account"),
        ("Akun saya terkunci karena terlalu banyak percobaan login", "Account"),
        ("Saya ingin memperbarui alamat surel saya", "Account"),
        ("Bisakah Anda memulihkan akun saya yang terhapus?", "Account"),
        ("Saya tidak menerima email reset password", "Account"),
        ("Bagaimana cara mengaktifkan autentikasi dua faktor?", "Account"),
        ("Saya kehilangan kode cadangan 2FA dan terkurung dari akun", "Account"),
        ("Bagaimana cara menggabungkan dua profil yang berbeda menjadi satu?", "Account"),
        ("Saya ingin mengganti username saya", "Account"),
        ("Akun saya tertulis ditangguhkan karena aktivitas mencurigakan", "Account"),
        ("Bagaimana cara mentransfer kepemilikan akun ini ke rekan kerja saya?", "Account"),
        ("Saya tidak bisa memverifikasi nomor telepon genggam saya", "Account"),
        ("Di mana saya bisa memperbarui pertanyaan keamanan saya?", "Account"),
        ("Bagaimana cara melepas tautan login Google dari profil saya?", "Account"),
        ("Sesi saya terus logout otomatis setiap 5 menit", "Account"),
        ("Saya mencoba mendaftar tetapi kode verifikasi tidak pernah sampai", "Account"),
        ("Tolong aktifkan kembali akun saya yang dinonaktifkan", "Account"),
        ("Bagaimana cara menghapus semua data pribadi saya dari profil?", "Account"),

        # Billing (Indonesian)
        ("Di mana uang pengembalian refund saya?", "Billing"),
        ("Saya ditagih dua kali untuk langganan bulan ini", "Billing"),
        ("Kartu kredit saya ditolak", "Billing"),
        ("Bisa saya minta faktur invoice untuk bulan lalu?", "Billing"),
        ("Mengapa harga paket layanan saya naik?", "Billing"),
        ("Saya ingin membatalkan langganan saya", "Billing"),
        ("Halaman checkout rusak, saya tidak bisa membayar", "Billing"),
        ("Tolong perbarui metode pembayaran saya dengan kartu yang baru", "Billing"),
        ("Saya ingin menyanggah tagihan penipuan di laporan rekening saya", "Billing"),
        ("Bagaimana cara mengubah paket bulanan menjadi paket tahunan?", "Billing"),
        ("Apakah kalian menerima transfer bank atau PayPal?", "Billing"),
        ("Kode diskon pelajar saya tidak bisa dipakai di checkout", "Billing"),
        ("Saya ditagih setelah masa uji coba gratis saya dibatalkan", "Billing"),
        ("Di mana saya bisa mengunduh tanda terima pajak tahunan saya?", "Billing"),
        ("Kartu kredit saya kedaluwarsa, bagaimana agar layanan tidak terputus?", "Billing"),
        ("Mengapa saya dikenakan biaya transaksi luar negeri?", "Billing"),
        ("Bisakah saya menunda langganan saya alih-alih membatalkannya?", "Billing"),
        ("Saya memasukkan alamat penagihan yang salah, bisakah saya ubah?", "Billing"),
        ("Saya meminta pengembalian dana minggu lalu tapi uangnya belum masuk", "Billing"),
        ("Mengapa nomor PPN VAT saya tidak diterima untuk pembebasan pajak?", "Billing"),

        # Sales (Indonesian)
        ("Apakah ada diskon volume untuk pembelian perusahaan enterprise?", "Sales"),
        ("Saya ingin meningkatkan paket langganan tim saya", "Sales"),
        ("Bisakah saya menjadwalkan demo produk?", "Sales"),
        ("Apakah kalian menawarkan harga khusus untuk organisasi nirlaba?", "Sales"),
        ("Saya ingin membeli 50 lisensi untuk perusahaan saya", "Sales"),
        ("Apa saja fitur-fitur dari paket Premium?", "Sales"),
        ("Siapa yang bisa saya hubungi untuk kerja sama bisnis?", "Sales"),
        ("Bisakah Anda mengirimkan brosur untuk produk-produk enterprise Anda?", "Sales"),
        ("Berapa biayanya untuk menambah 10 kursi pengguna lagi?", "Sales"),
        ("Kami adalah perusahaan rintisan startup, apakah ada diskon startup?", "Sales"),
        ("Apa perbedaan utama antara paket Basic dan Pro?", "Sales"),
        ("Bisakah kami membuat kesepakatan SLA khusus untuk perusahaan kami?", "Sales"),
        ("Saya ingin menyewa spesialis orientasi untuk memberikan pelatihan pada staf saya", "Sales"),
        ("Apakah Anda menyediakan sistem white-label untuk para penjual ulang?", "Sales"),
        ("Apakah ada biaya instalasi tersembunyi untuk paket Enterprise?", "Sales"),
        ("Saya perlu membeli perangkat keras dalam jumlah besar untuk distrik sekolah", "Sales"),
        ("Siapa account executive yang ditugaskan untuk wilayah saya?", "Sales"),
        ("Bolehkah kami melakukan Proof of Concept selama 30 hari sebelum membeli?", "Sales"),
        ("Saya tertarik dengan program mitra afiliasi", "Sales"),
        ("Kami harus menyelesaikan kuesioner keamanan pihak ketiga sebelum membeli", "Sales"),
    ]
    # Augmenting simple dataset slightly
    ticket_data *= 5  
    
    texts = [t[0] for t in ticket_data]
    labels = [t[1] for t in ticket_data]

    ticket_vectorizer = TfidfVectorizer(stop_words='english', lowercase=True, ngram_range=(1, 2))
    X = ticket_vectorizer.fit_transform(texts)
    
    ticket_classifier = MultinomialNB()
    ticket_classifier.fit(X, labels)
    
    # ---------------------------------------------------------
    # 2. TaskPulse Kanban Predictor (Regression)
    # ---------------------------------------------------------
    # Predicting Days to Completion based on (word_count, priority_level)
    # Priority scaling: Low=1, Medium=2, High=3
    # Synthetic logic: days = ~1.5 + (words * 0.05) + (priority * 0.8) + noise
    
    X_tasks = np.array([
        [10, 1], [30, 2], [150, 3], [5, 1], [80, 2],
        [200, 3], [50, 1], [10, 3], [60, 2], [110, 2]
    ])
    # Target: Days (rounded)
    y_days = np.array([2, 5, 11, 1, 7, 14, 4, 4, 6, 8])

    task_duration_model = LinearRegression()
    task_duration_model.fit(X_tasks, y_days)

    print("ML Models Initialized Successfully.")

# ============================================================================
# PROJECT 1: SEMANTIC ENGINE (TextForge Summarize/Sentiment)
# ============================================================================

def summarize_text(text, num_sentences=3):
    """Extractive Summarization using TF-IDF."""
    sentences = sent_tokenize(text)
    if len(sentences) <= num_sentences:
        return text

    # Score sentences based on TF-IDF term frequency
    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(sentences)
    
    # Sum of TF-IDF scores for each sentence acts as 'importance'
    sentence_scores = np.array(X.sum(axis=1)).flatten()
    
    # Get indices of top N sentences
    top_indices = sentence_scores.argsort()[-num_sentences:][::-1]
    top_indices.sort() # maintain chronological order
    
    summary = " ".join([sentences[i] for i in top_indices])
    return summary

def analyze_sentiment(text):
    """Return sentiment polarity and subjectivity using TextBlob."""
    blob = TextBlob(text)
    # Polarity: -1 (negative) to 1 (positive)
    # Subjectivity: 0 (objective) to 1 (subjective)
    result = {
        'polarity': round(blob.sentiment.polarity, 2),
        'subjectivity': round(blob.sentiment.subjectivity, 2),
        'tone': 'Positive' if blob.sentiment.polarity > 0.1 else ('Negative' if blob.sentiment.polarity < -0.1 else 'Neutral')
    }
    return result

# ============================================================================
# GEMINI HELPER
# ============================================================================

def call_gemini(prompt, is_json=False):
    try:
        client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt
        )
        res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res) if is_json else res
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return json.loads('{}') if is_json else "Error communicating with AI API."

def summarize_text_gemini(text, num_sentences=3):
    prompt = f"Summarize the following text in exactly {num_sentences} sentences. Return nothing but the summary.\n\nText: {text}"
    return call_gemini(prompt)

def analyze_sentiment_gemini(text):
    prompt = f"Analyze the sentiment of the following text. Return ONLY a JSON object with 'polarity' (a number between -1.0 and 1.0), 'subjectivity' (a number between 0.0 and 1.0), and 'tone' (Positive, Negative, or Neutral). Do not wrap in markdown.\n\nText: {text}"
    return call_gemini(prompt, is_json=True)

# ============================================================================
# PROJECT 2: TICKET AUTO-CATEGORIZER
# ============================================================================

def categorize_ticket_classic(text):
    """Predicts the category of a support ticket."""
    if not ticket_classifier or not ticket_vectorizer:
        init_models()
        
    X_vec = ticket_vectorizer.transform([text])
    prediction = ticket_classifier.predict(X_vec)[0]
    
    # Calculate confidence margin
    probs = ticket_classifier.predict_proba(X_vec)[0]
    confidence = round(max(probs) * 100, 1)
    
    return {
        'category': prediction,
        'confidence': confidence
    }

def categorize_ticket_gemini(text):
    """Predicts the category of a support ticket using Gemini API."""
    prompt = f"""You are an expert customer support routing AI. Analyze the following user's ticket and categorize it into exactly ONE of the following categories:
A) Billing: Anything related to invoices, refunds, charges, or pricing.
B) Software: Bug reports, app crashes, or errors.
C) Account: Login issues, account management, etc.
D) Hardware: Issues with physical devices.
E) Sales: Purchasing inquiries, enterprise contracts, etc.

Return ONLY a JSON object with two fields: "category" (the category name, e.g., "Billing", "Software", "Account", "Hardware", or "Sales") and "confidence" (a number between 0 and 100). Do not include markdown formatting or backticks.

User Ticket: "{text}"
"""
    res = call_gemini(prompt, is_json=True)
    return {
        'category': res.get('category', 'Unknown'),
        'confidence': res.get('confidence', 0)
    }

# ============================================================================
# PROJECT 3: TASKPULSE PREDICTOR (Kanban)
# ============================================================================

def predict_task_duration(description, priority):
    """Predicts how many days a task will take using Gemini."""
    prompt = f"Estimate how many days this software task will take to complete. Return ONLY an integer between 1 and 30.\nDescription: {description}\nPriority: {priority}"
    try:
        days_str = call_gemini(prompt)
        days = int(days_str)
        return max(1, min(30, days))
    except:
        return 5

# ============================================================================
# PROJECT 4: DOCUMENT CHAT (RAG / Semantic Extraction)
# ============================================================================

def chat_with_document(document, query, top_k=2):
    """Finds the most relevant sentences in a doc to answer a query using BM25."""
    sentences = sent_tokenize(document)
    if not sentences:
        return []

    # Tokenize and clean sentences for BM25
    tokenized_corpus = []
    for sent in sentences:
        tokens = word_tokenize(sent.lower())
        # Strip punctuation and english stopwords to improve matching
        tokens = [t for t in tokens if t not in string.punctuation and t not in ENGLISH_STOP_WORDS]
        tokenized_corpus.append(tokens)
        
    # Initialize BM25 with the tokenized document
    bm25 = BM25Okapi(tokenized_corpus)
    
    # Process the query
    query_tokens = word_tokenize(query.lower())
    query_tokens = [t for t in query_tokens if t not in string.punctuation and t not in ENGLISH_STOP_WORDS]
    
    # Get scores for all sentences
    doc_scores = bm25.get_scores(query_tokens)
    
    # Get top K indices
    top_indices = np.argsort(doc_scores)[-top_k:][::-1]
    
    results = []
    for idx in top_indices:
        if doc_scores[idx] > 0.1: # Threshold to ensure it found something
            # Pseudo-normalize BM25 scores to a percentage 
            # (Roughly bounded by query length since BM25 maxes around 3 * tokens)
            conf_percent = min(99, int((doc_scores[idx] / max(2.0, len(query_tokens) * 2.5)) * 100))
            
            results.append({
                'text': sentences[idx],
                'score': conf_percent
            })
            
    if not results:
         return [{'text': "No highly relevant information found in the document regarding that query.", 'score': 0}]
         
    return results

def chat_with_document_gemini(document, query):
    """Finds the most relevant information in a document using Gemini."""
    prompt = f"You are a helpful assistant. Use *only* the following document to answer the query. Return your answer as plain text.\n\nDocument: {document}\n\nQuery: {query}"
    answer = call_gemini(prompt)
    return [{'text': answer, 'score': 99}]
