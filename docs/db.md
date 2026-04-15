# Tourist Audio Guide - Database Schema

## Overview

This database supports a **tourist audio guide application** with:

- Points of Interest (POIs)
- Multi-language content (text + audio)
- Tours (ordered POIs)
- User authentication
- Subscription system

---

## Tables

---

### 1. Tours

Stores predefined tour collections.

| Column      | Type            | Description      |
| ----------- | --------------- | ---------------- |
| id          | varchar (PK)    | Unique tour ID   |
| name        | varchar         | Tour name        |
| description | text (nullable) | Tour description |

---

### 2. tour_points

Defines ordered POIs inside a tour.

| Column   | Type                    | Description    |
| -------- | ----------------------- | -------------- |
| id       | varchar (PK)            | Unique ID      |
| poi_id   | varchar (FK → Pois.id)  | POI reference  |
| tour_id  | varchar (FK → Tours.id) | Tour reference |
| position | int                     | Order in tour  |

#### Constraints

- `UNIQUE (tour_id, position)` → ensures order integrity

---

### 3. Pois

Core entity representing a Point of Interest.

| Column       | Type                    | Description                  |
| ------------ | ----------------------- | ---------------------------- |
| id           | varchar (PK)            | Unique POI ID                |
| default_lang | varchar (default: "vi") | Fallback language            |
| image        | varchar                 | Image URL                    |
| type         | enum                    | Category (food, drink, etc.) |
| radius       | int                     | Area radius                  |
| latitude     | double                  | GPS latitude                 |
| longitude    | double                  | GPS longitude                |
| status       | enum                    | Active/inactive              |
| slug         | varchar (unique)        | SEO-friendly identifier      |

---

### 4. LocalizedData

Stores localized content per POI.

| Column      | Type                   | Description                  |
| ----------- | ---------------------- | ---------------------------- |
| id          | varchar (PK)           | Unique ID                    |
| poi_id      | varchar (FK → Pois.id) | POI reference                |
| lang_code   | varchar                | Language code (e.g., vi, en) |
| name        | varchar                | Localized name               |
| description | text                   | Localized description        |
| audio       | varchar                | Audio file URL               |

#### Constraints

- `UNIQUE (poi_id, lang_code)` → one translation per language

---

### 5. Users

Stores user accounts.

| Column   | Type             | Description     |
| -------- | ---------------- | --------------- |
| id       | varchar (PK)     | Unique user ID  |
| email    | varchar (unique) | User email      |
| password | varchar          | Hashed password |
| role     | enum             | admin / tourist |

---

### 6. Supscription (Subscription)

Tracks user subscriptions.

| Column         | Type                               | Description               |
| -------------- | ---------------------------------- | ------------------------- |
| id             | varchar (PK)                       | Unique ID                 |
| user_id        | varchar (FK → Users.id)            | Owner                     |
| created_at     | datetime                           | Start time                |
| expired_at     | datetime                           | Expiration                |
| plan_id        | varchar (FK → SupscriptionPlan.id) | Plan reference            |
| payment_method | enum                               | Payment method            |
| amount         | double                             | Paid amount               |
| status         | enum                               | active / expired / failed |

---

### 7. SupscriptionPlan

Defines subscription pricing.

| Column     | Type         | Description  |
| ---------- | ------------ | ------------ |
| id         | varchar (PK) | Plan ID      |
| title      | varchar      | Plan name    |
| price      | double       | Price        |
| updated_at | datetime     | Last updated |

---

## Core Relationships

- `Tours (1) → (N) tour_points`
- `Pois (1) → (N) tour_points`
- `Pois (1) → (N) LocalizedData`
- `Users (1) → (N) Supscription`
- `SupscriptionPlan (1) → (N) Supscription`

---

## Localization Strategy

- Each POI has multiple localized records in `LocalizedData`
- `Pois.default_lang` defines fallback language
- Query pattern:
  - Try `user_lang`
  - Fallback to `default_lang`

---

## Audio Strategy

- Each `(poi_id, lang_code)` has **one audio file**
- Stored as URL in `LocalizedData.audio`
- Served via CDN or static hosting

---

## Key Design Decisions

### 1. Simplicity-first Audio Model

- Single audio per language
- No versioning / voice variants

### 2. Localization via Separate Table

- Avoids duplication
- Supports multi-language expansion

### 3. Ordered Tours

- `tour_points.position` ensures deterministic ordering

### 4. Subscription Snapshot

- Stores `amount` at purchase time
- Decouples from plan price changes

---

## Recommended Indexes

```sql
INDEX (latitude, longitude)
UNIQUE (slug)
UNIQUE (poi_id, lang_code)
UNIQUE (tour_id, position)
UNIQUE (email)
```
