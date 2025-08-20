# tools/project.py
from flask import Blueprint, request, jsonify, render_template
import google.generativeai as genai
import os
import time
import uuid
import threading
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini AI
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.5-pro')

# Create blueprint
project_bp = Blueprint('project', __name__, url_prefix='/api/ai-agentweb')

# In-memory storage for projects
projects = {}

def parse_ai_response(content):
    """Mem-parsing respons AI menjadi komponen terstruktur untuk multi-halaman."""
    result = {
        'title': 'Aplikasi Dihasilkan AI',
        'description': 'Deskripsi tidak tersedia.',
        'pages': {},
        'backend': '',
        'deployment': ''
    }
    
    try:
        # Ekstrak Judul
        title_match = re.search(r'### JUDUL APLIKASI ###\s*(.*?)\s*###', content, re.DOTALL)
        if title_match:
            result['title'] = title_match.group(1).strip()

        # Ekstrak Deskripsi
        desc_match = re.search(r'### DESKRIPSI ###\s*(.*?)\s*###', content, re.DOTALL)
        if desc_match:
            result['description'] = desc_match.group(1).strip()

        # Ekstrak Halaman (Pages)
        page_matches = re.finditer(r'### PAGE: (.*?) ###\s*(.*?)(?=### PAGE:|### BACKEND|### INSTRUKSI|$)', content, re.DOTALL)
        for match in page_matches:
            page_name = match.group(1).strip().lower().replace(" ", "_")
            page_content = match.group(2).strip()
            
            page_data = {'html': '', 'css': '', 'js': '', 'filename': f"{page_name}.html"}
            
            # Cari HTML, CSS, dan JS
            html_match = re.search(r'<html.*?>.*</html>', page_content, re.DOTALL | re.IGNORECASE)
            if html_match:
                soup = BeautifulSoup(html_match.group(0), 'html.parser')
                
                # Ekstrak dan hapus <style>
                css_tags = soup.find_all('style')
                page_data['css'] = '\n'.join(tag.string or '' for tag in css_tags)
                for tag in css_tags:
                    tag.decompose()

                # Ekstrak dan hapus <script>
                js_tags = soup.find_all('script')
                page_data['js'] = '\n'.join(tag.string or '' for tag in js_tags if not tag.get('src'))
                for tag in js_tags:
                    tag.decompose()
                
                # Sisa HTML adalah body content
                body_content = soup.find('body')
                page_data['html'] = str(body_content) if body_content else str(soup)
            else:
                page_data['html'] = f"<body>\n{page_content}\n</body>" # Bungkus konten tanpa HTML lengkap

            result['pages'][page_name] = page_data

        # Ekstrak Backend
        backend_match = re.search(r'### BACKEND \(PYTHON FLASK\) ###\s*(.*?)\s*###', content, re.DOTALL)
        if backend_match:
            result['backend'] = backend_match.group(1).strip()

        # Ekstrak Instruksi Deploy
        deploy_match = re.search(r'### INSTRUKSI DEPLOY ###\s*(.*?)$', content, re.DOTALL)
        if deploy_match:
            result['deployment'] = deploy_match.group(1).strip()

    except Exception as e:
        print(f"Error saat parsing respons: {str(e)}")
    
    return result

def inject_shared_elements(pages, title):
    """Menambahkan navigasi, header, dan footer yang konsisten ke semua halaman."""
    if not pages:
        return

    nav_items = []
    for name, data in pages.items():
        display_name = name.replace('_', ' ').title()
        nav_items.append(f'<li><a href="#" data-page="{name}">{display_name}</a></li>')
    
    nav_html = f'<nav class="app-nav"><ul>{"".join(nav_items)}</ul></nav>'
    header_html = f'<header class="app-header"><h1>{title}</h1>{nav_html}</header>'
    footer_html = '<footer class="app-footer"><p>Dihasilkan oleh AI App Builder</p></footer>'

    shared_css = """
        body { margin: 0; font-family: sans-serif; }
        .app-header { background: #f1f1f1; padding: 20px; border-bottom: 1px solid #ddd; display: flex; justify-content: space-between; align-items: center; }
        .app-header h1 { margin: 0; font-size: 24px; }
        .app-nav ul { list-style: none; margin: 0; padding: 0; display: flex; gap: 20px; }
        .app-nav a { text-decoration: none; color: #333; font-weight: bold; }
        .app-nav a:hover { color: #007bff; }
        .app-main { padding: 20px; min-height: 70vh; }
        .app-footer { background: #333; color: white; text-align: center; padding: 15px; }
    """

    for name, data in pages.items():
        soup = BeautifulSoup(data['html'], 'html.parser')
        
        # Hapus body tag jika ada, kita akan buat ulang
        body_tag = soup.find('body')
        if body_tag:
            body_content = body_tag.decode_contents()
        else:
            body_content = data['html']

        # Buat struktur baru yang konsisten
        full_html_structure = f"""
        {header_html}
        <main class="app-main">
            {body_content}
        </main>
        {footer_html}
        """
        data['html'] = full_html_structure
        data['css'] = shared_css + "\n" + data.get('css', '')

