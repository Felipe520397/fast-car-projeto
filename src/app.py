import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fastcar_secret_key_2026")

# Simulação de Base de Dados (Estrutura alinhada com o db/001_dominio.sql)
USERS_DB = {
    1: {"id": 1, "name": "Dono Fast-Car", "email": "admin@fastcar.com", "role": "admin"},
    2: {"id": 2, "name": "Instalador Técnico", "email": "tech@fastcar.com", "role": "funcionario"},
    3: {"id": 3, "name": "Marcos Cliente", "email": "cliente@email.com", "role": "cliente"}
}

QUOTES_DB = [
    {
        "id": 1,
        "user_id": 3,
        "vehicle_model": "Toyota Hilux SW4",
        "service_type": "Chave Smart Key",
        "description": "Codificação de nova chave de presença presencial OBD2.",
        "license_plate": "ABC-1234",
        "status": "pendente",
        "image_path": "uploads/sw4_key.jpg",
        "admin_notes": ""
    },
    {
        "id": 2,
        "user_id": 3,
        "vehicle_model": "Yamaha XTZ 250 Lander",
        "service_type": "Painel Digital",
        "description": "Instalação de painel digital universal e adequação de chicote elétrico.",
        "license_plate": "XYZ-5678",
        "status": "em_analise",
        "image_path": "uploads/lander_dash.jpg",
        "admin_notes": "Análise técnica em andamento: Chicote e adaptação com orçamento estimado em R$ 380,00."
    }
]

# Helper para obter utilizador autenticado atual (Sessão / Header)
def get_current_user():
    user_id = session.get("user_id") or request.headers.get("X-User-ID")
    if user_id:
        try:
            return USERS_DB.get(int(user_id))
        except (ValueError, TypeError):
            return None
    # Se for chamada à API sem autenticação explícita, mantém compatibilidade com testes locais (Cliente)
    if request.path.startswith('/api/'):
        return USERS_DB[3]
    return None

# Disponibiliza dados globais para todos os templates Jinja
@app.context_processor
def inject_global_context():
    return {
        "current_user": get_current_user(),
        "get_user": lambda uid: USERS_DB.get(uid)
    }

# -----------------------------------------------------------------------------
# ROTAS PÚBLICAS E LANDING PAGE (Requisito 9)
# -----------------------------------------------------------------------------
@app.route('/')
def landing_page():
    """Landing Page Pública com proposta de valor, atalhos e benefícios VIP."""
    return render_template('index.html')

@app.route('/services')
def services_page():
    """Catálogo público de serviços da oficina."""
    return render_template('services.html')

# -----------------------------------------------------------------------------
# AUTENTICAÇÃO E SESSÃO (Login, Logout e Acesso Rápido de Teste)
# -----------------------------------------------------------------------------
@app.route('/login', methods=['GET'])
def login_page():
    """Tela de login com credenciais e atalhos rápidos para Admin e Cliente."""
    if get_current_user():
        return redirect(url_for('list_quotes'))
    next_url = request.args.get('next', '')
    return render_template('login.html', next_url=next_url)

@app.route('/login', methods=['POST'])
def login_action():
    """Processamento do formulário de autenticação."""
    email = (request.form.get('email') or '').strip().lower()
    next_url = request.form.get('next')

    user = next((u for u in USERS_DB.values() if u['email'].lower() == email), None)
    if not user:
        flash('E-mail não cadastrado. Utilize uma das opções de demonstração abaixo.', 'error')
        return render_template('login.html', next_url=next_url), 401

    session['user_id'] = user['id']
    flash(f'Bem-vindo(a), {user["name"]}! Login realizado com sucesso.', 'success')

    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('list_quotes'))

@app.route('/quick-login/<int:user_id>')
def quick_login(user_id):
    """Atalho de login com 1 clique para facilidade de avaliação (Admin / Cliente / Funcionário)."""
    user = USERS_DB.get(user_id)
    if not user:
        flash('Perfil de usuário inexistente.', 'error')
        return redirect(url_for('login_page'))

    session['user_id'] = user['id']
    next_url = request.args.get('next')
    flash(f'Autenticado como {user["name"]} ({user["role"].upper()}).', 'success')

    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('list_quotes'))

