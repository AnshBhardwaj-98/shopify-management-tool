# Shopify Management Tool (Shopify Controller)

A robust web application designed to manage, edit, and perform bulk actions on Shopify products efficiently. Built with FastAPI and a modern customized Jinja2 templating block, it provides an intuitive local dashboard for advanced Shopify store management.

## Features

- **Store Dashboard**: A unified view for analytics and operations management.
- **Product Management**: View, edit, and navigate through products seamlessly.
- **Bulk Actions & Editing**: Efficiently update multiple products or variants at once through the `bulk_action` endpoint.
- **Grid View**: A granular grid representation to manage product parameters.
- **Upload & Export**: Easily import updates or export catalog data.
- **Modern UI**: Polished interface with global navigation, alert messages, and full Dark Mode support built seamlessly using HTML & vanilla CSS for optimal performance.

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Jinja2 Templates, HTML5, Vanilla CSS
- **Data Handling**: Pydantic schemas, organized service architecture
- **Integration**: Designed to interface with Shopify ecosystem

## Directory Structure

```plaintext
shopify_controller/
├── app/
│   ├── api/          # FastAPI routers (products, actions, etc.)
│   ├── clients/      # External API or third-party client integrations
│   ├── core/         # Core application configuration and startup handlers
│   ├── models/       # Data models and structures
│   ├── schemas/      # Pydantic schemas for request/response validation
│   ├── services/     # Core business logic handlers
│   ├── templates/    # Jinja2 HTML templates for the UI
│   └── main.py       # FastAPI application entry point
├── snapshots/        # Data backups or JSON-line snapshot storage
├── .env              # Environment configurations (ignored in git)
├── requirements.txt  # Python package dependencies
└── setup.sh          # Setup shell script
```

## Setup & Running Locally

1. **Clone the repository:**

   ```bash
   git clone <repository_url>
   cd "shopify_controller"
   ```

2. **Set up virtual environment:**

   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration:**
   Create or modify your `.env` file in the root directory mirroring the necessary secrets (like Shopify API keys).

5. **Start the Application:**

   ```bash
   # Use Uvicorn to run the development server
   uvicorn app.main:app --reload
   ```

6. **Access Dashboard:**
   Open your browser and navigate to `http://127.0.0.1:8000/` to access the main dashboard.