def generate_ai_response(prompt, project_id):
    """Menghasilkan dan memproses respons dari AI."""
    try:
        enhanced_prompt = f"""
        Anda adalah AI developer full-stack yang sangat canggih. Tugas Anda adalah membuat aplikasi web multi-halaman yang modern dan fungsional berdasarkan permintaan pengguna.

        Permintaan Pengguna: "{prompt}"

        HASILKAN KODE LENGKAP DALAM FORMAT TERSTRUKTUR BERIKUT. JANGAN MENAMBAHKAN PENJELASAN DI LUAR STRUKTUR INI.

        ### JUDUL APLIKASI ###
        [Nama aplikasi yang menarik dan relevan]

        ### DESKRIPSI ###
        [Deskripsi singkat 2-3 kalimat tentang fungsi dan tujuan aplikasi]

        ### PAGE: index ###
        [KODE LENGKAP untuk halaman utama (index). Sertakan HTML di dalam tag <body>, CSS di dalam tag <style>, dan JavaScript di dalam tag <script>. Buat desain yang modern dan responsif.]

        ### PAGE: about ###
        [KODE LENGKAP untuk halaman "Tentang Kami" (about). Gunakan struktur HTML, CSS, JS yang sama.]

        ### PAGE: services ###
        [KODE LENGKAP untuk halaman "Layanan" atau "Fitur" (services). Gunakan struktur HTML, CSS, JS yang sama.]

        ### PAGE: contact ###
        [KODE LENGKAP untuk halaman "Kontak" (contact) dengan formulir sederhana. Gunakan struktur HTML, CSS, JS yang sama.]

        ### BACKEND (PYTHON FLASK) ###
        [# Kode backend Python menggunakan Flask.
# Jika tidak diperlukan, tulis: TIDAK DIPERLUKAN]

        ### INSTRUKSI DEPLOY ###
        [# Langkah-langkah untuk menjalankan aplikasi.
# 1. Simpan setiap halaman HTML.
# 2. Jalankan server Flask jika ada.]
        """
        
        response = model.generate_content(enhanced_prompt)
        parsed_response = parse_ai_response(response.text)
        
        if not parsed_response['pages']:
             raise Exception("AI tidak menghasilkan konten halaman yang valid.")

        inject_shared_elements(parsed_response['pages'], parsed_response['title'])
        
        preview_data = {'pages': {}, 'main_page': 'index'}
        for name, data in parsed_response['pages'].items():
            full_page_html = f"""
            <!DOCTYPE html>
            <html lang="id">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{parsed_response['title']} | {name.title()}</title>
                <style>{data['css']}</style>
            </head>
            <body>
                {data['html']}
                <script>
                    document.addEventListener('DOMContentLoaded', () => {{
                        document.querySelectorAll('.app-nav a').forEach(link => {{
                            link.addEventListener('click', e => {{
                                e.preventDefault();
                                const page = e.target.getAttribute('data-page');
                                window.parent.postMessage({{ type: 'navigate', page: page }}, '*');
                            }});
                        }});
                    }});
                </script>
                <script>{data['js']}</script>
            </body>
            </html>
            """
            preview_data['pages'][name] = full_page_html

        projects[project_id] = {
            'status': 'completed',
            'title': parsed_response['title'],
            'description': parsed_response['description'],
            'pages': parsed_response['pages'],
            'backend': parsed_response['backend'],
            'deployment': parsed_response['deployment'],
            'preview': preview_data,
            'timestamp': int(time.time())
        }

    except Exception as e:
        print(f"Error di thread generator: {e}")
        projects[project_id] = {'status': 'error', 'error': str(e)}

@project_bp.route('/create', methods=['POST'])
def create_project():
    prompt = request.json.get('prompt')
    if not prompt:
        return jsonify({'error': 'Prompt tidak boleh kosong'}), 400
    
    project_id = str(uuid.uuid4())
    projects[project_id] = {'status': 'processing', 'prompt': prompt}
    
    thread = threading.Thread(target=generate_ai_response, args=(prompt, project_id))
    thread.start()
    
    return jsonify({'project_id': project_id})

@project_bp.route('/project/<project_id>')
def get_project(project_id):
    project = projects.get(project_id)
    if not project:
        return jsonify({'error': 'Proyek tidak ditemukan'}), 404
    return jsonify(project)

