CREATE DATABASE IF NOT EXISTS flask_python6;
USE flask_python6;

CREATE TABLE IF NOT EXISTS users (
    id_user INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100),
    password VARCHAR(100),
    role ENUM('admin','user','accounting','manager')
);

CREATE TABLE IF NOT EXISTS barang (
    id_barang INT AUTO_INCREMENT PRIMARY KEY,
    nama_barang VARCHAR(100),
    harga DOUBLE,
    stok INT
);

CREATE TABLE IF NOT EXISTS pengajuan (
    id_pengajuan INT AUTO_INCREMENT PRIMARY KEY,
    kode_pengajuan VARCHAR(30),
    id_user INT,
    tanggal DATETIME DEFAULT CURRENT_TIMESTAMP,
    grand_total DOUBLE,
    status ENUM('Draft','Finish','Rejected') DEFAULT 'Draft',
    approved_by VARCHAR(100) NULL,
    approved_at DATETIME NULL,
    rejected_by VARCHAR(100) NULL,
    rejected_at DATETIME NULL,
    signature_data LONGTEXT NULL,
    status_admin ENUM('Pending','Approved','Rejected') DEFAULT 'Pending',
    catatan_admin TEXT,
    status_accounting ENUM('Pending','Approved','Rejected') DEFAULT 'Pending',
    catatan_accounting TEXT,
    signature_accounting LONGTEXT NULL,
    accounting_approved_by VARCHAR(100) NULL,
    accounting_approved_at DATETIME NULL,
    accounting_rejected_by VARCHAR(100) NULL,
    accounting_rejected_at DATETIME NULL,
    status_manager ENUM('Pending','Approved','Rejected') DEFAULT 'Pending',
    catatan_manager TEXT,
    signature_manager LONGTEXT NULL,
    manager_approved_by VARCHAR(100) NULL,
    manager_approved_at DATETIME NULL,
    manager_rejected_by VARCHAR(100) NULL,
    manager_rejected_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS pengajuan_detail (
    id_detail INT AUTO_INCREMENT PRIMARY KEY,
    id_pengajuan INT,
    id_barang INT,
    qty INT,
    harga DOUBLE,
    sub_total DOUBLE
);

INSERT INTO users (username, password, role)
SELECT 'admin', '123', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');

INSERT INTO users (username, password, role)
SELECT 'user', '123', 'user'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'user');

INSERT INTO users (username, password, role)
SELECT 'akuntansi', 'a123', 'accounting'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'akuntansi');

INSERT INTO users (username, password, role)
SELECT 'manager', 'm123', 'manager'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'manager');

INSERT INTO barang (nama_barang, harga, stok)
SELECT 'Semen Tiga Roda', 68000, 120
WHERE NOT EXISTS (SELECT 1 FROM barang WHERE nama_barang = 'Semen Tiga Roda');

INSERT INTO barang (nama_barang, harga, stok)
SELECT 'Cat Tembok 5 Kg', 145000, 45
WHERE NOT EXISTS (SELECT 1 FROM barang WHERE nama_barang = 'Cat Tembok 5 Kg');

INSERT INTO barang (nama_barang, harga, stok)
SELECT 'Pipa PVC 3 Inch', 52000, 80
WHERE NOT EXISTS (SELECT 1 FROM barang WHERE nama_barang = 'Pipa PVC 3 Inch');

INSERT INTO barang (nama_barang, harga, stok)
SELECT 'Keramik 40x40', 78000, 60
WHERE NOT EXISTS (SELECT 1 FROM barang WHERE nama_barang = 'Keramik 40x40');

INSERT INTO barang (nama_barang, harga, stok)
SELECT 'Pasir Bangunan', 250000, 25
WHERE NOT EXISTS (SELECT 1 FROM barang WHERE nama_barang = 'Pasir Bangunan');
