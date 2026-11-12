-- Script de Migração e Seed do Domínio Fast-Car +
-- Arquivo: db/001_dominio.sql

-- 1. Criação da tabela de Usuários e Papéis (RBAC + SaaS Subscriptions)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'funcionario', 'cliente') NOT NULL DEFAULT 'cliente',
    plan ENUM('free', 'pro') NOT NULL DEFAULT 'free',
    stripe_customer_id VARCHAR(255) NULL,
    stripe_subscription_id VARCHAR(255) NULL,
    subscription_status ENUM('active', 'past_due', 'canceled', 'unpaid', 'incomplete', 'incomplete_expired', 'trialing') NULL DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Criação da tabela de Veículos (Garagem do Cliente)
CREATE TABLE IF NOT EXISTS vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    model VARCHAR(100) NOT NULL,
    year INT NOT NULL,
    license_plate VARCHAR(20) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Criação da tabela de Orçamentos (Recurso Principal do Negócio com Limites por Plano)
CREATE TABLE IF NOT EXISTS quotes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    service_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    status ENUM('pendente', 'em_analise', 'aprovado', 'concluido', 'cancelado') NOT NULL DEFAULT 'pendente',
    image_path VARCHAR(255) NULL,
    admin_notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Criação da tabela de Logs de Auditoria e Eventos de Negócio / Stripe
CREATE TABLE IF NOT EXISTS audit_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    user_id INT NULL,
    payload TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Criação da tabela de Idempotência de Webhooks do Stripe
CREATE TABLE IF NOT EXISTS processed_webhooks (
    id VARCHAR(255) PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =================================================================
-- SEED DATA (Dados Iniciais para Testes de Avaliação)
-- =================================================================

-- Inserção dos 3 papéis do negócio com planos configurados
INSERT INTO users (id, name, email, password_hash, role, plan, stripe_customer_id, stripe_subscription_id, subscription_status) VALUES
(1, 'Dono Fast-Car', 'admin@fastcar.com', 'scrypt:32768:8:1$hash_admin', 'admin', 'pro', 'cus_admin_test', 'sub_admin_test', 'active'),
(2, 'Instalador Técnico', 'tech@fastcar.com', 'scrypt:32768:8:1$hash_func', 'funcionario', 'pro', NULL, NULL, 'active'),
(3, 'Marcos Cliente', 'cliente@email.com', 'scrypt:32768:8:1$hash_cliente', 'cliente', 'free', NULL, NULL, NULL)
ON DUPLICATE KEY UPDATE id=id;

-- Inserção de veículos de teste
INSERT INTO vehicles (id, user_id, model, year, license_plate) VALUES
(1, 3, 'Toyota Hilux SW4', 2019, 'ABC-1234'),
(2, 3, 'Yamaha XTZ 250 Lander', 2006, 'XYZ-5678')
ON DUPLICATE KEY UPDATE id=id;

-- Inserção de orçamentos iniciais
INSERT INTO quotes (id, user_id, vehicle_id, service_type, description, status, image_path, admin_notes) VALUES
(1, 3, 1, 'Chave Smart Key', 'Codificação de nova chave de presença presencial OBD2.', 'pendente', 'uploads/sw4_key.jpg', NULL),
(2, 3, 2, 'Painel Digital', 'Instalação de painel digital universal e adequação de chicote elétrico.', 'em_analise', 'uploads/lander_dash.jpg', 'Análise técnica em andamento: Chicote e adaptação com orçamento estimado em R$ 380,00.')
ON DUPLICATE KEY UPDATE id=id;

-- Inserção de eventos de log iniciais
INSERT INTO audit_logs (event_type, description, user_id) VALUES
('system_init', 'Inicialização da plataforma Fast-Car + e catálogo SaaS.', 1),
('user_registered', 'Usuário Marcos Cliente registrado no Plano Free (limite: 3 orçamentos).', 3);
