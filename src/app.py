import os
import json
from datetime import datetime
import stripe
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fastcar_secret_key_2026")

# -----------------------------------------------------------------------------
# CONFIGURAÇÕES DO STRIPE (MODO DE TESTE) E AMBIENTE
# -----------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_placeholder")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "price_fastcar_vip_pro_monthly")
DOMAIN_URL = os.getenv("DOMAIN_URL", "http://localhost:8204")

stripe.api_key = STRIPE_SECRET_KEY

# Limites e Regras de Negócio SaaS
FREE_QUOTE_LIMIT = 3
PRO_MONTHLY_PRICE = 49.90

# -----------------------------------------------------------------------------
# BASE DE DADOS EM MEMÓRIA (Alinhada com db/001_dominio.sql)
# -----------------------------------------------------------------------------
USERS_DB = {
    1: {
        "id": 1,
        "name": "Dono Fast-Car",
        "email": "admin@fastcar.com",
        "role": "admin",
        "plan": "pro",
        "stripe_customer_id": "cus_admin_test",
        "stripe_subscription_id": "sub_admin_test",
        "subscription_status": "active"
    },
    2: {
        "id": 2,
        "name": "Instalador Técnico",
        "email": "tech@fastcar.com",
        "role": "funcionario",
        "plan": "pro",
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "subscription_status": "active"
    },
    3: {
        "id": 3,
        "name": "Marcos Cliente",
        "email": "cliente@email.com",
        "role": "cliente",
        "plan": "free",
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "subscription_status": None
    }
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

# Registro de eventos de auditoria / Logs de negócio e Stripe
AUDIT_LOGS = [
    {
        "id": 1,
        "event_type": "system_init",
        "description": "Plataforma Fast-Car + iniciada com suporte a Stripe Billing e RBAC.",
        "user_id": 1,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    },
    {
        "id": 2,
        "event_type": "user_registered",
        "description": "Usuário Marcos Cliente registrado no Plano Free (limite de 3 orçamentos).",
        "user_id": 3,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }
]

# Conjunto para garantir idempotência dos webhooks
PROCESSED_WEBHOOKS = set()

# -----------------------------------------------------------------------------
# HELPERS DE AUTENTICAÇÃO, LIMITES E AUDITORIA
# -----------------------------------------------------------------------------
def log_audit_event(event_type, description, user_id=None, payload=None):
    """Registra evento de auditoria no log do sistema."""
    log_entry = {
        "id": len(AUDIT_LOGS) + 1,
        "event_type": event_type,
        "description": description,
        "user_id": user_id,
        "payload": payload,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }
    AUDIT_LOGS.insert(0, log_entry)

def get_current_user():
    """Retorna o usuário autenticado por sessão ou cabeçalho X-User-ID."""
    user_id = session.get("user_id") or request.headers.get("X-User-ID")
    if user_id:
        try:
            return USERS_DB.get(int(user_id))
        except (ValueError, TypeError):
            return None
    if request.path.startswith('/api/'):
        return USERS_DB.get(3)
    return None

def can_user_create_quote(user):
    """
    Verifica a cada requisição se o usuário pode criar um orçamento de acordo com o plano.
    - Free: máximo de 3 orçamentos
    - Pro: orçamentos ilimitados
    """
    if not user:
        return False, 0, FREE_QUOTE_LIMIT

    # Admin e Funcionário não possuem limitações
    if user.get("role") in ["admin", "funcionario"]:
        return True, 0, -1

    # Plano Pro com assinatura ativa tem orçamentos ilimitados
    if user.get("plan") == "pro" and user.get("subscription_status") == "active":
        return True, 0, -1

    # Plano Free ou assinatura pendente/inadimplente
    user_quotes = [q for q in QUOTES_DB if q["user_id"] == user["id"]]
    count = len(user_quotes)
    allowed = count < FREE_QUOTE_LIMIT
    return allowed, count, FREE_QUOTE_LIMIT

def get_saas_metrics():
    """Calcula as métricas do negócio para o painel administrativo (Requisito 6)."""
    free_count = sum(1 for u in USERS_DB.values() if u.get("plan", "free") == "free")
    pro_count = sum(1 for u in USERS_DB.values() if u.get("plan") == "pro")
    
    # Assinaturas ativas no Stripe
    active_subs = [
        u for u in USERS_DB.values()
        if u.get("subscription_status") == "active" and u.get("role") == "cliente"
    ]
    # Total de assinaturas ativas
    active_subs_count = len(active_subs)
    
    # MRR (Monthly Recurring Revenue) de teste
    mrr = active_subs_count * PRO_MONTHLY_PRICE
    
    return {
        "free_count": free_count,
        "pro_count": pro_count,
        "active_subs_count": active_subs_count,
        "mrr": mrr,
        "recent_logs": AUDIT_LOGS[:15]
    }

# Disponibiliza contexto global para os templates Jinja
@app.context_processor
def inject_global_context():
    user = get_current_user()
    can_create, count, limit = can_user_create_quote(user) if user else (False, 0, FREE_QUOTE_LIMIT)
    return {
        "current_user": user,
        "get_user": lambda uid: USERS_DB.get(uid),
        "can_create_quote": can_create,
        "user_quote_count": count,
        "quote_limit": limit,
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY,
        "saas_metrics": get_saas_metrics() if (user and user.get("role") in ["admin", "funcionario"]) else None
    }

# -----------------------------------------------------------------------------
# ROTAS PÚBLICAS E LANDING PAGE
# -----------------------------------------------------------------------------
@app.route('/')
def landing_page():
    return render_template('index.html')

@app.route('/services')
def services_page():
    return render_template('services.html')

# -----------------------------------------------------------------------------
# AUTENTICAÇÃO, CADASTRO E SESSÃO
# -----------------------------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register_page():
    """Cadastro de novas contas de clientes (Cenário: nasce no Free)."""
    if request.method == 'GET':
        if get_current_user():
            return redirect(url_for('list_quotes'))
        return render_template('register.html')

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()

    if not name or not email:
        flash('Nome e e-mail são obrigatórios.', 'error')
        return render_template('register.html'), 400

    if any(u['email'].lower() == email for u in USERS_DB.values()):
        flash('Este e-mail já está cadastrado. Faça login.', 'warning')
        return redirect(url_for('login_page'))

    new_id = max(USERS_DB.keys(), default=0) + 1
    new_user = {
        "id": new_id,
        "name": name,
        "email": email,
        "role": "cliente",
        "plan": "free",  # Nasce obrigatoriamente no Free
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "subscription_status": None
    }
    USERS_DB[new_id] = new_user
    session['user_id'] = new_id

    log_audit_event("user_registered", f"Nova conta criada: {name} ({email}) no Plano Free.", user_id=new_id)
    flash(f"Conta criada com sucesso no Plano Free! Você tem até {FREE_QUOTE_LIMIT} orçamentos gratuitos.", "success")
    return redirect(url_for('list_quotes'))

@app.route('/login', methods=['GET'])
def login_page():
    if get_current_user():
        return redirect(url_for('list_quotes'))
    next_url = request.args.get('next', '')
    return render_template('login.html', next_url=next_url)

@app.route('/login', methods=['POST'])
def login_action():
    email = (request.form.get('email') or '').strip().lower()
    next_url = request.form.get('next')

    user = next((u for u in USERS_DB.values() if u['email'].lower() == email), None)
    if not user:
        flash('E-mail não cadastrado. Cadastre-se ou use os acessos de teste.', 'error')
        return render_template('login.html', next_url=next_url), 401

    session['user_id'] = user['id']
    flash(f'Bem-vindo(a), {user["name"]}! Login realizado com sucesso.', 'success')

    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('list_quotes'))

