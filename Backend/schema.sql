-- MySQL schema for the Notification Management Application.
-- This is the single source of truth for the two tables - there is no ORM
-- generating this from Python. Run it directly against MySQL, or let the
-- app create the same tables automatically on startup (see app/db.py:
-- init_db, which runs this exact DDL via PyMySQL).

CREATE DATABASE IF NOT EXISTS notification_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE notification_db;

CREATE TABLE IF NOT EXISTS notifications (
  id          VARCHAR(36)  NOT NULL PRIMARY KEY,
  title       VARCHAR(255) NOT NULL,
  message     TEXT         NOT NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notification_deliveries (
  id                   VARCHAR(36)  NOT NULL PRIMARY KEY,
  notification_id      VARCHAR(36)  NOT NULL,
  channel              VARCHAR(20)  NOT NULL,               -- TEAMS / EMAIL / SLACK
  destination          VARCHAR(255) NOT NULL,
  status               VARCHAR(20)  NOT NULL DEFAULT 'PENDING', -- PENDING/SENT/DELIVERED/FAILED
  provider             VARCHAR(50)  NOT NULL,
  provider_message_id  VARCHAR(255) NULL,
  retry_count          INT          NOT NULL DEFAULT 0,
  error_message        TEXT         NULL,
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_notification_deliveries_notification
    FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE,
  INDEX idx_notification_deliveries_notification_id (notification_id),
  INDEX idx_notification_deliveries_channel (channel),
  INDEX idx_notification_deliveries_status (status),
  INDEX idx_notification_deliveries_provider_message_id (provider_message_id)
) ENGINE=InnoDB;

-- One row per (channel, destination): remembers the anchor of the running
-- conversation thread for that recipient on that channel, so repeated
-- notifications to the same person group together instead of each showing
-- up as a brand new, unrelated message.
--   Slack -> the root message's `ts` (used as `thread_ts` on later posts)
--   Email -> the first email's Message-ID (used as In-Reply-To/References)
--   Teams -> unused; a 1:1 chat is already one continuous conversation
CREATE TABLE IF NOT EXISTS channel_threads (
  channel      VARCHAR(20)  NOT NULL,
  destination  VARCHAR(255) NOT NULL,
  thread_key   VARCHAR(512) NOT NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (channel, destination)
) ENGINE=InnoDB;
