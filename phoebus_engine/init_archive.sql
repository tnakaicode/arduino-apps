-- =========================================
-- Archive Engine tolerant schema (allow bad PV)
-- =========================================

DROP DATABASE IF EXISTS archive;
CREATE DATABASE archive;
USE archive;

-- =========================
-- USERS
-- =========================
CREATE USER IF NOT EXISTS 'archive'@'192.168.3.%' IDENTIFIED BY 'pass';
CREATE USER IF NOT EXISTS 'report'@'192.168.3.%' IDENTIFIED BY 'pass';

GRANT ALL PRIVILEGES ON archive.* TO 'archive'@'192.168.3.%';
GRANT SELECT ON archive.* TO 'report'@'192.168.3.%';

FLUSH PRIVILEGES;

-- =========================
-- CORE TABLES
-- =========================
CREATE TABLE smpl_eng (
   eng_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
   name VARCHAR(100),
   descr VARCHAR(200),
   url VARCHAR(200)
);

INSERT INTO smpl_eng VALUES (1,'Main','Archive Engine','http://localhost:4812/main');

CREATE TABLE chan_grp (
   grp_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
   name VARCHAR(100),
   eng_id INT UNSIGNED,
   descr VARCHAR(200),
   enabling_chan_id INT UNSIGNED
);

INSERT INTO chan_grp VALUES (1,'Main',1,'Main Group',NULL);

CREATE TABLE smpl_mode (
   smpl_mode_id INT UNSIGNED PRIMARY KEY,
   name VARCHAR(100),
   descr VARCHAR(200)
);

INSERT INTO smpl_mode VALUES
(1,'Monitor','Store updates'),
(2,'Scan','Periodic');

CREATE TABLE channel (
   channel_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
   name VARCHAR(200) NOT NULL,
   grp_id INT UNSIGNED,
   smpl_mode_id INT UNSIGNED,
   smpl_val DOUBLE DEFAULT 0,
   smpl_per DOUBLE DEFAULT 1,
   UNIQUE KEY channel_name_idx(name)
);

CREATE TABLE severity (
   severity_id INT UNSIGNED PRIMARY KEY,
   name VARCHAR(100)
);

INSERT INTO severity VALUES
(1,'OK'),(2,'MINOR'),(3,'MAJOR'),(4,'INVALID');

CREATE TABLE status (
   status_id INT UNSIGNED PRIMARY KEY,
   name VARCHAR(100)
);

INSERT INTO status VALUES
(1,'OK'),(2,'disconnected');

-- =========================
-- ✅ SAMPLE (fault tolerant)
-- =========================
CREATE TABLE sample (
   channel_id INT UNSIGNED NOT NULL,
   smpl_time TIMESTAMP NOT NULL,
   nanosecs INT UNSIGNED NOT NULL DEFAULT 0,
   severity_id INT UNSIGNED NOT NULL,
   status_id INT UNSIGNED NOT NULL,

   datatype VARCHAR(10),

   num_val DOUBLE,
   float_val DOUBLE,
   str_val VARCHAR(200),
   array_val BLOB,

   KEY idx_sample (channel_id, smpl_time, nanosecs)
);

-- =========================
-- METADATA
-- =========================
CREATE TABLE num_metadata (
   channel_id INT UNSIGNED PRIMARY KEY,
   low_disp_rng DOUBLE,
   high_disp_rng DOUBLE,
   low_warn_lmt DOUBLE,
   high_warn_lmt DOUBLE,
   low_alarm_lmt DOUBLE,
   high_alarm_lmt DOUBLE,
   prec INT,
   unit VARCHAR(100)
);

CREATE TABLE enum_metadata (
   channel_id INT UNSIGNED,
   enum_nbr INT,
   enum_val VARCHAR(200)
);

-- =========================
-- ✅ IMPORTANT: disable strict SQL mode
-- =========================
SET SESSION sql_mode='';

-- =========================
-- AUTO DELETE (1 day)
-- =========================
SET GLOBAL event_scheduler = ON;

DROP EVENT IF EXISTS delete_old_samples;

CREATE DEFINER=`archive`@`%`
EVENT delete_old_samples
ON SCHEDULE EVERY 1 HOUR
DO
DELETE FROM sample
WHERE smpl_time < NOW() - INTERVAL 3 DAY;