@app.route('/quick-login/<int:user_id>')
def quick_login(user_id):
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
    session.pop('user_id', None)
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('landing_page'))

# -----------------------------------------------------------------------------
# STRIPE SUBSCRIPTIONS, CHECKOUT E PORTAL DO CLIENTE (Requisitos 1, 2 e 4)
# -----------------------------------------------------------------------------
@app.route('/subscribe')
def subscribe_page():
    """Página de apresentação dos planos e checkout."""
    current_user = get_current_user()
    return render_template('subscribe.html', current_user=current_user)

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """
    Cria a Checkout Session com mode='subscription' no Stripe (Requisito 2).
    O plano NÃO muda no retorno do checkout; muda apenas pelo webhook.
    """
    current_user = get_current_user()
    if not current_user:
        flash("Faça login para assinar o Clube VIP.", "warning")
        return redirect(url_for('login_page'))

    domain = os.getenv("DOMAIN_URL", request.host_url.rstrip('/'))
    success_url = f"{domain}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{domain}/subscription/cancel"

    # Se estiver em ambiente sem chaves reais do Stripe, avisar amigavelmente
    if not STRIPE_SECRET_KEY or STRIPE_SECRET_KEY.startswith("sk_test_placeholder"):
        flash("Stripe não configurado com chaves de teste reais. Defina STRIPE_SECRET_KEY na stack do Portainer.", "warning")
        return redirect(url_for('subscribe_page'))

    try:
        customer_id = current_user.get("stripe_customer_id")
        if not customer_id:
            customer = stripe.Customer.create(
                email=current_user["email"],
                name=current_user["name"],
                metadata={"user_id": str(current_user["id"])}
            )
            customer_id = customer.id
            current_user["stripe_customer_id"] = customer_id

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": STRIPE_PRO_PRICE_ID,
                "quantity": 1,
            }],
            mode="subscription",
            customer=customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(current_user["id"]),
            metadata={
                "user_id": str(current_user["id"])
            }
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f"Erro ao iniciar Checkout do Stripe: {str(e)}", "error")
        return redirect(url_for('subscribe_page'))

