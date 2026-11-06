-- Script de Migração e Seed do Domínio Fast-Car +
-- Arquivo: db/001_dominio.sql

-- 1. Criação da tabela de Usuários e Papéis (RBAC)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'funcionario', 'cliente') NOT NULL DEFAULT 'cliente',
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

-- 3. Criação da tabela de Orçamentos (Recurso Principal do Negócio)
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

-- =================================================================
-- SEED DATA (Dados Iniciais para Testes de Avaliação)
-- =================================================================

-- Inserção dos 3 papéis do negócio
INSERT INTO users (id, name, email, password_hash, role) VALUES
(1, 'Dono Fast-Car', 'admin@fastcar.com', 'scrypt:32768:8:1$hash_admin', 'admin'),
(2, 'Instalador Técnico', 'tech@fastcar.com', 'scrypt:32768:8:1$hash_func', 'funcionario'),
(3, 'Marcos Cliente', 'cliente@email.com', 'scrypt:32768:8:1$hash_cliente', 'cliente')
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