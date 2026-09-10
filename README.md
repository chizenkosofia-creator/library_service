# 📚 Library Service API


---

## ✨ Features

* **Book & Inventory Management:** Full CRUD capabilities for managing books, stock inventory, and daily borrowing fees.
* **Borrowing Logic:**
  * Track borrowed and returned books.
  * Automatic inventory adjustments upon borrowing or returning.
  * Overdue book handling with automated fine calculation (`FINE_MULTIPLIER = 2`).
  * Block new borrowings for users with unpaid/pending payments.
* **Stripe Payment Integration:**
  * Automated Stripe Checkout Session generation for borrowings and overdue fines.
  * Dedicated `success/` and `cancel/` redirect handling endpoints.
* **Asynchronous Notifications (Celery + Redis + Telegram):**
  * Immediate Telegram alerts for new borrowings and successful payments.
  * Scheduled daily checks via Celery Beat for overdue borrowings.
* **Containerized Infrastructure:** Fully orchestrated via Docker Compose (PostgreSQL, Redis, Django, Celery Worker/Beat).

---

## 🛠 Tech Stack

* **Language:** Python 3.12+
* **Framework:** Django 5.x, Django REST Framework (DRF)
* **Database:** PostgreSQL
* **Task Queue & Broker:** Celery, Redis
* **Third-Party APIs:** Stripe API, Telegram Bot API
* **DevOps & Tools:** Docker, Docker Compose, Git

---

## 🚀 Quick Start & Installation

### Prerequisites
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
* Python 3.12+ (if running locally outside Docker).

---

### 1. Clone the Repository
```bash
git clone https://github.com/chizenkosofia-creator/library_service.git