@app.route('/create-portal-session', methods=['POST'])
def create_portal_session():
    """
    Abre o Billing Portal do Stripe para troca de plano ou cancelamento (Requisito 4).
    """
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('login_page'))

    customer_id = current_user.get("stripe_customer_id")
    if not customer_id:
        flash("Você ainda não possui uma assinatura vinculada no Stripe.", "warning")
        return redirect(url_for('list_quotes'))

    domain = os.getenv("DOMAIN_URL", request.host_url.rstrip('/'))
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{domain}/quotes"
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        flash(f"Erro ao abrir Portal de Assinatura do Stripe: {str(e)}", "error")
        return redirect(url_for('list_quotes'))

@app.route('/subscription/success')
def subscription_success():
    """Tela de retorno após conclusão do Checkout."""
    return render_template('subscription_status.html', status='success')

@app.route('/subscription/cancel')
def subscription_cancel():
    """Tela de retorno caso o usuário cancele o Checkout."""
    return render_template('subscription_status.html', status='cancel')

# -----------------------------------------------------------------------------
# STRIPE WEBHOOKS COM VALIDAÇÃO E IDEMPOTÊNCIA (Requisito 3)
# -----------------------------------------------------------------------------
def handle_checkout_session_completed(session_obj):
    customer_id = session_obj.get('customer')
    subscription_id = session_obj.get('subscription')
    user_id = session_obj.get('metadata', {}).get('user_id') or session_obj.get('client_reference_id')
    customer_email = session_obj.get('customer_details', {}).get('email')

    user = None
    if user_id:
        try:
            user = USERS_DB.get(int(user_id))
        except (ValueError, TypeError):
            user = None
    if not user and customer_email:
        user = next((u for u in USERS_DB.values() if u['email'].lower() == customer_email.lower()), None)
    if not user and customer_id:
        user = next((u for u in USERS_DB.values() if u.get('stripe_customer_id') == customer_id), None)

    if user:
        user['stripe_customer_id'] = customer_id
        user['stripe_subscription_id'] = subscription_id
        user['plan'] = 'pro'
        user['subscription_status'] = 'active'
        log_audit_event(
            "checkout.session.completed",
            f"Assinatura Pro (Clube VIP) ativada para {user['name']} ({user['email']}).",
            user_id=user['id'],
            payload={"customer_id": customer_id, "subscription_id": subscription_id}
        )

def handle_subscription_updated(sub_obj):
    sub_id = sub_obj.get('id')
    customer_id = sub_obj.get('customer')
    sub_status = sub_obj.get('status')

    user = next((u for u in USERS_DB.values() if u.get('stripe_subscription_id') == sub_id or u.get('stripe_customer_id') == customer_id), None)
    if user:
        user['subscription_status'] = sub_status
        if sub_status == 'active':
            user['plan'] = 'pro'
        elif sub_status in ['canceled', 'unpaid', 'incomplete_expired']:
            user['plan'] = 'free'
        elif sub_status == 'past_due':
            user['plan'] = 'free'  # Inadimplente: o Pro não continua de graça

        log_audit_event(
            "customer.subscription.updated",
            f"Assinatura {sub_id} atualizada para '{sub_status}' (Usuário: {user['email']}).",
            user_id=user['id'],
            payload={"status": sub_status}
        )

def handle_subscription_deleted(sub_obj):
    sub_id = sub_obj.get('id')
    customer_id = sub_obj.get('customer')

    user = next((u for u in USERS_DB.values() if u.get('stripe_subscription_id') == sub_id or u.get('stripe_customer_id') == customer_id), None)
    if user:
        user['plan'] = 'free'
        user['subscription_status'] = 'canceled'
        user['stripe_subscription_id'] = None
        log_audit_event(
            "customer.subscription.deleted",
            f"Assinatura cancelada para {user['name']} ({user['email']}). Plano revertido para Free.",
            user_id=user['id'],
            payload={"subscription_id": sub_id}
        )