@app.route('/logout')
def logout_action():
    """Encerra a sessão do usuário atual."""
    session.pop('user_id', None)
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('landing_page'))

# -----------------------------------------------------------------------------
# ROTAS DE ORÇAMENTOS - CLIENTE E ADMIN (Requisitos 4, 5 e 6)
# -----------------------------------------------------------------------------
@app.route('/quotes', methods=['GET'])
def list_quotes():
    """Lista os orçamentos: cliente vê apenas os seus; admin/funcionário vê todos."""
    current_user = get_current_user()
    if not current_user:
        flash('Por favor, faça login para acessar os orçamentos.', 'warning')
        return redirect(url_for('login_page', next=url_for('list_quotes')))

    status_filter = request.args.get('status')

    # Multi-Tenancy e Isolamento RBAC
    if current_user["role"] in ["admin", "funcionario"]:
        all_user_quotes = QUOTES_DB
    else:
        all_user_quotes = [q for q in QUOTES_DB if q["user_id"] == current_user["id"]]

    quotes_all_count = len(all_user_quotes)

    if status_filter:
        filtered_quotes = [q for q in all_user_quotes if q.get("status") == status_filter]
    else:
        filtered_quotes = all_user_quotes

    return render_template(
        'quote_request.html',
        quotes=filtered_quotes,
        quotes_all_count=quotes_all_count,
        current_status_filter=status_filter
    )

@app.route('/quotes/new', methods=['GET'])
def new_quote_page():
    """Formulário para o cliente solicitar um novo orçamento."""
    current_user = get_current_user()
    if not current_user:
        flash('Você precisa entrar na sua conta para solicitar um orçamento.', 'warning')
        return redirect(url_for('login_page', next=url_for('new_quote_page', service=request.args.get('service'))))

    selected_service = request.args.get('service', '')
    return render_template('new_quote.html', selected_service=selected_service)

@app.route('/quotes/new', methods=['POST'])
def create_quote_action():
    """Processa o pedido de orçamento enviado pelo cliente."""
    current_user = get_current_user()
    if not current_user:
        flash('Sessão expirada. Por favor faça login novamente.', 'error')
        return redirect(url_for('login_page'))

    vehicle_model = request.form.get('vehicle_model', '').strip()
    service_type = request.form.get('service_type', '').strip()
    description = request.form.get('description', '').strip()
    license_plate = request.form.get('license_plate', '').strip()
    image_name = request.form.get('image_name', '').strip() or None

    if not vehicle_model or not service_type or not description:
        flash('Por favor, preencha todos os campos obrigatórios (*).', 'error')
        return render_template('new_quote.html', selected_service=service_type), 400

    new_id = max([q['id'] for q in QUOTES_DB], default=0) + 1
    new_quote = {
        "id": new_id,
        "user_id": current_user["id"],
        "vehicle_model": vehicle_model,
        "service_type": service_type,
        "description": description,
        "license_plate": license_plate,
        "status": "pendente",
        "image_path": image_name,
        "admin_notes": ""
    }
    QUOTES_DB.append(new_quote)
    flash(f'Orçamento #{new_id} enviado com sucesso! Nossa equipe técnica avaliará seu {vehicle_model}.', 'success')
    return redirect(url_for('list_quotes'))

@app.route('/quotes/<int:quote_id>/status', methods=['POST'])
def update_quote_status(quote_id):
    """Admin/Funcionário: Altera o status e opcionalmente adiciona resposta/devolutiva para o cliente (Requisito 5 - RBAC)."""
    current_user = get_current_user()
    if not current_user or current_user["role"] not in ["admin", "funcionario"]:
        flash('Acesso negado: apenas administradores e técnicos podem alterar o status.', 'error')
        return redirect(url_for('list_quotes')), 403

    new_status = request.form.get('status')
    admin_notes = request.form.get('admin_notes', '').strip()
    valid_statuses = ['pendente', 'em_analise', 'aprovado', 'concluido', 'cancelado']
    if new_status not in valid_statuses:
        flash('Status inválido.', 'error')
        return redirect(url_for('list_quotes'))

    quote = next((q for q in QUOTES_DB if q["id"] == quote_id), None)
    if not quote:
        flash('Orçamento não encontrado.', 'error')
        return redirect(url_for('list_quotes'))

    quote["status"] = new_status
    if 'admin_notes' in request.form:
        quote["admin_notes"] = admin_notes

    flash(f'Status do orçamento #{quote_id} atualizado para "{new_status.replace("_", " ").upper()}" e devolvido ao cliente com sucesso.', 'success')
    return redirect(url_for('list_quotes'))