def handle_invoice_payment_failed(invoice_obj):
    customer_id = invoice_obj.get('customer')
    sub_id = invoice_obj.get('subscription')

    user = next((u for u in USERS_DB.values() if u.get('stripe_customer_id') == customer_id or u.get('stripe_subscription_id') == sub_id), None)
    if user:
        user['subscription_status'] = 'past_due'
        user['plan'] = 'free'  # Pro suspenso
        log_audit_event(
            "invoice.payment_failed",
            f"Cobrança de renovação falhou para {user['name']} ({user['email']}). Marcado como inadimplente.",
            user_id=user['id'],
            payload={"customer_id": customer_id}
        )

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Endpoint de Webhooks do Stripe.
    Valida a assinatura, garante idempotência e processa os 4 eventos essenciais.
    """
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    event = None
    if STRIPE_WEBHOOK_SECRET and not STRIPE_WEBHOOK_SECRET.startswith("whsec_placeholder"):
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return jsonify({"error": "Invalid payload"}), 400
        except stripe.error.SignatureVerificationError:
            return jsonify({"error": "Invalid signature"}), 400
    else:
        # Fallback para desenvolvimento e testes automatizados sem chave
        try:
            event = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400

    if not event:
        return jsonify({"error": "Event not found"}), 400

    event_id = event.get('id')
    event_type = event.get('type')

    # Verificação de Idempotência
    if event_id and event_id in PROCESSED_WEBHOOKS:
        return jsonify({"status": "already_processed", "event_id": event_id}), 200

    if event_id:
        PROCESSED_WEBHOOKS.add(event_id)

    data_object = event.get('data', {}).get('object', {})

    if event_type == 'checkout.session.completed':
        handle_checkout_session_completed(data_object)
    elif event_type == 'customer.subscription.updated':
        handle_subscription_updated(data_object)
    elif event_type == 'customer.subscription.deleted':
        handle_subscription_deleted(data_object)
    elif event_type == 'invoice.payment_failed':
        handle_invoice_payment_failed(data_object)

    return jsonify({"status": "success", "event_type": event_type}), 200

# -----------------------------------------------------------------------------
# PAINEL ADMINISTRATIVO SAAS E MRR (Requisito 6)
# -----------------------------------------------------------------------------
@app.route('/admin/saas')
def admin_saas_metrics():
    """Painel exclusivo para Admin: Usuários por plano, assinaturas ativas, MRR e logs."""
    current_user = get_current_user()
    if not current_user or current_user["role"] != "admin":
        flash("Acesso restrito ao Administrador.", "error")
        return redirect(url_for('list_quotes')), 403

    metrics = get_saas_metrics()
    return render_template('admin_saas.html', saas_metrics=metrics, all_users=list(USERS_DB.values()))

# -----------------------------------------------------------------------------
# ROTAS DE ORÇAMENTOS COM LIMITES DO PLANO FREE (Requisito 5)
# -----------------------------------------------------------------------------
@app.route('/quotes', methods=['GET'])
def list_quotes():
    current_user = get_current_user()
    if not current_user:
        flash('Por favor, faça login para acessar os orçamentos.', 'warning')
        return redirect(url_for('login_page', next=url_for('list_quotes')))

    status_filter = request.args.get('status')

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
    current_user = get_current_user()
    if not current_user:
        flash('Você precisa entrar na sua conta para solicitar um orçamento.', 'warning')
        return redirect(url_for('login_page', next=url_for('new_quote_page', service=request.args.get('service'))))

    selected_service = request.args.get('service', '')
    return render_template('new_quote.html', selected_service=selected_service)

@app.route('/quotes/new', methods=['POST'])
def create_quote_action():
    """Processa o orçamento com verificação estrita de limites do plano Free."""
    current_user = get_current_user()
    if not current_user:
        flash('Sessão expirada. Faça login novamente.', 'error')
        return redirect(url_for('login_page'))

    # Verificação de Limite no Backend
    can_create, count, limit = can_user_create_quote(current_user)
    if not can_create:
        log_audit_event("limit_reached", f"Web: Usuário {current_user['email']} bloqueado por limite Free ({limit}).", user_id=current_user['id'])
        flash(f"Limite do plano Free atingido ({count}/{limit} orçamentos criados). Assine o Clube VIP (Pro) para ter orçamentos ilimitados e benefícios exclusivos!", "warning")
        return redirect(url_for('subscribe_page'))

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
    log_audit_event("quote_created", f"Orçamento #{new_id} criado por {current_user['email']} ({vehicle_model}).", user_id=current_user['id'])
    flash(f'Orçamento #{new_id} enviado com sucesso! Nossa equipe técnica avaliará seu {vehicle_model}.', 'success')
    return redirect(url_for('list_quotes'))

@app.route('/quotes/<int:quote_id>/status', methods=['POST'])
def update_quote_status(quote_id):
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

    log_audit_event("quote_status_updated", f"Orçamento #{quote_id} atualizado para '{new_status}' pelo técnico/admin.", user_id=current_user['id'])
    flash(f'Status do orçamento #{quote_id} atualizado para "{new_status.replace("_", " ").upper()}" e devolvido ao cliente com sucesso.', 'success')
    return redirect(url_for('list_quotes'))

@app.route('/quotes/<int:quote_id>/delete', methods=['POST'])
def delete_quote_action(quote_id):
    current_user = get_current_user()
    if not current_user or current_user["role"] != "admin":
        flash('Acesso proibido: apenas o Administrador pode excluir orçamentos.', 'error')
        return redirect(url_for('list_quotes')), 403

    QUOTES_DB[:] = [q for q in QUOTES_DB if q["id"] != quote_id]
    log_audit_event("quote_deleted", f"Orçamento #{quote_id} removido pelo Administrador.", user_id=current_user['id'])
    flash(f'Orçamento #{quote_id} removido com sucesso.', 'success')
    return redirect(url_for('list_quotes'))

# -----------------------------------------------------------------------------
# API REST COM LIMITES SAAS E ISOLAMENTO MULTI-TENANCY (Requisitos 3, 5 e 6)
# -----------------------------------------------------------------------------
@app.route('/api/quotes', methods=['GET'])
def api_list_quotes():
    current_user = get_current_user()
    if current_user and current_user["role"] in ["admin", "funcionario"]:
        return jsonify(QUOTES_DB), 200

    user_id = current_user["id"] if current_user else 3
    user_quotes = [q for q in QUOTES_DB if q["user_id"] == user_id]
    return jsonify(user_quotes), 200

@app.route('/api/quotes', methods=['POST'])
def api_create_quote():
    """API: Criação de novo orçamento com verificação estrita de limites Free (Requisito 5)."""
    current_user = get_current_user()
    user_id = current_user["id"] if current_user else 3
    user = USERS_DB.get(user_id)

    # Verificação do Limite do Plano
    can_create, count, limit = can_user_create_quote(user)
    if not can_create:
        log_audit_event("limit_reached", f"API: Usuário {user['email']} bloqueado por atingir limite Free ({limit}).", user_id=user['id'])
        return jsonify({
            "error": "Limite do plano Free atingido",
            "message": f"Você atingiu o limite de {limit} orçamentos do plano Free. Faça upgrade para o Clube VIP (Pro) para ter solicitações ilimitadas!",
            "limit": limit,
            "current_count": count,
            "plan": user.get("plan", "free"),
            "upgrade_url": "/subscribe"
        }), 403

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
    log_audit_event("quote_created", f"API: Orçamento #{new_id} criado com sucesso por {user['email']}.", user_id=user['id'])
    return jsonify({"message": "Orçamento criado com sucesso", "quote": new_quote}), 201

@app.route('/api/quotes/<int:quote_id>', methods=['GET'])
def api_get_quote(quote_id):
    current_user = get_current_user()
    quote = next((q for q in QUOTES_DB if q["id"] == quote_id), None)

    if not quote:
        return jsonify({"error": "Orçamento não encontrado"}), 404

    if current_user and current_user["role"] == "cliente" and quote["user_id"] != current_user["id"]:
        return jsonify({"error": "Acesso negado: registo pertencente a outro utilizador"}), 403

    return jsonify(quote), 200

@app.route('/api/quotes/<int:quote_id>', methods=['DELETE'])
def api_delete_quote(quote_id):
    current_user = get_current_user()

    if not current_user or current_user["role"] != "admin":
        return jsonify({"error": "Acesso proibido: papel sem permissão para esta ação"}), 403

    QUOTES_DB[:] = [q for q in QUOTES_DB if q["id"] != quote_id]
    return jsonify({"message": f"Orçamento {quote_id} removido com sucesso"}), 200

@app.route('/api/saas/metrics', methods=['GET'])
def api_saas_metrics():
    """API: Retorna métricas do SaaS (Acesso restrito ao Admin)."""
    current_user = get_current_user()
    if not current_user or current_user["role"] != "admin":
        return jsonify({"error": "Acesso negado"}), 403
    return jsonify(get_saas_metrics()), 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8204))
    app.run(host='0.0.0.0', port=port, debug=True)