@app.route('/quotes/<int:quote_id>/delete', methods=['POST'])
def delete_quote_action(quote_id):
    """Admin: Remove um orçamento do sistema (Requisito 5 - RBAC)."""
    current_user = get_current_user()
    if not current_user or current_user["role"] != "admin":
        flash('Acesso proibido: apenas o Administrador pode excluir orçamentos.', 'error')
        return redirect(url_for('list_quotes')), 403

    QUOTES_DB[:] = [q for q in QUOTES_DB if q["id"] != quote_id]
    flash(f'Orçamento #{quote_id} removido com sucesso.', 'success')
    return redirect(url_for('list_quotes'))

# -----------------------------------------------------------------------------
# API REST COM CRUD, RBAC E ISOLAMENTO (Requisitos 3, 5 e 6)
# -----------------------------------------------------------------------------
@app.route('/api/quotes', methods=['GET'])
def api_list_quotes():
    """API: Listagem de orçamentos com isolamento por utilizador."""
    current_user = get_current_user()
    if current_user and current_user["role"] in ["admin", "funcionario"]:
        return jsonify(QUOTES_DB), 200

    user_id = current_user["id"] if current_user else 3
    user_quotes = [q for q in QUOTES_DB if q["user_id"] == user_id]
    return jsonify(user_quotes), 200

@app.route('/api/quotes', methods=['POST'])
def api_create_quote():
    """API: Criação de novo orçamento pelo cliente."""
    current_user = get_current_user()
    user_id = current_user["id"] if current_user else 3
    data = request.json or {}

    new_id = max([q['id'] for q in QUOTES_DB], default=0) + 1
    new_quote = {
        "id": new_id,
        "user_id": user_id,
        "vehicle_model": data.get("vehicle_model", "Veículo Não Informado"),
        "service_type": data.get("service_type", "Geral"),
        "description": data.get("description", ""),
        "status": "pendente",
        "image_path": data.get("image_path", None),
        "admin_notes": data.get("admin_notes", None)
    }
    QUOTES_DB.append(new_quote)
    return jsonify({"message": "Orçamento criado com sucesso", "quote": new_quote}), 201

@app.route('/api/quotes/<int:quote_id>', methods=['GET'])
def api_get_quote(quote_id):
    """API: Detalhes do orçamento (Verifica Isolamento - Requisito 6)."""
    current_user = get_current_user()
    quote = next((q for q in QUOTES_DB if q["id"] == quote_id), None)

    if not quote:
        return jsonify({"error": "Orçamento não encontrado"}), 404

    # Bloqueio Multi-Tenancy: Cliente só pode abrir os seus próprios registos
    if current_user and current_user["role"] == "cliente" and quote["user_id"] != current_user["id"]:
        return jsonify({"error": "Acesso negado: registo pertencente a outro utilizador"}), 403

    return jsonify(quote), 200

@app.route('/api/quotes/<int:quote_id>', methods=['DELETE'])
def api_delete_quote(quote_id):
    """API: Remoção de orçamento com verificação RBAC (Requisito 5)."""
    current_user = get_current_user()

    # Apenas Admin pode apagar registos diretamente
    if not current_user or current_user["role"] != "admin":
        return jsonify({"error": "Acesso proibido: papel sem permissão para esta ação"}), 403

    QUOTES_DB[:] = [q for q in QUOTES_DB if q["id"] != quote_id]
    return jsonify({"message": f"Orçamento {quote_id} removido com sucesso"}), 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8204))
    app.run(host='0.0.0.0', port=port, debug=True)
